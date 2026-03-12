"""CLI entry point for fix-my-claw.

This module is intentionally a thin facade that preserves the legacy patch
surface used by tests and other callers, while delegating heavy helpers and
parser construction to ``cli_commands`` submodules.
"""

from __future__ import annotations

import argparse
import json
import sys
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
    build_status_payload,
)
from .repair import attempt_repair
from .shared import _as_path, setup_logging
from .state import FileLock, State, StateStore

from .cli_commands.parser import build_parser as _build_parser
from .cli_commands.service import (
    cmd_service_install as _cmd_service_install_impl,
    cmd_service_reconcile as _cmd_service_reconcile_impl,
    cmd_service_start as _cmd_service_start_impl,
    cmd_service_status as _cmd_service_status_impl,
    cmd_service_stop as _cmd_service_stop_impl,
    cmd_service_uninstall as _cmd_service_uninstall_impl,
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


def cmd_service_install(args: argparse.Namespace) -> int:
    return _cmd_service_install_impl(
        args,
        load_or_init_config_impl=_load_or_init_config,
    )


def cmd_service_uninstall(args: argparse.Namespace) -> int:
    return _cmd_service_uninstall_impl(args)


def cmd_service_start(args: argparse.Namespace) -> int:
    return _cmd_service_start_impl(
        args,
        load_or_init_config_impl=_load_or_init_config,
        default_config_path=DEFAULT_CONFIG_PATH,
    )


def cmd_service_stop(args: argparse.Namespace) -> int:
    return _cmd_service_stop_impl(args)


def cmd_service_status(args: argparse.Namespace) -> int:
    return _cmd_service_status_impl(args, default_config_path=DEFAULT_CONFIG_PATH)


def cmd_service_reconcile(args: argparse.Namespace) -> int:
    return _cmd_service_reconcile_impl(
        args,
        load_or_init_config_impl=_load_or_init_config,
        default_config_path=DEFAULT_CONFIG_PATH,
    )


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
