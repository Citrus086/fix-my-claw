"""Internal helpers shared across CLI commands."""

from __future__ import annotations

import argparse
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import AppConfig
    from ..state import State, StateStore


def add_config_arg(parser: argparse.ArgumentParser, *, default: str) -> None:
    """Add --config argument to a parser."""
    parser.add_argument(
        "--config",
        default=default,
        help=f"Path to TOML config file (default: {default}).",
    )


def emit_state_payload(payload: dict[str, object], *, as_json: bool) -> None:
    """Emit status payload as JSON or human-readable text."""
    if as_json:
        print(json.dumps(payload, ensure_ascii=False))
        return
    print(f"enabled: {payload['enabled']}")
    print(f"config_path: {payload['config_path']}")
    print(f"config_exists: {payload['config_exists']}")
    print(f"state_path: {payload['state_path']}")
