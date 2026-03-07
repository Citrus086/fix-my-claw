from __future__ import annotations

import argparse
import json
import os
import plistlib
import shutil
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
from .repair import attempt_repair
from .shared import _as_path, setup_logging
from .state import FileLock, State, StateStore


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
    return {
        "enabled": current.enabled,
        "config_path": str(_as_path(config_path)),
        "config_exists": config_exists,
        "state_path": str(store.path),
        "last_ok_ts": current.last_ok_ts,
        "last_repair_ts": current.last_repair_ts,
        "last_ai_ts": current.last_ai_ts,
        "ai_attempts_day": current.ai_attempts_day,
        "ai_attempts_count": current.ai_attempts_count,
    }


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
        print(json.dumps(result.to_check_json(), ensure_ascii=False))
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


def cmd_repair(args: argparse.Namespace) -> int:
    cfg = _load_or_init_config(args.config, init_if_missing=False)
    setup_logging(cfg)

    def _run() -> int:
        store = StateStore(cfg.monitor.state_dir)
        result = attempt_repair(cfg, store, force=args.force, reason=None)
        if args.json:
            print(json.dumps(result.to_json(), ensure_ascii=False))
        return 0 if result.fixed else 1

    return _with_single_instance(cfg, _run)


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
        print(json.dumps(_config_to_dict(cfg), ensure_ascii=False, indent=2))
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
    return sys.platform == "darwin"


def _get_launchd_label() -> str:
    return "com.fix-my-claw.monitor"


def _get_launchd_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{_get_launchd_label()}.plist"


def _get_launchd_domain() -> str:
    return f"gui/{os.getuid()}"


def _get_fix_my_claw_path() -> str:
    current = shutil.which("fix-my-claw")
    if current:
        return str(Path(current).resolve())
    argv0 = Path(sys.argv[0]).expanduser()
    if argv0.name == "fix-my-claw" and argv0.exists():
        return str(argv0.resolve())
    raise FileNotFoundError("fix-my-claw not found in PATH")


def _launchd_path_env() -> str:
    return os.environ.get("PATH", "") or "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def _generate_launchd_plist(cfg: AppConfig, config_path: str) -> bytes:
    state_dir = cfg.monitor.state_dir
    plist = {
        "Label": _get_launchd_label(),
        "ProgramArguments": [
            _get_fix_my_claw_path(),
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


def _launchctl_run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["launchctl", *args],
        check=check,
        capture_output=True,
        text=True,
    )


def _bootout_launchd_service(plist_path: Path) -> None:
    domain = _get_launchd_domain()
    label = _get_launchd_label()
    _launchctl_run("bootout", domain, str(plist_path), check=False)
    _launchctl_run("bootout", f"{domain}/{label}", check=False)


def _service_status_payload(*, installed: bool, running: bool) -> dict[str, object]:
    return {
        "installed": installed,
        "running": running,
        "label": _get_launchd_label(),
        "plist_path": str(_get_launchd_plist_path()),
        "domain": _get_launchd_domain(),
    }


def _emit_service_status(*, installed: bool, running: bool, as_json: bool) -> None:
    payload = _service_status_payload(installed=installed, running=running)
    if as_json:
        print(json.dumps(payload, ensure_ascii=False))
        return
    print(f"installed={'true' if installed else 'false'}")
    print(f"running={'true' if running else 'false'}")


def cmd_service_install(args: argparse.Namespace) -> int:
    if not _service_platform_supported():
        print("service commands are supported on macOS only", file=sys.stderr)
        return 1
    cfg = _load_or_init_config(args.config, init_if_missing=True)
    plist_path = _get_launchd_plist_path()
    if plist_path.exists():
        print(f"service already installed at {plist_path}", file=sys.stderr)
        return 1

    # Track what we've created so we can clean up on failure
    plist_created = False
    bootstrapped = False

    try:
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        cfg.monitor.state_dir.mkdir(parents=True, exist_ok=True)
        plist_path.write_bytes(_generate_launchd_plist(cfg, args.config))
        plist_created = True
        _launchctl_run("bootstrap", _get_launchd_domain(), str(plist_path))
        bootstrapped = True
        _launchctl_run("enable", f"{_get_launchd_domain()}/{_get_launchd_label()}")
        _launchctl_run("kickstart", "-k", f"{_get_launchd_domain()}/{_get_launchd_label()}")
    except (FileNotFoundError, OSError, subprocess.CalledProcessError) as exc:
        # Clean up on partial failure
        if bootstrapped:
            _bootout_launchd_service(plist_path)
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
        _bootout_launchd_service(plist_path)
        plist_path.unlink(missing_ok=True)
    except OSError as exc:
        print(f"error uninstalling service: {exc}", file=sys.stderr)
        return 1
    print("service uninstalled")
    return 0


def cmd_service_start(args: argparse.Namespace) -> int:
    if not _service_platform_supported():
        print("service commands are supported on macOS only", file=sys.stderr)
        return 1
    plist_path = _get_launchd_plist_path()
    if not plist_path.exists():
        print("service not installed", file=sys.stderr)
        return 1
    try:
        _bootout_launchd_service(plist_path)
        _launchctl_run("bootstrap", _get_launchd_domain(), str(plist_path))
        _launchctl_run("enable", f"{_get_launchd_domain()}/{_get_launchd_label()}")
        _launchctl_run("kickstart", "-k", f"{_get_launchd_domain()}/{_get_launchd_label()}")
    except subprocess.CalledProcessError as exc:
        print(f"error starting service: {exc.stderr.strip() or exc}", file=sys.stderr)
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
    _bootout_launchd_service(plist_path)
    print("service stopped")
    return 0


def cmd_service_status(args: argparse.Namespace) -> int:
    if not _service_platform_supported():
        print("service commands are supported on macOS only", file=sys.stderr)
        return 1
    plist_path = _get_launchd_plist_path()
    installed = plist_path.exists()
    running = False
    if installed:
        result = _launchctl_run("print", f"{_get_launchd_domain()}/{_get_launchd_label()}", check=False)
        running = result.returncode == 0
    _emit_service_status(installed=installed, running=running, as_json=args.json)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fix-my-claw")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    parser_up = subparsers.add_parser("up", help="One-command start: init default config (if missing) then monitor.")
    _add_config_arg(parser_up)
    parser_up.set_defaults(func=cmd_up)

    parser_init = subparsers.add_parser("init", help="Write default config (prints config path).")
    _add_config_arg(parser_init)
    parser_init.add_argument("--force", action="store_true", help="Overwrite config if it already exists.")
    parser_init.set_defaults(func=cmd_init)

    parser_check = subparsers.add_parser("check", help="Probe OpenClaw health/status once.")
    _add_config_arg(parser_check)
    parser_check.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser_check.set_defaults(func=cmd_check)

    parser_status = subparsers.add_parser(
        "status",
        help="Show whether monitoring is enabled plus persisted monitor state.",
    )
    _add_config_arg(parser_status)
    parser_status.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser_status.set_defaults(func=cmd_status)

    parser_start = subparsers.add_parser(
        "start",
        help="Enable monitoring so an active monitor loop resumes auto-heal.",
    )
    _add_config_arg(parser_start)
    parser_start.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser_start.set_defaults(func=cmd_start)

    parser_stop = subparsers.add_parser(
        "stop",
        help="Disable monitoring so monitor loops idle instead of probing/repairing.",
    )
    _add_config_arg(parser_stop)
    parser_stop.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser_stop.set_defaults(func=cmd_stop)

    parser_repair = subparsers.add_parser("repair", help="Run official repair (and optional AI repair) once if unhealthy.")
    _add_config_arg(parser_repair)
    parser_repair.add_argument("--force", action="store_true", help="Ignore cooldown and attempt repair.")
    parser_repair.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser_repair.set_defaults(func=cmd_repair)

    parser_monitor = subparsers.add_parser("monitor", help="Run 24/7 monitor loop (requires config to exist).")
    _add_config_arg(parser_monitor)
    parser_monitor.set_defaults(func=cmd_monitor)

    parser_config = subparsers.add_parser("config", help="Manage fix-my-claw configuration.")
    config_subparsers = parser_config.add_subparsers(dest="config_cmd", required=True)

    parser_config_show = config_subparsers.add_parser("show", help="Show current configuration.")
    _add_config_arg(parser_config_show)
    parser_config_show.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser_config_show.set_defaults(func=cmd_config_show)

    parser_config_set = config_subparsers.add_parser("set", help="Replace configuration from stdin JSON.")
    _add_config_arg(parser_config_set)
    parser_config_set.add_argument("--json", action="store_true", help="Read JSON input from stdin.")
    parser_config_set.set_defaults(func=cmd_config_set)

    parser_service = subparsers.add_parser("service", help="Manage the macOS launchd monitor service.")
    service_subparsers = parser_service.add_subparsers(dest="service_cmd", required=True)

    parser_service_install = service_subparsers.add_parser("install", help="Install the launchd service.")
    _add_config_arg(parser_service_install)
    parser_service_install.set_defaults(func=cmd_service_install)

    parser_service_uninstall = service_subparsers.add_parser("uninstall", help="Uninstall the launchd service.")
    parser_service_uninstall.set_defaults(func=cmd_service_uninstall)

    parser_service_start = service_subparsers.add_parser("start", help="Start the launchd service.")
    parser_service_start.set_defaults(func=cmd_service_start)

    parser_service_stop = service_subparsers.add_parser("stop", help="Stop the launchd service.")
    parser_service_stop.set_defaults(func=cmd_service_stop)

    parser_service_status = service_subparsers.add_parser("status", help="Show launchd service status.")
    parser_service_status.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser_service_status.set_defaults(func=cmd_service_status)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    code = args.func(args)
    raise SystemExit(code)


__all__ = [
    "_add_config_arg",
    "_load_or_init_config",
    "build_parser",
    "cmd_check",
    "cmd_config_set",
    "cmd_config_show",
    "cmd_init",
    "cmd_monitor",
    "cmd_repair",
    "cmd_service_install",
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
