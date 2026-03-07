from __future__ import annotations

import argparse
import json
import sys
from typing import Callable

from .config import DEFAULT_CONFIG_PATH, AppConfig, load_config, write_default_config
from .monitor import monitor_loop, run_check
from .repair import attempt_repair
from .shared import _as_path, setup_logging
from .state import DESIRED_STATE_RUNNING, DESIRED_STATE_STOPPED, FileLock, State, StateStore


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
        "desired_state": current.desired_state,
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
    print(f"desired_state: {payload['desired_state']}")
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
        store.set_desired_state(DESIRED_STATE_RUNNING)
        monitor_loop(cfg, store)
        return 0

    return _with_single_instance(cfg, _run)


def cmd_start(args: argparse.Namespace) -> int:
    cfg = _load_or_init_config(args.config, init_if_missing=True)
    setup_logging(cfg)
    store = StateStore(cfg.monitor.state_dir)
    state = store.set_desired_state(DESIRED_STATE_RUNNING)
    _emit_state_payload(
        _state_payload(store, config_path=args.config, config_exists=True, state=state),
        as_json=args.json,
    )
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    cfg = _load_or_init_config(args.config, init_if_missing=True)
    setup_logging(cfg)
    store = StateStore(cfg.monitor.state_dir)
    state = store.set_desired_state(DESIRED_STATE_STOPPED)
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
        help="Show desired_state and persisted monitor state without changing monitor behavior.",
    )
    _add_config_arg(parser_status)
    parser_status.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser_status.set_defaults(func=cmd_status)

    parser_start = subparsers.add_parser(
        "start",
        help="Set desired_state=running so an active monitor loop resumes auto-heal.",
    )
    _add_config_arg(parser_start)
    parser_start.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser_start.set_defaults(func=cmd_start)

    parser_stop = subparsers.add_parser(
        "stop",
        help="Set desired_state=stopped so monitor loops idle instead of probing/repairing.",
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
    "cmd_init",
    "cmd_monitor",
    "cmd_repair",
    "cmd_start",
    "cmd_status",
    "cmd_stop",
    "cmd_up",
    "main",
]
