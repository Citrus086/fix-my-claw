"""Service CLI commands and launchd helpers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from ..protocol import (
    build_service_reconcile_payload,
    build_service_status_payload,
)
from ..shared import _as_path
from ._config_helpers import load_or_init_config

if TYPE_CHECKING:
    from ..config import AppConfig


def _service_platform_supported() -> bool:
    return sys.platform == "darwin"


def _get_launchd_label() -> str:
    return "com.fix-my-claw.monitor"


def _get_launchd_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{_get_launchd_label()}.plist"


def _get_launchd_domain() -> str:
    return f"gui/{os.getuid()}"


def _get_launchd_job_target() -> str:
    return f"{_get_launchd_domain()}/{_get_launchd_label()}"


def _get_launchd_service_binary_path() -> Path:
    return Path.home() / ".fix-my-claw" / "bin" / "fix-my-claw-service"


def _get_fix_my_claw_path() -> str:
    argv0 = Path(sys.argv[0]).expanduser()
    if argv0.name == "fix-my-claw" and argv0.exists():
        return str(argv0.resolve())
    current = shutil.which("fix-my-claw")
    if current:
        return str(Path(current).resolve())
    raise FileNotFoundError("fix-my-claw not found in PATH")


def _launchd_path_env() -> str:
    return os.environ.get("PATH", "") or "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def _expected_launchd_config_path(config_path: str | None) -> str | None:
    if config_path is None:
        return None
    return str(_as_path(config_path))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_fix_my_claw_to_stable_service_path(
    *,
    _get_fix_my_claw_path_impl: Callable[[], str] | None = None,
    _get_launchd_service_binary_path_impl: Callable[[], Path] | None = None,
) -> tuple[Path, bool]:
    get_fix_my_claw_path = _get_fix_my_claw_path_impl or _get_fix_my_claw_path
    get_launchd_service_binary_path = (
        _get_launchd_service_binary_path_impl or _get_launchd_service_binary_path
    )
    source_path = Path(get_fix_my_claw_path()).resolve()
    target_path = get_launchd_service_binary_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    desired_mode = source_path.stat().st_mode & 0o777
    if desired_mode & 0o111 == 0:
        desired_mode |= 0o755
    if source_path == target_path:
        current_mode = target_path.stat().st_mode & 0o777
        if current_mode != desired_mode:
            target_path.chmod(desired_mode)
            return target_path, True
        return target_path, False

    needs_replace = not target_path.exists()
    if not needs_replace:
        if source_path.stat().st_size != target_path.stat().st_size:
            needs_replace = True
        else:
            needs_replace = _sha256_file(source_path) != _sha256_file(target_path)
    if not needs_replace:
        current_mode = target_path.stat().st_mode & 0o777
        if current_mode != desired_mode:
            target_path.chmod(desired_mode)
            return target_path, True
        return target_path, False

    tmp_path = target_path.parent / f".{target_path.name}.{os.getpid()}.tmp"
    shutil.copy2(source_path, tmp_path)
    tmp_path.chmod(desired_mode)
    tmp_path.replace(target_path)
    return target_path, True


def _generate_launchd_plist(
    cfg: "AppConfig",
    config_path: str,
    *,
    _get_launchd_label_impl: Callable[[], str] | None = None,
    _get_launchd_service_binary_path_impl: Callable[[], Path] | None = None,
) -> bytes:
    get_launchd_label = _get_launchd_label_impl or _get_launchd_label
    get_launchd_service_binary_path = (
        _get_launchd_service_binary_path_impl or _get_launchd_service_binary_path
    )
    state_dir = cfg.monitor.state_dir
    plist = {
        "Label": get_launchd_label(),
        "ProgramArguments": [
            str(get_launchd_service_binary_path()),
            "monitor",
            "--config",
            str(_as_path(config_path)),
        ],
        "EnvironmentVariables": {
            "PATH": _launchd_path_env(),
            "PYTHONUNBUFFERED": "1",
        },
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "WorkingDirectory": "/tmp",
        "StandardOutPath": str((state_dir / "monitor.stdout.log").resolve()),
        "StandardErrorPath": str((state_dir / "monitor.stderr.log").resolve()),
    }
    return plistlib.dumps(plist)


def _write_launchd_plist(
    cfg: "AppConfig",
    config_path: str,
    plist_path: Path,
    *,
    _generate_launchd_plist_impl: Callable[["AppConfig", str], bytes] | None = None,
) -> None:
    generate_launchd_plist = _generate_launchd_plist_impl or _generate_launchd_plist
    cfg.monitor.state_dir.mkdir(parents=True, exist_ok=True)
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_bytes(generate_launchd_plist(cfg, config_path))


def _launchctl_run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["launchctl", *args],
        check=check,
        capture_output=True,
        text=True,
    )


def _launchctl_result_indicates_missing_service(result: subprocess.CompletedProcess[str]) -> bool:
    text = "\n".join(part for part in (result.stdout, result.stderr) if part).lower()
    return "no such process" in text or "could not find service" in text


def _launchd_metadata_from_program_arguments(arguments: list[str]) -> dict[str, str | None]:
    program_path = arguments[0] if arguments else None
    config_path = None
    for index, value in enumerate(arguments):
        if value == "--config" and index + 1 < len(arguments):
            config_path = str(_as_path(arguments[index + 1]))
            break
    return {
        "program_path": program_path,
        "config_path": config_path,
    }


def _read_launchd_plist_metadata(plist_path: Path) -> dict[str, str | None]:
    try:
        plist = plistlib.loads(plist_path.read_bytes())
    except (FileNotFoundError, OSError, plistlib.InvalidFileException):
        return {"program_path": None, "config_path": None}

    program_arguments = plist.get("ProgramArguments")
    if not isinstance(program_arguments, list) or not all(isinstance(arg, str) for arg in program_arguments):
        return {"program_path": None, "config_path": None}
    return _launchd_metadata_from_program_arguments(program_arguments)


def _parse_launchctl_print_metadata(output: str) -> dict[str, str | None]:
    program_path = None
    arguments: list[str] = []
    in_arguments = False

    for raw_line in output.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped.startswith("program = "):
            candidate = stripped.removeprefix("program = ").strip()
            program_path = None if candidate in {"", "(null)"} else candidate
            continue
        if stripped == "arguments = {":
            in_arguments = True
            continue
        if in_arguments:
            if stripped == "}":
                in_arguments = False
                continue
            if stripped:
                arguments.append(stripped)

    metadata = _launchd_metadata_from_program_arguments(arguments) if arguments else {
        "program_path": None,
        "config_path": None,
    }
    if program_path is not None:
        metadata["program_path"] = program_path
    return metadata


def _raise_launchctl_error(result: subprocess.CompletedProcess[str]) -> None:
    raise subprocess.CalledProcessError(
        result.returncode, result.args, output=result.stdout, stderr=result.stderr
    )


def _inspect_loaded_launchd_service(
    *,
    _launchctl_run_impl: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    _get_launchd_job_target_impl: Callable[[], str] | None = None,
) -> tuple[bool, dict[str, str | None] | None]:
    launchctl_run = _launchctl_run_impl or _launchctl_run
    get_launchd_job_target = _get_launchd_job_target_impl or _get_launchd_job_target
    result = launchctl_run("print", get_launchd_job_target(), check=False)
    if result.returncode == 0:
        return True, _parse_launchctl_print_metadata(result.stdout)
    if _launchctl_result_indicates_missing_service(result):
        return False, None
    _raise_launchctl_error(result)


def _launchd_service_loaded(
    *,
    _launchctl_run_impl: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    _get_launchd_job_target_impl: Callable[[], str] | None = None,
) -> bool:
    loaded, _ = _inspect_loaded_launchd_service(
        _launchctl_run_impl=_launchctl_run_impl,
        _get_launchd_job_target_impl=_get_launchd_job_target_impl,
    )
    return loaded


def _ensure_launchd_service_unloaded(
    plist_path: Path,
    *,
    _launchd_service_loaded_impl: Callable[[], bool] | None = None,
    _launchctl_run_impl: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    _get_launchd_domain_impl: Callable[[], str] | None = None,
    _get_launchd_job_target_impl: Callable[[], str] | None = None,
) -> None:
    """Unload launchd service if it is currently loaded."""
    launchctl_run = _launchctl_run_impl or _launchctl_run
    get_launchd_domain = _get_launchd_domain_impl or _get_launchd_domain
    get_launchd_job_target = _get_launchd_job_target_impl or _get_launchd_job_target
    launchd_service_loaded = _launchd_service_loaded_impl or (
        lambda: _launchd_service_loaded(
            _launchctl_run_impl=launchctl_run,
            _get_launchd_job_target_impl=get_launchd_job_target,
        )
    )
    if not launchd_service_loaded():
        return

    result = launchctl_run("bootout", get_launchd_domain(), str(plist_path), check=False)
    if result.returncode != 0:
        result = launchctl_run("bootout", get_launchd_job_target(), check=False)
    if result.returncode == 0 or _launchctl_result_indicates_missing_service(result):
        return
    _raise_launchctl_error(result)


def _collect_launchd_service_status(
    *,
    config_path: str | None,
    ignore_launchctl_errors: bool = False,
    _get_launchd_plist_path_impl: Callable[[], Path] | None = None,
    _launchctl_run_impl: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    _get_launchd_job_target_impl: Callable[[], str] | None = None,
    _get_launchd_service_binary_path_impl: Callable[[], Path] | None = None,
    _get_launchd_label_impl: Callable[[], str] | None = None,
    _get_launchd_domain_impl: Callable[[], str] | None = None,
) -> dict[str, object]:
    get_launchd_plist_path = _get_launchd_plist_path_impl or _get_launchd_plist_path
    get_launchd_service_binary_path = (
        _get_launchd_service_binary_path_impl or _get_launchd_service_binary_path
    )
    get_launchd_label = _get_launchd_label_impl or _get_launchd_label
    get_launchd_domain = _get_launchd_domain_impl or _get_launchd_domain
    plist_path = get_launchd_plist_path()
    installed = plist_path.exists()
    running = False
    loaded_metadata: dict[str, str | None] | None = None
    plist_metadata = {"program_path": None, "config_path": None}

    if installed:
        try:
            running, loaded_metadata = _inspect_loaded_launchd_service(
                _launchctl_run_impl=_launchctl_run_impl,
                _get_launchd_job_target_impl=_get_launchd_job_target_impl,
            )
        except subprocess.CalledProcessError:
            if not ignore_launchctl_errors:
                raise
            running = False
            loaded_metadata = None
        plist_metadata = _read_launchd_plist_metadata(plist_path)

    program_path = (loaded_metadata or {}).get("program_path") or plist_metadata["program_path"]
    actual_config_path = (loaded_metadata or {}).get("config_path") or plist_metadata["config_path"]
    expected_program_path = str(get_launchd_service_binary_path())
    expected_config_path = _expected_launchd_config_path(config_path)

    drifted = installed and program_path != expected_program_path
    if installed and expected_config_path is not None:
        drifted = drifted or actual_config_path != expected_config_path

    return build_service_status_payload(
        installed=installed,
        running=running,
        label=get_launchd_label(),
        plist_path=str(plist_path),
        domain=get_launchd_domain(),
        program_path=program_path,
        config_path=actual_config_path,
        expected_program_path=expected_program_path,
        expected_config_path=expected_config_path,
        drifted=drifted,
    )


def _emit_service_status(payload: dict[str, object], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False))
        return
    print(f"installed={'true' if payload['installed'] else 'false'}")
    print(f"running={'true' if payload['running'] else 'false'}")


def _restart_launchd_service(
    cfg: "AppConfig",
    config_path: str,
    plist_path: Path,
    *,
    _write_launchd_plist_impl: Callable[["AppConfig", str, Path], None] | None = None,
    _ensure_launchd_service_unloaded_impl: Callable[[Path], None] | None = None,
    _launchctl_run_impl: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    _get_launchd_domain_impl: Callable[[], str] | None = None,
    _get_launchd_job_target_impl: Callable[[], str] | None = None,
) -> None:
    write_launchd_plist = _write_launchd_plist_impl or _write_launchd_plist
    ensure_launchd_service_unloaded = (
        _ensure_launchd_service_unloaded_impl or _ensure_launchd_service_unloaded
    )
    launchctl_run = _launchctl_run_impl or _launchctl_run
    get_launchd_domain = _get_launchd_domain_impl or _get_launchd_domain
    get_launchd_job_target = _get_launchd_job_target_impl or _get_launchd_job_target
    write_launchd_plist(cfg, config_path, plist_path)
    ensure_launchd_service_unloaded(plist_path)
    launchctl_run("bootstrap", get_launchd_domain(), str(plist_path))
    launchctl_run("enable", get_launchd_job_target())
    launchctl_run("kickstart", "-k", get_launchd_job_target())


def _service_reconcile_reasons(
    *,
    status_payload: dict[str, object],
    binary_updated: bool,
) -> list[str]:
    reasons: list[str] = []
    installed = bool(status_payload["installed"])
    if not installed:
        reasons.append("missing_plist")
    if installed and not bool(status_payload["running"]):
        reasons.append("not_running")
    if installed and status_payload.get("program_path") != status_payload.get("expected_program_path"):
        reasons.append("program_path")
    expected_config_path = status_payload.get("expected_config_path")
    if installed and expected_config_path is not None and status_payload.get("config_path") != expected_config_path:
        reasons.append("config_path")
    if binary_updated:
        reasons.append("binary_changed")
    return reasons


def _reconcile_launchd_service(
    cfg: "AppConfig",
    config_path: str,
    *,
    _collect_launchd_service_status_impl: Callable[..., dict[str, object]] | None = None,
    _copy_fix_my_claw_to_stable_service_path_impl: Callable[[], tuple[Path, bool]] | None = None,
    _service_reconcile_reasons_impl: Callable[..., list[str]] | None = None,
    _get_launchd_plist_path_impl: Callable[[], Path] | None = None,
    _restart_launchd_service_impl: Callable[["AppConfig", str, Path], None] | None = None,
) -> dict[str, object]:
    collect_launchd_service_status = (
        _collect_launchd_service_status_impl or _collect_launchd_service_status
    )
    copy_fix_my_claw_to_stable_service_path = (
        _copy_fix_my_claw_to_stable_service_path_impl or _copy_fix_my_claw_to_stable_service_path
    )
    service_reconcile_reasons = (
        _service_reconcile_reasons_impl or _service_reconcile_reasons
    )
    get_launchd_plist_path = _get_launchd_plist_path_impl or _get_launchd_plist_path
    restart_launchd_service = _restart_launchd_service_impl or _restart_launchd_service
    initial_status = collect_launchd_service_status(config_path=config_path)
    _, binary_updated = copy_fix_my_claw_to_stable_service_path()
    reasons = service_reconcile_reasons(
        status_payload=initial_status,
        binary_updated=binary_updated,
    )

    action = "noop"
    plist_path = get_launchd_plist_path()
    installed = bool(initial_status["installed"])
    running = bool(initial_status["running"])
    drifted = bool(initial_status["drifted"])

    if not installed:
        restart_launchd_service(cfg, config_path, plist_path)
        action = "installed"
    elif drifted or binary_updated:
        restart_launchd_service(cfg, config_path, plist_path)
        action = "updated"
    elif not running:
        restart_launchd_service(cfg, config_path, plist_path)
        action = "restarted"

    final_status = collect_launchd_service_status(config_path=config_path)
    return build_service_reconcile_payload(
        action=action,
        reasons=reasons,
        service=final_status,
    )


def cmd_service_install(
    args: argparse.Namespace,
    *,
    load_or_init_config_impl: Callable[..., "AppConfig"] = load_or_init_config,
    _service_platform_supported_impl: Callable[[], bool] | None = None,
    _get_launchd_plist_path_impl: callable | None = None,
    _copy_fix_my_claw_to_stable_service_path_impl: callable | None = None,
    _restart_launchd_service_impl: callable | None = None,
    _ensure_launchd_service_unloaded_impl: callable | None = None,
) -> int:
    """Install the launchd service."""
    service_platform_supported = _service_platform_supported_impl or _service_platform_supported
    if not service_platform_supported():
        print("service commands are supported on macOS only", file=sys.stderr)
        return 1
    
    _get_plist_path = _get_launchd_plist_path_impl or _get_launchd_plist_path
    _copy_binary = _copy_fix_my_claw_to_stable_service_path_impl or _copy_fix_my_claw_to_stable_service_path
    _restart_service = _restart_launchd_service_impl or _restart_launchd_service
    _unload_service = _ensure_launchd_service_unloaded_impl or _ensure_launchd_service_unloaded
    
    cfg = load_or_init_config_impl(args.config, init_if_missing=True)
    plist_path = _get_plist_path()
    if plist_path.exists():
        print(f"service already installed at {plist_path}", file=sys.stderr)
        return 1

    # Track what we've created so we can clean up on failure
    plist_created = False
    bootstrapped = False

    try:
        _copy_binary()
        plist_created = True
        _restart_service(cfg, args.config, plist_path)
        bootstrapped = True
    except (FileNotFoundError, OSError, subprocess.CalledProcessError) as exc:
        # Clean up on partial failure
        if bootstrapped:
            _unload_service(plist_path)
        if plist_created:
            try:
                plist_path.unlink(missing_ok=True)
            except Exception:
                pass
        print(f"error installing service: {exc}", file=sys.stderr)
        return 1
    print(str(plist_path))
    return 0


def cmd_service_uninstall(
    args: argparse.Namespace,
    *,
    _service_platform_supported_impl: Callable[[], bool] | None = None,
    _get_launchd_plist_path_impl: Callable[[], Path] | None = None,
    _ensure_launchd_service_unloaded_impl: Callable[[Path], None] | None = None,
) -> int:
    """Uninstall the launchd service."""
    service_platform_supported = _service_platform_supported_impl or _service_platform_supported
    get_launchd_plist_path = _get_launchd_plist_path_impl or _get_launchd_plist_path
    ensure_launchd_service_unloaded = (
        _ensure_launchd_service_unloaded_impl or _ensure_launchd_service_unloaded
    )
    if not service_platform_supported():
        print("service commands are supported on macOS only", file=sys.stderr)
        return 1
    plist_path = get_launchd_plist_path()
    if not plist_path.exists():
        print("service not installed")
        return 0
    try:
        ensure_launchd_service_unloaded(plist_path)
    except subprocess.CalledProcessError as exc:
        print(f"error stopping service: {exc.stderr.strip() if exc.stderr else exc}", file=sys.stderr)
        return 1
    try:
        plist_path.unlink(missing_ok=True)
    except OSError as exc:
        print(f"error removing plist: {exc}", file=sys.stderr)
        return 1
    print("service uninstalled")
    return 0


def cmd_service_start(
    args: argparse.Namespace,
    *,
    load_or_init_config_impl: Callable[..., "AppConfig"] = load_or_init_config,
    default_config_path: str,
    _service_platform_supported_impl: Callable[[], bool] | None = None,
    _get_launchd_plist_path_impl: Callable[[], Path] | None = None,
    _restart_launchd_service_impl: Callable[["AppConfig", str, Path], None] | None = None,
) -> int:
    """Start the launchd service."""
    service_platform_supported = _service_platform_supported_impl or _service_platform_supported
    get_launchd_plist_path = _get_launchd_plist_path_impl or _get_launchd_plist_path
    restart_launchd_service = _restart_launchd_service_impl or _restart_launchd_service
    if not service_platform_supported():
        print("service commands are supported on macOS only", file=sys.stderr)
        return 1
    config_path = getattr(args, "config", default_config_path)
    cfg = load_or_init_config_impl(config_path, init_if_missing=True)
    plist_path = get_launchd_plist_path()
    if not plist_path.exists():
        print("service not installed", file=sys.stderr)
        return 1
    try:
        restart_launchd_service(cfg, config_path, plist_path)
    except (OSError, subprocess.CalledProcessError) as exc:
        stderr = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) and exc.stderr else str(exc)
        print(f"error starting service: {stderr}", file=sys.stderr)
        return 1
    print("service started")
    return 0


def cmd_service_stop(
    args: argparse.Namespace,
    *,
    _service_platform_supported_impl: Callable[[], bool] | None = None,
    _get_launchd_plist_path_impl: Callable[[], Path] | None = None,
    _ensure_launchd_service_unloaded_impl: Callable[[Path], None] | None = None,
) -> int:
    """Stop the launchd service."""
    service_platform_supported = _service_platform_supported_impl or _service_platform_supported
    get_launchd_plist_path = _get_launchd_plist_path_impl or _get_launchd_plist_path
    ensure_launchd_service_unloaded = (
        _ensure_launchd_service_unloaded_impl or _ensure_launchd_service_unloaded
    )
    if not service_platform_supported():
        print("service commands are supported on macOS only", file=sys.stderr)
        return 1
    plist_path = get_launchd_plist_path()
    if not plist_path.exists():
        print("service not installed")
        return 0
    try:
        ensure_launchd_service_unloaded(plist_path)
    except subprocess.CalledProcessError as exc:
        print(f"error stopping service: {exc.stderr.strip() if exc.stderr else exc}", file=sys.stderr)
        return 1
    print("service stopped")
    return 0


def cmd_service_status(
    args: argparse.Namespace,
    *,
    default_config_path: str,
    _service_platform_supported_impl: Callable[[], bool] | None = None,
    _collect_launchd_service_status_impl: Callable[..., dict[str, object]] | None = None,
) -> int:
    """Show launchd service status."""
    service_platform_supported = _service_platform_supported_impl or _service_platform_supported
    collect_launchd_service_status = (
        _collect_launchd_service_status_impl or _collect_launchd_service_status
    )
    if not service_platform_supported():
        print("service commands are supported on macOS only", file=sys.stderr)
        return 1
    payload = collect_launchd_service_status(
        config_path=getattr(args, "config", default_config_path),
        ignore_launchctl_errors=True,
    )
    _emit_service_status(payload, as_json=args.json)
    return 0


def cmd_service_reconcile(
    args: argparse.Namespace,
    *,
    load_or_init_config_impl: Callable[..., "AppConfig"] = load_or_init_config,
    default_config_path: str,
    _service_platform_supported_impl: Callable[[], bool] | None = None,
    _reconcile_launchd_service_impl: Callable[["AppConfig", str], dict[str, object]] | None = None,
) -> int:
    """Align the launchd service plist, binary path, and loaded job."""
    service_platform_supported = _service_platform_supported_impl or _service_platform_supported
    reconcile_launchd_service = (
        _reconcile_launchd_service_impl or _reconcile_launchd_service
    )
    if not service_platform_supported():
        print("service commands are supported on macOS only", file=sys.stderr)
        return 1
    config_path = getattr(args, "config", default_config_path)
    cfg = load_or_init_config_impl(config_path, init_if_missing=True)
    try:
        payload = reconcile_launchd_service(cfg, config_path)
    except (FileNotFoundError, OSError, subprocess.CalledProcessError) as exc:
        stderr = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) and exc.stderr else str(exc)
        print(f"error reconciling service: {stderr}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(payload["action"])
    return 0
