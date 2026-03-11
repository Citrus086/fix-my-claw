"""Config serialization functions."""
from __future__ import annotations

from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any

from ..shared import ensure_dir
from .models import AgentRolesConfig, AppConfig
from .defaults import DEFAULT_CONFIG_TOML

try:
    import tomli_w
except ModuleNotFoundError:  # pragma: no cover
    tomli_w = None


def _config_to_dict(cfg: AppConfig) -> dict[str, Any]:
    """Convert AppConfig into a JSON/TOML-friendly nested mapping."""

    def _convert(value: Any) -> Any:
        if value is None:
            return None  # Mark None for filtering
        if isinstance(value, Path):
            return str(value)
        # Check AgentRolesConfig BEFORE is_dataclass because it's also a dataclass
        if isinstance(value, AgentRolesConfig):
            # Special case: flatten AgentRolesConfig.roles to match TOML/JSON format
            # Expected: {"orchestrator": [...], "builder": [...]}
            # NOT: {"roles": {"orchestrator": [...], ...}}
            return {str(key): list(_convert(item) for item in aliases) for key, aliases in value.roles.items()}
        if is_dataclass(value):
            return {field_.name: _convert(getattr(value, field_.name)) for field_ in fields(value)}
        if isinstance(value, list):
            return [_convert(item) for item in value]
        if isinstance(value, tuple):
            return [_convert(item) for item in value]
        if isinstance(value, dict):
            return {str(key): _convert(item) for key, item in value.items()}
        return value

    def _filter_none(value: Any) -> Any:
        """Recursively remove None values from the structure."""
        if value is None:
            return None  # Will be removed at dict level
        if isinstance(value, dict):
            return {k: _filter_none(v) for k, v in value.items() if v is not None}
        if isinstance(value, list):
            return [_filter_none(item) for item in value]
        return value

    converted = _convert(cfg)
    if not isinstance(converted, dict):
        raise TypeError("AppConfig conversion did not produce a mapping")
    
    # Filter out None values before serialization
    return _filter_none(converted)


def _dict_to_config(data: dict[str, Any]) -> AppConfig:
    """Rebuild AppConfig from a JSON-compatible mapping."""
    from .parse import (
        _parse_ai,
        _parse_anomaly_guard,
        _parse_monitor,
        _parse_notify,
        _parse_openclaw,
        _parse_repair,
        _parse_agent_roles,
    )
    from ..config_validation import validate_section_dict

    if not isinstance(data, dict):
        raise TypeError("config payload must be a JSON object")

    data = dict(data)
    data.pop("api_version", None)

    anomaly_raw = data.get("anomaly_guard", data.get("loop_guard", {}))
    if anomaly_raw is None:
        anomaly_raw = {}
    if not isinstance(anomaly_raw, dict):
        raise TypeError("anomaly_guard must be an object")

    return AppConfig(
        monitor=_parse_monitor(validate_section_dict(data, "monitor")),
        openclaw=_parse_openclaw(validate_section_dict(data, "openclaw")),
        repair=_parse_repair(validate_section_dict(data, "repair")),
        anomaly_guard=_parse_anomaly_guard(dict(anomaly_raw)),
        notify=_parse_notify(validate_section_dict(data, "notify")),
        ai=_parse_ai(validate_section_dict(data, "ai")),
        agent_roles=_parse_agent_roles(validate_section_dict(data, "agent_roles")),
    )


def _write_toml(path: Path, data: dict[str, Any]) -> None:
    """Write a TOML mapping to disk."""
    if tomli_w is None:
        raise ImportError("tomli_w is required to write TOML files")
    ensure_dir(path.parent)
    path.write_text(tomli_w.dumps(data), encoding="utf-8")


def write_default_config(path: str, *, overwrite: bool = False) -> Path:
    """Write default config TOML to the specified path."""
    p = Path(path).expanduser()
    if p.exists() and not overwrite:
        return p
    ensure_dir(p.parent)
    p.write_text(DEFAULT_CONFIG_TOML, encoding="utf-8")
    return p
