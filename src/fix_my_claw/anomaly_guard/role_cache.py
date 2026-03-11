"""Role aliases cache management for anomaly detection."""
from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import AppConfig


# Module-level caches for performance (updated when config changes)
# Use config content hash as key instead of id() to avoid issues with object reuse
_cached_config_hash: str | None = None
_cached_role_aliases: dict[str, tuple[str, ...]] | None = None
_cached_agent_roles: frozenset[str] | None = None
_cached_all_aliases: frozenset[str] | None = None
_cache_lock = threading.Lock()


def _config_hash(cfg: "AppConfig") -> str:
    """Compute a hash of the agent_roles config for cache invalidation.

    Using content hash instead of id() avoids issues where Python reuses
    memory addresses for different config objects.
    """
    # Hash based on agent_roles content since that's what we cache
    roles = cfg.agent_roles.roles
    # Sort for deterministic hash
    items = tuple((k, tuple(sorted(v))) for k, v in sorted(roles.items()))
    return str(hash(items))


def _build_role_aliases_from_config(cfg: "AppConfig") -> dict[str, tuple[str, ...]]:
    """Build ROLE_ALIASES from config, with fallback to defaults."""
    return dict(cfg.agent_roles.roles)


def _build_agent_roles_from_config(cfg: "AppConfig") -> frozenset[str]:
    """Build AGENT_ROLES (canonical role names) from config."""
    return cfg.agent_roles.get_canonical_roles()


def _build_all_aliases_from_config(cfg: "AppConfig") -> frozenset[str]:
    """Build ALL_ROLE_ALIASES (all alias strings) from config."""
    return cfg.agent_roles.get_all_aliases()


def _refresh_caches_if_needed(cfg: "AppConfig") -> None:
    """Refresh all caches if config has changed.

    This ensures all three caches are updated atomically when the config changes,
    preventing stale cache data from being used after a config switch.
    """
    global _cached_config_hash, _cached_role_aliases, _cached_agent_roles, _cached_all_aliases
    config_hash = _config_hash(cfg)
    with _cache_lock:
        if _cached_config_hash != config_hash:
            # Config changed - refresh ALL caches atomically
            _cached_config_hash = config_hash
            _cached_role_aliases = _build_role_aliases_from_config(cfg)
            _cached_agent_roles = _build_agent_roles_from_config(cfg)
            _cached_all_aliases = _build_all_aliases_from_config(cfg)


def get_role_aliases(cfg: "AppConfig") -> dict[str, tuple[str, ...]]:
    """Get role aliases, using cache if config hasn't changed."""
    _refresh_caches_if_needed(cfg)
    with _cache_lock:
        # Cache is guaranteed to be valid after refresh
        return _cached_role_aliases if _cached_role_aliases is not None else {}


def get_agent_roles(cfg: "AppConfig") -> frozenset[str]:
    """Get canonical agent roles, using cache if config hasn't changed."""
    _refresh_caches_if_needed(cfg)
    with _cache_lock:
        # Cache is guaranteed to be valid after refresh
        return _cached_agent_roles if _cached_agent_roles is not None else frozenset()


def get_all_aliases(cfg: "AppConfig") -> frozenset[str]:
    """Get all role aliases, using cache if config hasn't changed."""
    _refresh_caches_if_needed(cfg)
    with _cache_lock:
        # Cache is guaranteed to be valid after refresh
        return _cached_all_aliases if _cached_all_aliases is not None else frozenset()
