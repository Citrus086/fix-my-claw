"""Dataclass models for configuration."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..shared import _as_path
from .defaults import DEFAULT_AGENT_ROLES, DEFAULT_PAUSE_MESSAGE


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
