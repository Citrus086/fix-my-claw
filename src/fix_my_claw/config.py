from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

from .config_validation import (
    clamp_float,
    clamp_int,
    get_value,
    parse_string_list,
    validate_section_dict,
)
from .shared import _as_path, ensure_dir

_logger = logging.getLogger(__name__)

try:
    import tomllib  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

try:
    import tomli_w
except ModuleNotFoundError:  # pragma: no cover
    tomli_w = None

DEFAULT_CONFIG_PATH = "~/.fix-my-claw/config.toml"
DEFAULT_PAUSE_MESSAGE = """[CONTROL]
Action: PAUSE
Reason: fix-my-claw detected an unhealthy state and is preserving the current task before stronger recovery.
Expectation: ACK once, then stay paused until further instruction.
"""

# Default agent role aliases - maps canonical role names to their possible aliases
DEFAULT_AGENT_ROLES = {
    "orchestrator": ["orchestrator", "macs-orchestrator"],
    "builder": ["builder", "macs-builder"],
    "architect": ["architect", "macs-architect"],
    "research": ["research", "macs-research"],
}

# Allowed commands for official_steps to prevent command injection
# Supports both bare commands and absolute paths (checks basename)
ALLOWED_OFFICIAL_STEP_COMMANDS = frozenset({
    "openclaw",  # OpenClaw CLI commands
})

DEFAULT_CONFIG_TOML = """\
[monitor]
interval_seconds = 60
probe_timeout_seconds = 30
repair_cooldown_seconds = 300
state_dir = "~/.fix-my-claw"
log_file = "~/.fix-my-claw/fix-my-claw.log"
log_level = "INFO"
# Log rotation settings
log_max_bytes = 5242880  # 5 MB - rotate when log file exceeds this size
log_backup_count = 5  # Number of backup log files to keep
log_retention_days = 30  # Delete log files older than this many days on cleanup

[openclaw]
command = "openclaw"
state_dir = "~/.openclaw"
workspace_dir = "~/.openclaw/workspace"
health_args = ["gateway", "health", "--json"]
status_args = ["gateway", "status", "--json"]
logs_args = ["logs", "--limit", "200", "--plain"]

[repair]
enabled = true
session_control_enabled = true
session_active_minutes = 30
# List of agent IDs that fix-my-claw can send session commands to.
# These should match the agent IDs configured in your OpenClaw setup.
session_agents = ["YOUR_ORCHESTRATOR_AGENT_ID", "YOUR_BUILDER_AGENT_ID", "YOUR_ARCHITECT_AGENT_ID", "YOUR_RESEARCH_AGENT_ID"]
soft_pause_enabled = true
pause_message = '''
[CONTROL]
Action: PAUSE
Reason: fix-my-claw detected an unhealthy state and is preserving the current task before stronger recovery.
Expectation: ACK once, then stay paused until further instruction.
'''
pause_wait_seconds = 20
terminate_message = "/stop"
new_message = "/new"
session_command_timeout_seconds = 120
session_stage_wait_seconds = 1
official_steps = [
  ["openclaw", "doctor", "--repair"],
  ["openclaw", "gateway", "restart"],
]
step_timeout_seconds = 600
post_step_wait_seconds = 2

[notify]
channel = "discord"
account = "fix-my-claw"
# Target for notifications. For Discord, use "channel:YOUR_CHANNEL_ID" or "user:YOUR_USER_ID".
# You must configure this to receive alerts.
target = "channel:YOUR_DISCORD_CHANNEL_ID"
# If set, channel replies must explicitly mention this account/user id.
# Leave empty to auto-detect from built-in defaults when possible.
required_mention_id = ""
silent = true
send_timeout_seconds = 20
read_timeout_seconds = 20
ask_enable_ai = true
ask_timeout_seconds = 300
poll_interval_seconds = 5
read_limit = 20
max_invalid_replies = 3
# Notification level: "all" (all events), "important" (AI confirmation, repair failures), "critical" (only critical failures)
level = "all"
# If target is channel:..., reply should mention notify account (e.g. "@fix-my-claw yes").
# Only strict replies are accepted: 是/否/yes/no. Invalid replies are re-asked and capped at 3 attempts.
operator_user_ids = []
# Keywords for manual repair command recognition (case-insensitive)
manual_repair_keywords = ["手动修复", "manual repair", "修复", "repair"]
# Keywords for AI approval (yes) - case-insensitive
ai_approve_keywords = ["yes", "是"]
# Keywords for AI rejection (no) - case-insensitive
ai_reject_keywords = ["no", "否"]

[anomaly_guard]
enabled = true
window_lines = 200
probe_timeout_seconds = 30
keywords_stop = ["stop", "halt", "abort", "cancel", "terminate", "停止", "立刻停止", "强制停止", "终止", "停止指令"]
keywords_repeat = ["repeat", "repeating", "loop", "ping-pong", "重复", "死循环", "不断", "一直在重复", "重复汇报"]
max_repeat_same_signature = 3
min_cycle_repeated_turns = 4
max_cycle_period = 4
stagnation_enabled = true
stagnation_min_events = 8
stagnation_min_roles = 2
stagnation_max_novel_cluster_ratio = 0.34
min_signature_chars = 16
auto_dispatch_check = true
dispatch_window_lines = 20
keywords_dispatch = ["dispatch", "handoff", "delegate", "assign", "开始实施", "开始执行", "派给", "转交"]
min_post_dispatch_unexpected_turns = 2
similarity_enabled = true
similarity_threshold = 0.82
similarity_min_chars = 12
max_similar_repeat = 4

[ai]
enabled = false
provider = "codex"
command = "codex"
args = [
  "exec",
  "-s", "workspace-write",
  "-c", "approval_policy=\\"never\\"",
  "--skip-git-repo-check",
  "-C", "$workspace_dir",
  "--add-dir", "$openclaw_state_dir",
  "--add-dir", "$monitor_state_dir",
]
model = "gpt-5.2"
timeout_seconds = 1800
max_attempts_per_day = 2
cooldown_seconds = 3600
allow_code_changes = false
args_code = [
  "exec",
  "-s", "danger-full-access",
  "-c", "approval_policy=\\"never\\"",
  "--skip-git-repo-check",
  "-C", "$workspace_dir",
]

# Agent roles configuration for anomaly detection.
# Maps canonical role names to their possible aliases (e.g., short name and full agent ID).
# The anomaly detector uses these to identify which agent is speaking in the logs.
[agent_roles]
# Each key is a canonical role name, and the value is a list of possible aliases.
orchestrator = ["orchestrator", "YOUR_ORCHESTRATOR_AGENT_ID"]
builder = ["builder", "YOUR_BUILDER_AGENT_ID"]
architect = ["architect", "YOUR_ARCHITECT_AGENT_ID"]
research = ["research", "YOUR_RESEARCH_AGENT_ID"]
"""


@dataclass(frozen=True)
class MonitorConfig:
    interval_seconds: int = 60
    probe_timeout_seconds: int = 30
    repair_cooldown_seconds: int = 300
    state_dir: Path = field(default_factory=lambda: _as_path("~/.fix-my-claw"))
    log_file: Path = field(default_factory=lambda: _as_path("~/.fix-my-claw/fix-my-claw.log"))
    log_level: str = "INFO"
    log_max_bytes: int = 5 * 1024 * 1024  # 5 MB - rotate when log exceeds this size
    log_backup_count: int = 5  # Number of backup files to keep after rotation
    log_retention_days: int = 30  # Delete logs older than this many days on cleanup


@dataclass(frozen=True)
class OpenClawConfig:
    command: str = "openclaw"
    state_dir: Path = field(default_factory=lambda: _as_path("~/.openclaw"))
    workspace_dir: Path = field(default_factory=lambda: _as_path("~/.openclaw/workspace"))
    health_args: list[str] = field(default_factory=lambda: ["gateway", "health", "--json"])
    status_args: list[str] = field(default_factory=lambda: ["gateway", "status", "--json"])
    logs_args: list[str] = field(default_factory=lambda: ["logs", "--limit", "200", "--plain"])


@dataclass(frozen=True)
class RepairConfig:
    enabled: bool = True
    session_control_enabled: bool = True
    session_active_minutes: int = 30
    session_agents: list[str] = field(
        default_factory=lambda: list(DEFAULT_AGENT_ROLES.get("orchestrator", []))
        + list(DEFAULT_AGENT_ROLES.get("builder", []))
        + list(DEFAULT_AGENT_ROLES.get("architect", []))
        + list(DEFAULT_AGENT_ROLES.get("research", []))
    )
    soft_pause_enabled: bool = True
    pause_message: str = DEFAULT_PAUSE_MESSAGE
    pause_wait_seconds: int = 20
    terminate_message: str = "/stop"
    new_message: str = "/new"
    session_command_timeout_seconds: int = 120
    session_stage_wait_seconds: int = 1
    official_steps: list[list[str]] = field(
        default_factory=lambda: [
            ["openclaw", "doctor", "--repair"],
            ["openclaw", "gateway", "restart"],
        ]
    )
    step_timeout_seconds: int = 600
    post_step_wait_seconds: int = 2


@dataclass(frozen=True)
class AnomalyGuardConfig:
    enabled: bool = True
    window_lines: int = 200
    probe_timeout_seconds: int = 30
    keywords_stop: list[str] = field(
        default_factory=lambda: [
            "stop",
            "halt",
            "abort",
            "cancel",
            "terminate",
            "停止",
            "立刻停止",
            "强制停止",
            "终止",
            "停止指令",
        ]
    )
    keywords_repeat: list[str] = field(
        default_factory=lambda: [
            "repeat",
            "repeating",
            "loop",
            "ping-pong",
            "重复",
            "死循环",
            "不断",
            "一直在重复",
            "重复汇报",
        ]
    )
    max_repeat_same_signature: int = 3
    min_cycle_repeated_turns: int = 4
    max_cycle_period: int = 4
    stagnation_enabled: bool = True
    stagnation_min_events: int = 8
    stagnation_min_roles: int = 2
    stagnation_max_novel_cluster_ratio: float = 0.34
    min_signature_chars: int = 16
    auto_dispatch_check: bool = True
    dispatch_window_lines: int = 20
    keywords_dispatch: list[str] = field(
        default_factory=lambda: [
            "dispatch",
            "handoff",
            "delegate",
            "assign",
            "开始实施",
            "开始执行",
            "派给",
            "转交",
        ]
    )
    min_post_dispatch_unexpected_turns: int = 2
    keywords_architect_active: list[str] = field(
        default_factory=lambda: [
            "architect",
            "still output",
            "continue output",
            "还在输出",
            "继续发内容",
            "连续输出",
        ]
    )
    similarity_enabled: bool = True
    similarity_threshold: float = 0.82
    similarity_min_chars: int = 12
    max_similar_repeat: int = 4

    @property
    def min_ping_pong_turns(self) -> int:
        return self.min_cycle_repeated_turns


@dataclass(frozen=True)
class NotifyConfig:
    channel: str = "discord"
    account: str = "fix-my-claw"
    target: str = "channel:YOUR_DISCORD_CHANNEL_ID"  # Must be configured by user
    required_mention_id: str = ""
    silent: bool = True
    send_timeout_seconds: int = 20
    read_timeout_seconds: int = 20
    ask_enable_ai: bool = True
    ask_timeout_seconds: int = 300
    poll_interval_seconds: int = 5
    read_limit: int = 20
    max_invalid_replies: int = 3
    level: str = "all"  # "all" | "important" | "critical"
    operator_user_ids: list[str] = field(default_factory=list)
    # Keywords for manual repair command recognition
    manual_repair_keywords: list[str] = field(
        default_factory=lambda: ["手动修复", "manual repair", "修复", "repair"]
    )
    # Keywords for AI approval (yes)
    ai_approve_keywords: list[str] = field(
        default_factory=lambda: ["yes", "是"]
    )
    # Keywords for AI rejection (no)
    ai_reject_keywords: list[str] = field(
        default_factory=lambda: ["no", "否"]
    )


@dataclass(frozen=True)
class AgentRolesConfig:
    """Configuration for agent role aliases used in anomaly detection.

    Maps canonical role names to their possible aliases.
    For example: {"orchestrator": ["orchestrator", "macs-orchestrator"]}
    """
    roles: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: {k: tuple(v) for k, v in DEFAULT_AGENT_ROLES.items()}
    )

    def get_aliases(self, role: str) -> tuple[str, ...]:
        """Get all aliases for a given canonical role name."""
        return self.roles.get(role, ())

    def get_all_aliases(self) -> frozenset[str]:
        """Get all aliases across all roles."""
        return frozenset(alias for aliases in self.roles.values() for alias in aliases)

    def get_canonical_roles(self) -> frozenset[str]:
        """Get all canonical role names."""
        return frozenset(self.roles.keys())


@dataclass(frozen=True)
class AiConfig:
    enabled: bool = False
    provider: str = "codex"
    command: str = "codex"
    args: list[str] = field(
        default_factory=lambda: [
            "exec",
            "-s",
            "workspace-write",
            "-c",
            'approval_policy="never"',
            "--skip-git-repo-check",
            "-C",
            "$workspace_dir",
            "--add-dir",
            "$openclaw_state_dir",
            "--add-dir",
            "$monitor_state_dir",
        ]
    )
    model: str | None = None
    timeout_seconds: int = 1800
    max_attempts_per_day: int = 2
    cooldown_seconds: int = 3600
    allow_code_changes: bool = False
    args_code: list[str] = field(
        default_factory=lambda: [
            "exec",
            "-s",
            "danger-full-access",
            "-c",
            'approval_policy="never"',
            "--skip-git-repo-check",
            "-C",
            "$workspace_dir",
        ]
    )


@dataclass(frozen=True)
class AppConfig:
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    openclaw: OpenClawConfig = field(default_factory=OpenClawConfig)
    repair: RepairConfig = field(default_factory=RepairConfig)
    anomaly_guard: AnomalyGuardConfig = field(default_factory=AnomalyGuardConfig)
    notify: NotifyConfig = field(default_factory=NotifyConfig)
    ai: AiConfig = field(default_factory=AiConfig)
    agent_roles: AgentRolesConfig = field(default_factory=AgentRolesConfig)


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


def write_default_config(path: str, *, overwrite: bool = False) -> Path:
    p = _as_path(path)
    if p.exists() and not overwrite:
        return p
    ensure_dir(p.parent)
    p.write_text(DEFAULT_CONFIG_TOML, encoding="utf-8")
    return p


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
