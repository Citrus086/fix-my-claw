"""Config CLI commands: config show, config set."""

from __future__ import annotations

import argparse
import json
import sys

from ..protocol import build_config_payload
from ..shared import setup_logging


def cmd_config_show(
    args: argparse.Namespace,
    *,
    load_config: callable,
    config_to_dict: callable,
) -> int:
    """Show current configuration."""
    from ._config_helpers import load_or_init_config as _load_or_init

    cfg = _load_or_init(
        args.config,
        init_if_missing=False,
        write_default_config=lambda *a, **k: None,
        load_config=load_config,
    )
    if args.json:
        print(json.dumps(build_config_payload(config_to_dict(cfg)), ensure_ascii=False, indent=2))
        return 0
    print("Current configuration:")
    print(f"monitor.interval_seconds={cfg.monitor.interval_seconds}")
    print(f"repair.enabled={cfg.repair.enabled}")
    print(f"ai.enabled={cfg.ai.enabled}")
    return 0


def cmd_config_set(
    args: argparse.Namespace,
    *,
    dict_to_config: callable,
    config_to_dict: callable,
    write_toml: callable,
) -> int:
    """Replace configuration from stdin JSON."""
    from pathlib import Path

    if not args.json:
        print("config set requires --json and JSON input on stdin", file=sys.stderr)
        return 1
    try:
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError as exc:
        print(f"error parsing JSON: {exc}", file=sys.stderr)
        return 1

    try:
        cfg = dict_to_config(payload)
    except (TypeError, ValueError) as exc:
        print(f"error validating configuration: {exc}", file=sys.stderr)
        return 1

    config_path = Path(args.config).expanduser()
    normalized = config_to_dict(cfg)
    try:
        write_toml(config_path, normalized)
    except Exception as exc:
        print(f"error writing configuration: {exc}", file=sys.stderr)
        return 1
    print(str(config_path))
    return 0
