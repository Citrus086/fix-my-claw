"""Config loading helpers shared across CLI commands."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import AppConfig


def as_path(path: str | Path) -> Path:
    """Convert string to Path, expanding user."""
    return Path(path).expanduser()


def load_or_init_config(
    path: str,
    *,
    init_if_missing: bool,
    write_default_config: callable,
    load_config: callable,
) -> "AppConfig":
    """Load config or initialize if missing."""
    config_path = as_path(path)
    if not config_path.exists():
        if init_if_missing:
            write_default_config(str(config_path), overwrite=False)
        else:
            raise FileNotFoundError(
                f"config not found: {config_path} (run `fix-my-claw init` or `fix-my-claw up`)"
            )
    return load_config(str(config_path))


def load_config_or_default(
    path: str,
    load_config: callable,
    default_config_factory: callable,
) -> tuple["AppConfig", bool]:
    """Load config if exists, otherwise return default."""
    config_path = as_path(path)
    if config_path.exists():
        return load_config(str(config_path)), True
    return default_config_factory(), False
