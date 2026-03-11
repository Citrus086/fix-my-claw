"""Configuration management - facade module.

This module provides the public API for configuration management.
Implementation details have been moved to config_parts/ submodules.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

# Re-export all models from config_parts.models
from .config_parts.models import (
    AgentRolesConfig,
    AiConfig,
    AnomalyGuardConfig,
    AppConfig,
    MonitorConfig,
    NotifyConfig,
    OpenClawConfig,
    RepairConfig,
)

# Re-export defaults from config_parts.defaults
from .config_parts.defaults import (
    DEFAULT_AGENT_ROLES,
    DEFAULT_CONFIG_PATH,
    DEFAULT_CONFIG_TOML,
    DEFAULT_PAUSE_MESSAGE,
    ALLOWED_OFFICIAL_STEP_COMMANDS,
)

# Re-export parse functions from config_parts.parse
from .config_parts.parse import (
    _parse_monitor,
    _parse_openclaw,
    _parse_repair,
    _parse_anomaly_guard,
    _parse_keyword_list,
    _parse_notify,
    _parse_ai,
    _parse_agent_roles,
    load_config,
)

# Re-export serialize functions from config_parts.serialize
from .config_parts.serialize import (
    _config_to_dict,
    _dict_to_config,
    _write_toml,
    write_default_config,
)

# Keep underscore helpers importable as module attributes for internal callers
# and tests, but only advertise the public API through ``__all__``.
__all__ = [
    "AgentRolesConfig",
    "AiConfig",
    "AnomalyGuardConfig",
    "AppConfig",
    "MonitorConfig",
    "NotifyConfig",
    "OpenClawConfig",
    "RepairConfig",
    "DEFAULT_AGENT_ROLES",
    "DEFAULT_CONFIG_PATH",
    "DEFAULT_CONFIG_TOML",
    "DEFAULT_PAUSE_MESSAGE",
    "ALLOWED_OFFICIAL_STEP_COMMANDS",
    "load_config",
    "write_default_config",
]
