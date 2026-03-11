"""Core CLI commands: init, check, status, start, stop, repair, auto-repair, monitor, up."""

from __future__ import annotations

import argparse
import json
import sys
from typing import TYPE_CHECKING, Callable

from ..protocol import (
    build_check_payload,
    build_repair_payload,
    build_status_payload,
)
from ..shared import setup_logging
from ..state import FileLock, StateStore
from ._config_helpers import load_or_init_config, load_config_or_default

if TYPE_CHECKING:
    from ..config import AppConfig


def _with_single_instance(cfg: "AppConfig", action: Callable[[], int]) -> int:
    """Run action with single-instance lock."""
    lock = FileLock(cfg.monitor.state_dir / "fix-my-claw.lock")
    if not lock.acquire(timeout_seconds=0):
        print("another fix-my-claw instance is running", file=sys.stderr)
        return 2
    try:
        return action()
    finally:
        lock.release()


def _state_payload(
    store: StateStore,
    *,
    config_path: str,
    config_exists: bool,
    state: "State | None" = None,
) -> dict[str, object]:
    """Build status payload from state."""
    from ..shared import _as_path

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


def cmd_init(
    args: argparse.Namespace,
    *,
    write_default_config: callable,
) -> int:
    """Write default config."""
    config_path = write_default_config(args.config, overwrite=args.force)
    print(str(config_path))
    return 0


def cmd_check(
    args: argparse.Namespace,
    *,
    load_config: callable,
    run_check: callable,
) -> int:
    """Probe OpenClaw health/status once."""
    from ..config import DEFAULT_CONFIG_PATH
    from ._config_helpers import load_or_init_config as _load_or_init

    cfg = _load_or_init(
        args.config,
        init_if_missing=False,
        write_default_config=lambda *a, **k: None,
        load_config=load_config,
    )
    setup_logging(cfg)
    store = StateStore(cfg.monitor.state_dir)
    result = run_check(cfg, store)
    if args.json:
        print(json.dumps(build_check_payload(result.to_check_json()), ensure_ascii=False))
    return 0 if result.effective_healthy else 1


def _run_repair_once(
    args: argparse.Namespace,
    *,
    reason: str | None,
    load_config: callable,
    attempt_repair: callable,
) -> int:
    """Run repair once with single-instance lock."""
    from ._config_helpers import load_or_init_config as _load_or_init

    cfg = _load_or_init(
        args.config,
        init_if_missing=False,
        write_default_config=lambda *a, **k: None,
        load_config=load_config,
    )
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


def cmd_repair(
    args: argparse.Namespace,
    *,
    load_config: callable,
    attempt_repair: callable,
) -> int:
    """Run manual repair."""
    return _run_repair_once(
        args,
        reason="manual_cli",
        load_config=load_config,
        attempt_repair=attempt_repair,
    )


def cmd_auto_repair(
    args: argparse.Namespace,
    *,
    load_config: callable,
    attempt_repair: callable,
) -> int:
    """Run automatic repair."""
    return _run_repair_once(
        args,
        reason=None,
        load_config=load_config,
        attempt_repair=attempt_repair,
    )


def cmd_monitor(
    args: argparse.Namespace,
    *,
    load_config: callable,
    monitor_loop: callable,
) -> int:
    """Run 24/7 monitor loop."""
    from ._config_helpers import load_or_init_config as _load_or_init

    cfg = _load_or_init(
        args.config,
        init_if_missing=False,
        write_default_config=lambda *a, **k: None,
        load_config=load_config,
    )
    setup_logging(cfg)

    def _run() -> int:
        store = StateStore(cfg.monitor.state_dir)
        monitor_loop(cfg, store)
        return 0

    return _with_single_instance(cfg, _run)


def cmd_up(
    args: argparse.Namespace,
    *,
    load_config: callable,
    write_default_config: callable,
    monitor_loop: callable,
) -> int:
    """One-command start: init default config then monitor."""
    from ._config_helpers import load_or_init_config as _load_or_init

    cfg = _load_or_init(
        args.config,
        init_if_missing=True,
        write_default_config=write_default_config,
        load_config=load_config,
    )
    setup_logging(cfg)

    def _run() -> int:
        store = StateStore(cfg.monitor.state_dir)
        store.set_enabled(True)
        monitor_loop(cfg, store)
        return 0

    return _with_single_instance(cfg, _run)


def cmd_start(
    args: argparse.Namespace,
    *,
    load_config: callable,
    write_default_config: callable,
) -> int:
    """Enable monitoring."""
    from ._helpers import emit_state_payload
    from ._config_helpers import load_or_init_config as _load_or_init

    cfg = _load_or_init(
        args.config,
        init_if_missing=True,
        write_default_config=write_default_config,
        load_config=load_config,
    )
    setup_logging(cfg)
    store = StateStore(cfg.monitor.state_dir)
    state = store.set_enabled(True)
    emit_state_payload(
        _state_payload(store, config_path=args.config, config_exists=True, state=state),
        as_json=args.json,
    )
    return 0


def cmd_stop(
    args: argparse.Namespace,
    *,
    load_config: callable,
    write_default_config: callable,
) -> int:
    """Disable monitoring."""
    from ._helpers import emit_state_payload
    from ._config_helpers import load_or_init_config as _load_or_init

    cfg = _load_or_init(
        args.config,
        init_if_missing=True,
        write_default_config=write_default_config,
        load_config=load_config,
    )
    setup_logging(cfg)
    store = StateStore(cfg.monitor.state_dir)
    state = store.set_enabled(False)
    emit_state_payload(
        _state_payload(store, config_path=args.config, config_exists=True, state=state),
        as_json=args.json,
    )
    return 0


def cmd_status(
    args: argparse.Namespace,
    *,
    load_config: callable,
    default_config_factory: callable,
    load_config_or_default: callable | None = None,
) -> int:
    """Show monitoring status."""
    from ._helpers import emit_state_payload
    from ._config_helpers import load_config_or_default as _default_load_or_default

    _load_or_default = load_config_or_default or _default_load_or_default
    cfg, config_exists = _load_or_default(
        args.config,
        load_config=load_config,
        default_config_factory=default_config_factory,
    )
    if config_exists:
        setup_logging(cfg)
    store = StateStore(cfg.monitor.state_dir)
    emit_state_payload(
        _state_payload(store, config_path=args.config, config_exists=config_exists),
        as_json=args.json,
    )
    return 0
