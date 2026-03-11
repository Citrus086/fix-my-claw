"""Config parsing functions."""
from __future__ import annotations

import logging
import os
from typing import Any

from ..config_validation import (
    clamp_float,
    clamp_int,
    get_value,
    parse_string_list,
    validate_section_dict,
)
from ..shared import _as_path
from .defaults import ALLOWED_OFFICIAL_STEP_COMMANDS
from .models import (
    AgentRolesConfig,
    AiConfig,
    AnomalyGuardConfig,
    AppConfig,
    MonitorConfig,
    NotifyConfig,
    OpenClawConfig,
    RepairConfig,
)

_logger = logging.getLogger(__name__)


try:
    import tomllib  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore


def _parse_monitor(raw: dict[str, Any]) -> MonitorConfig:
    cfg = MonitorConfig()
    return MonitorConfig(
        interval_seconds=clamp_int(get_value(raw, "interval_seconds", cfg.interval_seconds), 1),
        probe_timeout_seconds=clamp_int(get_value(raw, "probe_timeout_seconds", cfg.probe_timeout_seconds), 1),
        repair_cooldown_seconds=clamp_int(get_value(raw, "repair_cooldown_seconds", cfg.repair_cooldown_seconds), 0),
        state_dir=_as_path(str(get_value(raw, "state_dir", cfg.state_dir))),
        log_file=_as_path(str(get_value(raw, "log_file", cfg.log_file))),
        log_level=str(get_value(raw, "log_level", cfg.log_level)),
        log_max_bytes=clamp_int(get_value(raw, "log_max_bytes", cfg.log_max_bytes), 1024 * 1024),  # Min 1 MB
        log_backup_count=clamp_int(get_value(raw, "log_backup_count", cfg.log_backup_count), 0),
        log_retention_days=clamp_int(get_value(raw, "log_retention_days", cfg.log_retention_days), 1),  # Min 1 day
    )


def _parse_openclaw(raw: dict[str, Any]) -> OpenClawConfig:
    cfg = OpenClawConfig()
    return OpenClawConfig(
        command=str(get_value(raw, "command", cfg.command)),
        state_dir=_as_path(str(get_value(raw, "state_dir", cfg.state_dir))),
        workspace_dir=_as_path(str(get_value(raw, "workspace_dir", cfg.workspace_dir))),
        health_args=list(get_value(raw, "health_args", cfg.health_args)),
        status_args=list(get_value(raw, "status_args", cfg.status_args)),
        logs_args=list(get_value(raw, "logs_args", cfg.logs_args)),
    )


def _parse_repair(raw: dict[str, Any]) -> RepairConfig:
    cfg = RepairConfig()
    raw_official_steps = get_value(raw, "official_steps", cfg.official_steps)
    # Filter and validate official_steps commands
    official_steps: list[list[str]] = []
    for step in raw_official_steps:
        if not step:
            continue
        step_list = list(step)
        if not step_list:
            continue
        # Validate command is in whitelist (check basename to support absolute paths)
        cmd = str(step_list[0]).strip()
        cmd_basename = os.path.basename(cmd)
        if cmd_basename in ALLOWED_OFFICIAL_STEP_COMMANDS:
            official_steps.append(step_list)
        else:
            # Warn about disallowed commands instead of silently ignoring
            _logger.warning(
                "Skipping official_step with disallowed command: %r "
                "(basename %r not in allowed commands: %s)",
                cmd,
                cmd_basename,
                sorted(ALLOWED_OFFICIAL_STEP_COMMANDS),
            )
    return RepairConfig(
        enabled=bool(get_value(raw, "enabled", cfg.enabled)),
        session_control_enabled=bool(get_value(raw, "session_control_enabled", cfg.session_control_enabled)),
        session_active_minutes=clamp_int(get_value(raw, "session_active_minutes", cfg.session_active_minutes), 1),
        session_agents=parse_string_list(get_value(raw, "session_agents", cfg.session_agents)),
        soft_pause_enabled=bool(get_value(raw, "soft_pause_enabled", cfg.soft_pause_enabled)),
        pause_message=str(get_value(raw, "pause_message", cfg.pause_message)),
        pause_wait_seconds=clamp_int(get_value(raw, "pause_wait_seconds", cfg.pause_wait_seconds), 0),
        terminate_message=str(get_value(raw, "terminate_message", cfg.terminate_message)),
        new_message=str(get_value(raw, "new_message", cfg.new_message)),
        session_command_timeout_seconds=clamp_int(get_value(raw, "session_command_timeout_seconds", cfg.session_command_timeout_seconds), 10),
        session_stage_wait_seconds=clamp_int(get_value(raw, "session_stage_wait_seconds", cfg.session_stage_wait_seconds), 0),
        official_steps=official_steps,
        step_timeout_seconds=clamp_int(get_value(raw, "step_timeout_seconds", cfg.step_timeout_seconds), 1),
        post_step_wait_seconds=clamp_int(get_value(raw, "post_step_wait_seconds", cfg.post_step_wait_seconds), 0),
    )


def _parse_anomaly_guard(raw: dict[str, Any]) -> AnomalyGuardConfig:
    cfg = AnomalyGuardConfig()
    # Support legacy alias min_ping_pong_turns -> min_cycle_repeated_turns
    min_cycle_repeated_turns = get_value(
        raw, "min_cycle_repeated_turns",
        get_value(raw, "min_ping_pong_turns", cfg.min_cycle_repeated_turns)
    )
    return AnomalyGuardConfig(
        enabled=bool(get_value(raw, "enabled", cfg.enabled)),
        window_lines=clamp_int(get_value(raw, "window_lines", cfg.window_lines), 20),
        probe_timeout_seconds=clamp_int(get_value(raw, "probe_timeout_seconds", cfg.probe_timeout_seconds), 3),
        keywords_stop=parse_string_list(get_value(raw, "keywords_stop", cfg.keywords_stop)),
        keywords_repeat=parse_string_list(get_value(raw, "keywords_repeat", cfg.keywords_repeat)),
        max_repeat_same_signature=clamp_int(get_value(raw, "max_repeat_same_signature", cfg.max_repeat_same_signature), 2),
        min_cycle_repeated_turns=clamp_int(min_cycle_repeated_turns, 2),
        max_cycle_period=clamp_int(get_value(raw, "max_cycle_period", cfg.max_cycle_period), 2),
        stagnation_enabled=bool(get_value(raw, "stagnation_enabled", cfg.stagnation_enabled)),
        stagnation_min_events=clamp_int(get_value(raw, "stagnation_min_events", cfg.stagnation_min_events), 4),
        stagnation_min_roles=clamp_int(get_value(raw, "stagnation_min_roles", cfg.stagnation_min_roles), 1),
        stagnation_max_novel_cluster_ratio=clamp_float(
            get_value(raw, "stagnation_max_novel_cluster_ratio", cfg.stagnation_max_novel_cluster_ratio),
            0.05, 1.0
        ),
        min_signature_chars=clamp_int(get_value(raw, "min_signature_chars", cfg.min_signature_chars), 8),
        auto_dispatch_check=bool(get_value(raw, "auto_dispatch_check", cfg.auto_dispatch_check)),
        dispatch_window_lines=clamp_int(get_value(raw, "dispatch_window_lines", cfg.dispatch_window_lines), 1),
        keywords_dispatch=parse_string_list(get_value(raw, "keywords_dispatch", cfg.keywords_dispatch)),
        min_post_dispatch_unexpected_turns=clamp_int(
            get_value(raw, "min_post_dispatch_unexpected_turns", cfg.min_post_dispatch_unexpected_turns), 2
        ),
        keywords_architect_active=parse_string_list(
            get_value(raw, "keywords_architect_active", cfg.keywords_architect_active)
        ),
        similarity_enabled=bool(get_value(raw, "similarity_enabled", cfg.similarity_enabled)),
        similarity_threshold=clamp_float(get_value(raw, "similarity_threshold", cfg.similarity_threshold), 0.5, 1.0),
        similarity_min_chars=clamp_int(get_value(raw, "similarity_min_chars", cfg.similarity_min_chars), 6),
        max_similar_repeat=clamp_int(get_value(raw, "max_similar_repeat", cfg.max_similar_repeat), 2),
    )


def _parse_keyword_list(value: Any, default: list[str] | None = None) -> list[str]:
    """Parse a list of keywords, filtering out empty strings and normalizing to lowercase.
    
    Returns default if value is empty or contains only empty strings.
    """
    keywords = parse_string_list(value)
    # Filter out empty strings and normalize
    result = [k.strip().lower() for k in keywords if isinstance(k, str) and k.strip()]
    # Return default if result is empty (prevents accidental lockout from bad config)
    if not result and default is not None:
        return list(default)
    return result


def _parse_notify(raw: dict[str, Any]) -> NotifyConfig:
    cfg = NotifyConfig()
    # Clamp timeouts to reasonable bounds: min 5s, max 5 minutes
    send_timeout_seconds = clamp_int(get_value(raw, "send_timeout_seconds", cfg.send_timeout_seconds), 5, 300)
    read_timeout_seconds = clamp_int(get_value(raw, "read_timeout_seconds", send_timeout_seconds), 5, 300)
    # Validate level enum
    level_value = str(get_value(raw, "level", cfg.level)).strip().lower()
    if level_value not in {"all", "important", "critical"}:
        level_value = "all"
    return NotifyConfig(
        channel=str(get_value(raw, "channel", cfg.channel)),
        account=str(get_value(raw, "account", cfg.account)),
        target=str(get_value(raw, "target", cfg.target)),
        required_mention_id=str(get_value(raw, "required_mention_id", cfg.required_mention_id)).strip(),
        silent=bool(get_value(raw, "silent", cfg.silent)),
        send_timeout_seconds=send_timeout_seconds,
        read_timeout_seconds=read_timeout_seconds,
        ask_enable_ai=bool(get_value(raw, "ask_enable_ai", cfg.ask_enable_ai)),
        # Clamp ask timeout: min 15s, max 24 hours
        ask_timeout_seconds=clamp_int(get_value(raw, "ask_timeout_seconds", cfg.ask_timeout_seconds), 15, 86400),
        # Clamp poll interval: min 1s, max 1 hour
        poll_interval_seconds=clamp_int(get_value(raw, "poll_interval_seconds", cfg.poll_interval_seconds), 1, 3600),
        read_limit=clamp_int(get_value(raw, "read_limit", cfg.read_limit), 1),
        max_invalid_replies=clamp_int(get_value(raw, "max_invalid_replies", cfg.max_invalid_replies), 1, 20),
        level=level_value,
        operator_user_ids=parse_string_list(get_value(raw, "operator_user_ids", cfg.operator_user_ids)),
        # Parse keyword lists (non-empty strings only)
        manual_repair_keywords=_parse_keyword_list(get_value(raw, "manual_repair_keywords", cfg.manual_repair_keywords)),
        ai_approve_keywords=_parse_keyword_list(get_value(raw, "ai_approve_keywords", cfg.ai_approve_keywords)),
        ai_reject_keywords=_parse_keyword_list(get_value(raw, "ai_reject_keywords", cfg.ai_reject_keywords)),
    )


def _parse_ai(raw: dict[str, Any]) -> AiConfig:
    cfg = AiConfig()
    return AiConfig(
        enabled=bool(get_value(raw, "enabled", cfg.enabled)),
        provider=str(get_value(raw, "provider", cfg.provider)),
        command=str(get_value(raw, "command", cfg.command)),
        args=list(get_value(raw, "args", cfg.args)),
        model=get_value(raw, "model", cfg.model),
        # Clamp timeout: min 1s, max 24 hours
        timeout_seconds=clamp_int(get_value(raw, "timeout_seconds", cfg.timeout_seconds), 1, 86400),
        # Clamp max attempts: min 0, max 100 (reasonable upper bound)
        max_attempts_per_day=clamp_int(get_value(raw, "max_attempts_per_day", cfg.max_attempts_per_day), 0, 100),
        # Clamp cooldown: min 0, max 7 days
        cooldown_seconds=clamp_int(get_value(raw, "cooldown_seconds", cfg.cooldown_seconds), 0, 604800),
        allow_code_changes=bool(get_value(raw, "allow_code_changes", cfg.allow_code_changes)),
        args_code=list(get_value(raw, "args_code", cfg.args_code)),
    )


def _parse_agent_roles(raw: dict[str, Any]) -> AgentRolesConfig:
    """Parse agent roles configuration from TOML/JSON data.

    Expected format:
    [agent_roles]
    orchestrator = ["orchestrator", "macs-orchestrator"]
    builder = ["builder", "macs-builder"]
    ...

    User-specified roles are merged with defaults, so missing roles
    fall back to default values rather than being removed.
    """
    # Start with default roles
    default_config = AgentRolesConfig()
    merged_roles: dict[str, tuple[str, ...]] = dict(default_config.roles)

    if not raw:
        return default_config

    # Merge user-specified roles (override defaults)
    for role_name, aliases in raw.items():
        if not isinstance(aliases, list):
            continue
        # Filter to non-empty strings
        valid_aliases = tuple(str(a).strip() for a in aliases if a and str(a).strip())
        if valid_aliases:
            merged_roles[str(role_name).strip()] = valid_aliases

    return AgentRolesConfig(roles=merged_roles)


def load_config(path: str) -> AppConfig:
    p = _as_path(path)
    if not p.exists():
        raise FileNotFoundError(f"config not found: {p}")
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    monitor = _parse_monitor(dict(data.get("monitor", {})))
    openclaw = _parse_openclaw(dict(data.get("openclaw", {})))
    repair = _parse_repair(dict(data.get("repair", {})))
    anomaly_raw = data.get("anomaly_guard", data.get("loop_guard", {}))
    anomaly_guard = _parse_anomaly_guard(dict(anomaly_raw))
    notify = _parse_notify(dict(data.get("notify", {})))
    ai = _parse_ai(dict(data.get("ai", {})))
    agent_roles = _parse_agent_roles(dict(data.get("agent_roles", {})))
    return AppConfig(
        monitor=monitor,
        openclaw=openclaw,
        repair=repair,
        anomaly_guard=anomaly_guard,
        notify=notify,
        ai=ai,
        agent_roles=agent_roles,
    )
