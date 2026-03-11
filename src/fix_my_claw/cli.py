"""CLI entry point for fix-my-claw.

This module is intentionally a thin facade that preserves the legacy patch
surface used by tests and other callers, while delegating heavy helpers and
parser construction to ``cli_commands`` submodules.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Callable

from .config import (
    DEFAULT_CONFIG_PATH,
    AppConfig,
    _config_to_dict,
    _dict_to_config,
    load_config,
    write_default_config,
    _write_toml,
)
from .monitor import monitor_loop, run_check
from .protocol import (
    build_check_payload,
    build_config_payload,
    build_repair_payload,
    build_service_reconcile_payload,
    build_status_payload,
)
from .repair import attempt_repair
from .shared import _as_path, setup_logging
from .state import FileLock, State, StateStore

from .cli_commands.parser import build_parser as _build_parser
from .cli_commands.service import (
    _collect_launchd_service_status as _collect_launchd_service_status_impl,
    _copy_fix_my_claw_to_stable_service_path as _copy_fix_my_claw_to_stable_service_path_impl,
    _ensure_launchd_service_unloaded as _ensure_launchd_service_unloaded_impl,
    _generate_launchd_plist as _generate_launchd_plist_impl,
    _get_fix_my_claw_path as _get_fix_my_claw_path_impl,
    _get_launchd_domain as _get_launchd_domain_impl,
    _get_launchd_job_target as _get_launchd_job_target_impl,
    _get_launchd_label as _get_launchd_label_impl,
    _get_launchd_plist_path as _get_launchd_plist_path_impl,
    _get_launchd_service_binary_path as _get_launchd_service_binary_path_impl,
    _launchctl_run as _launchctl_run_impl,
    _launchd_service_loaded as _launchd_service_loaded_impl,
    _restart_launchd_service as _restart_launchd_service_impl,
    _service_platform_supported as _service_platform_supported_impl,
    _service_reconcile_reasons as _service_reconcile_reasons_impl,
)


def _add_config_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to TOML config file (default: {DEFAULT_CONFIG_PATH}).",
    )


def _load_or_init_config(path: str, *, init_if_missing: bool) -> AppConfig:
    config_path = _as_path(path)
    if not config_path.exists():
        if init_if_missing:
            write_default_config(str(config_path), overwrite=False)
        else:
            raise FileNotFoundError(
                f"config not found: {config_path} (run `fix-my-claw init` or `fix-my-claw up`)"
            )
    return load_config(str(config_path))


def _load_config_or_default(path: str) -> tuple[AppConfig, bool]:
    config_path = _as_path(path)
    if config_path.exists():
        return load_config(str(config_path)), True
    return AppConfig(), False


def _state_payload(store: StateStore, *, config_path: str, config_exists: bool, state: State | None = None) -> dict[str, object]:
    current = state or store.load()
    return build_status_payload(
        enabled=current.enabled,
        config_path=str(_as_path(config_path)),
        config_exists=config_exists,
        state_path=str(store.path),
        last_ok_ts=current.last_ok_ts,
        last_repair_ts=current.last_repair_ts,
        last_ai_ts=current.last_ai_ts,
        ai_attempts_day=current.ai_attempts_day,
        ai_attempts_count=current.ai_attempts_count,
    )


def _emit_state_payload(payload: dict[str, object], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False))
        return
    print(f"enabled: {payload['enabled']}")
    print(f"config_path: {payload['config_path']}")
    print(f"config_exists: {payload['config_exists']}")
    print(f"state_path: {payload['state_path']}")


def cmd_init(args: argparse.Namespace) -> int:
    config_path = write_default_config(args.config, overwrite=args.force)
    print(str(config_path))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    cfg = _load_or_init_config(args.config, init_if_missing=False)
    setup_logging(cfg)
    store = StateStore(cfg.monitor.state_dir)
    result = run_check(cfg, store)
    if args.json:
        print(json.dumps(build_check_payload(result.to_check_json()), ensure_ascii=False))
    return 0 if result.effective_healthy else 1


def _with_single_instance(cfg: AppConfig, action: Callable[[], int]) -> int:
    lock = FileLock(cfg.monitor.state_dir / "fix-my-claw.lock")
    if not lock.acquire(timeout_seconds=0):
        print("another fix-my-claw instance is running", file=sys.stderr)
        return 2
    try:
        return action()
    finally:
        lock.release()


def _run_repair_once(args: argparse.Namespace, *, reason: str | None) -> int:
    cfg = _load_or_init_config(args.config, init_if_missing=False)
    setup_logging(cfg)

    def _run() -> int:
        store = StateStore(cfg.monitor.state_dir)
        result = attempt_repair(
            cfg,
            store,
            force=args.force,
            reason=reason,
        )
        if args.json:
            print(json.dumps(build_repair_payload(result.to_json()), ensure_ascii=False))
        return 0 if result.fixed else 1

    return _with_single_instance(cfg, _run)


def cmd_repair(args: argparse.Namespace) -> int:
    return _run_repair_once(args, reason="manual_cli")


def cmd_auto_repair(args: argparse.Namespace) -> int:
    return _run_repair_once(args, reason=None)


def cmd_monitor(args: argparse.Namespace) -> int:
    cfg = _load_or_init_config(args.config, init_if_missing=False)
    setup_logging(cfg)

    def _run() -> int:
        store = StateStore(cfg.monitor.state_dir)
        monitor_loop(cfg, store)
        return 0

    return _with_single_instance(cfg, _run)


def cmd_up(args: argparse.Namespace) -> int:
    cfg = _load_or_init_config(args.config, init_if_missing=True)
    setup_logging(cfg)

    def _run() -> int:
        store = StateStore(cfg.monitor.state_dir)
        store.set_enabled(True)
        monitor_loop(cfg, store)
        return 0

    return _with_single_instance(cfg, _run)


def cmd_start(args: argparse.Namespace) -> int:
    cfg = _load_or_init_config(args.config, init_if_missing=True)
    setup_logging(cfg)
    store = StateStore(cfg.monitor.state_dir)
    state = store.set_enabled(True)
    _emit_state_payload(
        _state_payload(store, config_path=args.config, config_exists=True, state=state),
        as_json=args.json,
    )
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    cfg = _load_or_init_config(args.config, init_if_missing=True)
    setup_logging(cfg)
    store = StateStore(cfg.monitor.state_dir)
    state = store.set_enabled(False)
    _emit_state_payload(
        _state_payload(store, config_path=args.config, config_exists=True, state=state),
        as_json=args.json,
    )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    cfg, config_exists = _load_config_or_default(args.config)
    if config_exists:
        setup_logging(cfg)
    store = StateStore(cfg.monitor.state_dir)
    _emit_state_payload(
        _state_payload(store, config_path=args.config, config_exists=config_exists),
        as_json=args.json,
    )
    return 0


def cmd_config_show(args: argparse.Namespace) -> int:
    cfg = _load_or_init_config(args.config, init_if_missing=False)
    if args.json:
        print(json.dumps(build_config_payload(_config_to_dict(cfg)), ensure_ascii=False, indent=2))
        return 0
    print("Current configuration:")
    print(f"monitor.interval_seconds={cfg.monitor.interval_seconds}")
    print(f"repair.enabled={cfg.repair.enabled}")
    print(f"ai.enabled={cfg.ai.enabled}")
    return 0


def cmd_config_set(args: argparse.Namespace) -> int:
    if not args.json:
        print("config set requires --json and JSON input on stdin", file=sys.stderr)
        return 1
    try:
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError as exc:
        print(f"error parsing JSON: {exc}", file=sys.stderr)
        return 1

    try:
        cfg = _dict_to_config(payload)
    except (TypeError, ValueError) as exc:
        print(f"error validating configuration: {exc}", file=sys.stderr)
        return 1

    config_path = _as_path(args.config)
    normalized = _config_to_dict(cfg)
    try:
        _write_toml(config_path, normalized)
    except Exception as exc:
        print(f"error writing configuration: {exc}", file=sys.stderr)
        return 1
    print(str(config_path))
    return 0


def _service_platform_supported() -> bool:
    return _service_platform_supported_impl()


def _get_launchd_label() -> str:
    return _get_launchd_label_impl()


def _get_launchd_plist_path() -> Path:
    return _get_launchd_plist_path_impl()


def _get_launchd_domain() -> str:
    return _get_launchd_domain_impl()


def _get_launchd_job_target() -> str:
    return _get_launchd_job_target_impl()


def _get_launchd_service_binary_path() -> Path:
    return _get_launchd_service_binary_path_impl()


def _get_fix_my_claw_path() -> str:
    return _get_fix_my_claw_path_impl()


def _launchctl_run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return _launchctl_run_impl(*args, check=check)


def _generate_launchd_plist(cfg: AppConfig, config_path: str) -> bytes:
    import fix_my_claw.cli_commands.service as _service_module

    original = _service_module._get_launchd_service_binary_path
    try:
        _service_module._get_launchd_service_binary_path = _get_launchd_service_binary_path
        return _generate_launchd_plist_impl(cfg, config_path)
    finally:
        _service_module._get_launchd_service_binary_path = original


def _copy_fix_my_claw_to_stable_service_path() -> tuple[Path, bool]:
    import fix_my_claw.cli_commands.service as _service_module

    original_get_fix_my_claw_path = _service_module._get_fix_my_claw_path
    original_get_launchd_service_binary_path = _service_module._get_launchd_service_binary_path
    try:
        _service_module._get_fix_my_claw_path = _get_fix_my_claw_path
        _service_module._get_launchd_service_binary_path = _get_launchd_service_binary_path
        return _copy_fix_my_claw_to_stable_service_path_impl()
    finally:
        _service_module._get_fix_my_claw_path = original_get_fix_my_claw_path
        _service_module._get_launchd_service_binary_path = original_get_launchd_service_binary_path


def _launchd_service_loaded() -> bool:
    import fix_my_claw.cli_commands.service as _service_module

    original = _service_module._launchctl_run
    try:
        _service_module._launchctl_run = _launchctl_run
        return _launchd_service_loaded_impl()
    finally:
        _service_module._launchctl_run = original


def _ensure_launchd_service_unloaded(plist_path: Path) -> None:
    import fix_my_claw.cli_commands.service as _service_module

    original = _service_module._launchctl_run
    try:
        _service_module._launchctl_run = _launchctl_run
        _ensure_launchd_service_unloaded_impl(plist_path)
    finally:
        _service_module._launchctl_run = original


def _collect_launchd_service_status(
    *,
    config_path: str | None,
    ignore_launchctl_errors: bool = False,
) -> dict[str, object]:
    import fix_my_claw.cli_commands.service as _service_module

    original_get_launchd_plist_path = _service_module._get_launchd_plist_path
    original_launchctl_run = _service_module._launchctl_run
    original_get_launchd_service_binary_path = _service_module._get_launchd_service_binary_path
    try:
        _service_module._get_launchd_plist_path = _get_launchd_plist_path
        _service_module._launchctl_run = _launchctl_run
        _service_module._get_launchd_service_binary_path = _get_launchd_service_binary_path
        return _collect_launchd_service_status_impl(
            config_path=config_path,
            ignore_launchctl_errors=ignore_launchctl_errors,
        )
    finally:
        _service_module._get_launchd_plist_path = original_get_launchd_plist_path
        _service_module._launchctl_run = original_launchctl_run
        _service_module._get_launchd_service_binary_path = original_get_launchd_service_binary_path


def _restart_launchd_service(cfg: AppConfig, config_path: str, plist_path: Path) -> None:
    import fix_my_claw.cli_commands.service as _service_module

    original_generate_launchd_plist = _service_module._generate_launchd_plist
    original_ensure_launchd_service_unloaded = _service_module._ensure_launchd_service_unloaded
    original_launchctl_run = _service_module._launchctl_run
    try:
        _service_module._generate_launchd_plist = _generate_launchd_plist
        _service_module._ensure_launchd_service_unloaded = _ensure_launchd_service_unloaded
        _service_module._launchctl_run = _launchctl_run
        _restart_launchd_service_impl(cfg, config_path, plist_path)
    finally:
        _service_module._generate_launchd_plist = original_generate_launchd_plist
        _service_module._ensure_launchd_service_unloaded = original_ensure_launchd_service_unloaded
        _service_module._launchctl_run = original_launchctl_run


def _service_reconcile_reasons(
    *,
    status_payload: dict[str, object],
    binary_updated: bool,
) -> list[str]:
    return _service_reconcile_reasons_impl(
        status_payload=status_payload,
        binary_updated=binary_updated,
    )


def _reconcile_launchd_service(cfg: AppConfig, config_path: str) -> dict[str, object]:
    initial_status = _collect_launchd_service_status(config_path=config_path)
    _, binary_updated = _copy_fix_my_claw_to_stable_service_path()
    reasons = _service_reconcile_reasons(
        status_payload=initial_status,
        binary_updated=binary_updated,
    )

    action = "noop"
    plist_path = _get_launchd_plist_path()
    installed = bool(initial_status["installed"])
    running = bool(initial_status["running"])
    drifted = bool(initial_status["drifted"])

    if not installed:
        _restart_launchd_service(cfg, config_path, plist_path)
        action = "installed"
    elif drifted or binary_updated:
        _restart_launchd_service(cfg, config_path, plist_path)
        action = "updated"
    elif not running:
        _restart_launchd_service(cfg, config_path, plist_path)
        action = "restarted"

    final_status = _collect_launchd_service_status(config_path=config_path)
    return build_service_reconcile_payload(
        action=action,
        reasons=reasons,
        service=final_status,
    )


def _emit_service_status(payload: dict[str, object], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False))
        return
    print(f"installed={'true' if payload['installed'] else 'false'}")
    print(f"running={'true' if payload['running'] else 'false'}")


def cmd_service_install(args: argparse.Namespace) -> int:
    if not _service_platform_supported():
        print("service commands are supported on macOS only", file=sys.stderr)
        return 1
    cfg = _load_or_init_config(args.config, init_if_missing=True)
    plist_path = _get_launchd_plist_path()
    if plist_path.exists():
        print(f"service already installed at {plist_path}", file=sys.stderr)
        return 1

    plist_created = False
    bootstrapped = False

    try:
        _copy_fix_my_claw_to_stable_service_path()
        plist_created = True
        _restart_launchd_service(cfg, args.config, plist_path)
        bootstrapped = True
    except (FileNotFoundError, OSError, subprocess.CalledProcessError) as exc:
        if bootstrapped:
            _ensure_launchd_service_unloaded(plist_path)
        if plist_created:
            try:
                plist_path.unlink(missing_ok=True)
            except Exception:
                pass
        print(f"error installing service: {exc}", file=sys.stderr)
        return 1
    print(str(plist_path))
    return 0


def cmd_service_uninstall(args: argparse.Namespace) -> int:
    if not _service_platform_supported():
        print("service commands are supported on macOS only", file=sys.stderr)
        return 1
    plist_path = _get_launchd_plist_path()
    if not plist_path.exists():
        print("service not installed")
        return 0
    try:
        _ensure_launchd_service_unloaded(plist_path)
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


def cmd_service_start(args: argparse.Namespace) -> int:
    if not _service_platform_supported():
        print("service commands are supported on macOS only", file=sys.stderr)
        return 1
    config_path = getattr(args, "config", DEFAULT_CONFIG_PATH)
    cfg = _load_or_init_config(config_path, init_if_missing=True)
    plist_path = _get_launchd_plist_path()
    if not plist_path.exists():
        print("service not installed", file=sys.stderr)
        return 1
    try:
        cfg.monitor.state_dir.mkdir(parents=True, exist_ok=True)
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        plist_path.write_bytes(_generate_launchd_plist(cfg, config_path))
        _ensure_launchd_service_unloaded(plist_path)
        _launchctl_run("bootstrap", _get_launchd_domain(), str(plist_path))
        _launchctl_run("enable", _get_launchd_job_target())
        _launchctl_run("kickstart", "-k", _get_launchd_job_target())
    except (OSError, subprocess.CalledProcessError) as exc:
        stderr = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) and exc.stderr else str(exc)
        print(f"error starting service: {stderr}", file=sys.stderr)
        return 1
    print("service started")
    return 0


def cmd_service_stop(args: argparse.Namespace) -> int:
    if not _service_platform_supported():
        print("service commands are supported on macOS only", file=sys.stderr)
        return 1
    plist_path = _get_launchd_plist_path()
    if not plist_path.exists():
        print("service not installed")
        return 0
    try:
        _ensure_launchd_service_unloaded(plist_path)
    except subprocess.CalledProcessError as exc:
        print(f"error stopping service: {exc.stderr.strip() if exc.stderr else exc}", file=sys.stderr)
        return 1
    print("service stopped")
    return 0


def cmd_service_status(args: argparse.Namespace) -> int:
    if not _service_platform_supported():
        print("service commands are supported on macOS only", file=sys.stderr)
        return 1
    payload = _collect_launchd_service_status(
        config_path=getattr(args, "config", DEFAULT_CONFIG_PATH),
        ignore_launchctl_errors=True,
    )
    _emit_service_status(payload, as_json=args.json)
    return 0


def cmd_service_reconcile(args: argparse.Namespace) -> int:
    if not _service_platform_supported():
        print("service commands are supported on macOS only", file=sys.stderr)
        return 1
    config_path = getattr(args, "config", DEFAULT_CONFIG_PATH)
    cfg = _load_or_init_config(config_path, init_if_missing=True)
    try:
        payload = _reconcile_launchd_service(cfg, config_path)
    except (FileNotFoundError, OSError, subprocess.CalledProcessError) as exc:
        stderr = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) and exc.stderr else str(exc)
        print(f"error reconciling service: {stderr}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(payload["action"])
    return 0


def build_parser() -> argparse.ArgumentParser:
    return _build_parser(
        default_config_path=DEFAULT_CONFIG_PATH,
        cmd_init=cmd_init,
        cmd_check=cmd_check,
        cmd_status=cmd_status,
        cmd_start=cmd_start,
        cmd_stop=cmd_stop,
        cmd_repair=cmd_repair,
        cmd_auto_repair=cmd_auto_repair,
        cmd_monitor=cmd_monitor,
        cmd_up=cmd_up,
        cmd_config_show=cmd_config_show,
        cmd_config_set=cmd_config_set,
        cmd_service_install=cmd_service_install,
        cmd_service_uninstall=cmd_service_uninstall,
        cmd_service_start=cmd_service_start,
        cmd_service_stop=cmd_service_stop,
        cmd_service_status=cmd_service_status,
        cmd_service_reconcile=cmd_service_reconcile,
    )


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    code = args.func(args)
    raise SystemExit(code)


__all__ = [
    "_add_config_arg",
    "_load_or_init_config",
    "_load_config_or_default",
    "_with_single_instance",
    "_get_fix_my_claw_path",
    "_service_platform_supported",
    "_get_launchd_label",
    "_get_launchd_domain",
    "_get_launchd_job_target",
    "_get_launchd_plist_path",
    "_get_launchd_service_binary_path",
    "_launchctl_run",
    "_launchd_service_loaded",
    "_ensure_launchd_service_unloaded",
    "_generate_launchd_plist",
    "_copy_fix_my_claw_to_stable_service_path",
    "_collect_launchd_service_status",
    "_restart_launchd_service",
    "_reconcile_launchd_service",
    "build_parser",
    "cmd_auto_repair",
    "cmd_check",
    "cmd_config_set",
    "cmd_config_show",
    "cmd_init",
    "cmd_monitor",
    "cmd_repair",
    "cmd_service_install",
    "cmd_service_reconcile",
    "cmd_service_start",
    "cmd_service_status",
    "cmd_service_stop",
    "cmd_service_uninstall",
    "cmd_start",
    "cmd_status",
    "cmd_stop",
    "cmd_up",
    "main",
]
