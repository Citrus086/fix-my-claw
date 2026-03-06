from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .shared import _as_path, ensure_dir

try:
    import tomllib  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

DEFAULT_CONFIG_PATH = "~/.fix-my-claw/config.toml"

DEFAULT_CONFIG_TOML = """\
[monitor]
interval_seconds = 60
probe_timeout_seconds = 15
repair_cooldown_seconds = 300
state_dir = "~/.fix-my-claw"
log_file = "~/.fix-my-claw/fix-my-claw.log"
log_level = "INFO"

[openclaw]
command = "openclaw"
state_dir = "~/.openclaw"
workspace_dir = "~/.openclaw/workspace"
health_args = ["gateway", "health", "--json"]
status_args = ["gateway", "status", "--json"]
logs_args = ["logs", "--tail", "200"]

[repair]
enabled = true
session_control_enabled = true
session_active_minutes = 30
session_agents = ["macs-orchestrator", "macs-builder", "macs-architect", "macs-research"]
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
account = "orchestrator"
target = "channel:1479011917367476347"
silent = true
send_timeout_seconds = 20
read_timeout_seconds = 20
ask_enable_ai = true
ask_timeout_seconds = 300
poll_interval_seconds = 5
read_limit = 20
# If target is channel:..., reply should mention notify account (e.g. "@fix-my-claw yes").
# Only strict replies are accepted: 是/否/yes/no. Invalid replies are re-asked and capped at 3 attempts.
operator_user_ids = []

[anomaly_guard]
enabled = true
window_lines = 200
probe_timeout_seconds = 15
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
"""


@dataclass(frozen=True)
class MonitorConfig:
    interval_seconds: int = 60
    probe_timeout_seconds: int = 15
    repair_cooldown_seconds: int = 300
    state_dir: Path = field(default_factory=lambda: _as_path("~/.fix-my-claw"))
    log_file: Path = field(default_factory=lambda: _as_path("~/.fix-my-claw/fix-my-claw.log"))
    log_level: str = "INFO"


@dataclass(frozen=True)
class OpenClawConfig:
    command: str = "openclaw"
    state_dir: Path = field(default_factory=lambda: _as_path("~/.openclaw"))
    workspace_dir: Path = field(default_factory=lambda: _as_path("~/.openclaw/workspace"))
    health_args: list[str] = field(default_factory=lambda: ["gateway", "health", "--json"])
    status_args: list[str] = field(default_factory=lambda: ["gateway", "status", "--json"])
    logs_args: list[str] = field(default_factory=lambda: ["logs", "--tail", "200"])


@dataclass(frozen=True)
class RepairConfig:
    enabled: bool = True
    session_control_enabled: bool = True
    session_active_minutes: int = 30
    session_agents: list[str] = field(
        default_factory=lambda: [
            "macs-orchestrator",
            "macs-builder",
            "macs-architect",
            "macs-research",
        ]
    )
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
    probe_timeout_seconds: int = 15
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
    account: str = "orchestrator"
    target: str = "channel:1479011917367476347"
    silent: bool = True
    send_timeout_seconds: int = 20
    read_timeout_seconds: int = 20
    ask_enable_ai: bool = True
    ask_timeout_seconds: int = 300
    poll_interval_seconds: int = 5
    read_limit: int = 20
    operator_user_ids: list[str] = field(default_factory=list)


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


def _get(d: dict[str, Any], key: str, default: Any) -> Any:
    v = d.get(key, default)
    return default if v is None else v


def _parse_monitor(raw: dict[str, Any]) -> MonitorConfig:
    return MonitorConfig(
        interval_seconds=max(1, int(_get(raw, "interval_seconds", 60))),
        probe_timeout_seconds=max(1, int(_get(raw, "probe_timeout_seconds", 15))),
        repair_cooldown_seconds=max(0, int(_get(raw, "repair_cooldown_seconds", 300))),
        state_dir=_as_path(str(_get(raw, "state_dir", "~/.fix-my-claw"))),
        log_file=_as_path(str(_get(raw, "log_file", "~/.fix-my-claw/fix-my-claw.log"))),
        log_level=str(_get(raw, "log_level", "INFO")),
    )


def _parse_openclaw(raw: dict[str, Any]) -> OpenClawConfig:
    return OpenClawConfig(
        command=str(_get(raw, "command", "openclaw")),
        state_dir=_as_path(str(_get(raw, "state_dir", "~/.openclaw"))),
        workspace_dir=_as_path(str(_get(raw, "workspace_dir", "~/.openclaw/workspace"))),
        health_args=list(_get(raw, "health_args", ["gateway", "health", "--json"])),
        status_args=list(_get(raw, "status_args", ["gateway", "status", "--json"])),
        logs_args=list(_get(raw, "logs_args", ["logs", "--tail", "200"])),
    )


def _parse_repair(raw: dict[str, Any]) -> RepairConfig:
    raw_official_steps = _get(raw, "official_steps", RepairConfig().official_steps)
    official_steps = [list(x) for x in raw_official_steps if x]
    return RepairConfig(
        enabled=bool(_get(raw, "enabled", True)),
        session_control_enabled=bool(_get(raw, "session_control_enabled", True)),
        session_active_minutes=max(1, int(_get(raw, "session_active_minutes", 30))),
        session_agents=[str(x).strip() for x in _get(raw, "session_agents", RepairConfig().session_agents)],
        terminate_message=str(_get(raw, "terminate_message", "/stop")),
        new_message=str(_get(raw, "new_message", "/new")),
        session_command_timeout_seconds=max(10, int(_get(raw, "session_command_timeout_seconds", 120))),
        session_stage_wait_seconds=max(0, int(_get(raw, "session_stage_wait_seconds", 1))),
        official_steps=official_steps,
        step_timeout_seconds=max(1, int(_get(raw, "step_timeout_seconds", 600))),
        post_step_wait_seconds=max(0, int(_get(raw, "post_step_wait_seconds", 2))),
    )


def _parse_anomaly_guard(raw: dict[str, Any]) -> AnomalyGuardConfig:
    cfg = AnomalyGuardConfig()
    min_cycle_repeated_turns = _get(raw, "min_cycle_repeated_turns", _get(raw, "min_ping_pong_turns", cfg.min_cycle_repeated_turns))
    return AnomalyGuardConfig(
        enabled=bool(_get(raw, "enabled", cfg.enabled)),
        window_lines=max(20, int(_get(raw, "window_lines", cfg.window_lines))),
        probe_timeout_seconds=max(3, int(_get(raw, "probe_timeout_seconds", cfg.probe_timeout_seconds))),
        keywords_stop=[str(x).strip() for x in _get(raw, "keywords_stop", cfg.keywords_stop)],
        keywords_repeat=[str(x).strip() for x in _get(raw, "keywords_repeat", cfg.keywords_repeat)],
        max_repeat_same_signature=max(2, int(_get(raw, "max_repeat_same_signature", cfg.max_repeat_same_signature))),
        min_cycle_repeated_turns=max(2, int(min_cycle_repeated_turns)),
        max_cycle_period=max(2, int(_get(raw, "max_cycle_period", cfg.max_cycle_period))),
        stagnation_enabled=bool(_get(raw, "stagnation_enabled", cfg.stagnation_enabled)),
        stagnation_min_events=max(4, int(_get(raw, "stagnation_min_events", cfg.stagnation_min_events))),
        stagnation_min_roles=max(1, int(_get(raw, "stagnation_min_roles", cfg.stagnation_min_roles))),
        stagnation_max_novel_cluster_ratio=max(
            0.05,
            min(
                1.0,
                float(_get(raw, "stagnation_max_novel_cluster_ratio", cfg.stagnation_max_novel_cluster_ratio)),
            ),
        ),
        min_signature_chars=max(8, int(_get(raw, "min_signature_chars", cfg.min_signature_chars))),
        auto_dispatch_check=bool(_get(raw, "auto_dispatch_check", cfg.auto_dispatch_check)),
        dispatch_window_lines=max(1, int(_get(raw, "dispatch_window_lines", cfg.dispatch_window_lines))),
        keywords_dispatch=[str(x).strip() for x in _get(raw, "keywords_dispatch", cfg.keywords_dispatch)],
        min_post_dispatch_unexpected_turns=max(
            2,
            int(_get(raw, "min_post_dispatch_unexpected_turns", cfg.min_post_dispatch_unexpected_turns)),
        ),
        keywords_architect_active=[
            str(x).strip() for x in _get(raw, "keywords_architect_active", cfg.keywords_architect_active)
        ],
        similarity_enabled=bool(_get(raw, "similarity_enabled", cfg.similarity_enabled)),
        similarity_threshold=max(0.5, min(1.0, float(_get(raw, "similarity_threshold", cfg.similarity_threshold)))),
        similarity_min_chars=max(6, int(_get(raw, "similarity_min_chars", cfg.similarity_min_chars))),
        max_similar_repeat=max(2, int(_get(raw, "max_similar_repeat", cfg.max_similar_repeat))),
    )


def _parse_notify(raw: dict[str, Any]) -> NotifyConfig:
    cfg = NotifyConfig()
    send_timeout_seconds = max(5, int(_get(raw, "send_timeout_seconds", cfg.send_timeout_seconds)))
    read_timeout_seconds = max(5, int(_get(raw, "read_timeout_seconds", send_timeout_seconds)))
    return NotifyConfig(
        channel=str(_get(raw, "channel", cfg.channel)),
        account=str(_get(raw, "account", cfg.account)),
        target=str(_get(raw, "target", cfg.target)),
        silent=bool(_get(raw, "silent", cfg.silent)),
        send_timeout_seconds=send_timeout_seconds,
        read_timeout_seconds=read_timeout_seconds,
        ask_enable_ai=bool(_get(raw, "ask_enable_ai", cfg.ask_enable_ai)),
        ask_timeout_seconds=max(15, int(_get(raw, "ask_timeout_seconds", cfg.ask_timeout_seconds))),
        poll_interval_seconds=max(1, int(_get(raw, "poll_interval_seconds", cfg.poll_interval_seconds))),
        read_limit=max(1, int(_get(raw, "read_limit", cfg.read_limit))),
        operator_user_ids=[str(x).strip() for x in _get(raw, "operator_user_ids", cfg.operator_user_ids)],
    )


def _parse_ai(raw: dict[str, Any]) -> AiConfig:
    cfg = AiConfig()
    return AiConfig(
        enabled=bool(_get(raw, "enabled", cfg.enabled)),
        provider=str(_get(raw, "provider", cfg.provider)),
        command=str(_get(raw, "command", cfg.command)),
        args=list(_get(raw, "args", cfg.args)),
        model=_get(raw, "model", cfg.model),
        timeout_seconds=max(1, int(_get(raw, "timeout_seconds", cfg.timeout_seconds))),
        max_attempts_per_day=max(0, int(_get(raw, "max_attempts_per_day", cfg.max_attempts_per_day))),
        cooldown_seconds=max(0, int(_get(raw, "cooldown_seconds", cfg.cooldown_seconds))),
        allow_code_changes=bool(_get(raw, "allow_code_changes", cfg.allow_code_changes)),
        args_code=list(_get(raw, "args_code", cfg.args_code)),
    )


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
    return AppConfig(
        monitor=monitor,
        openclaw=openclaw,
        repair=repair,
        anomaly_guard=anomaly_guard,
        notify=notify,
        ai=ai,
    )


def write_default_config(path: str, *, overwrite: bool = False) -> Path:
    p = _as_path(path)
    if p.exists() and not overwrite:
        return p
    ensure_dir(p.parent)
    p.write_text(DEFAULT_CONFIG_TOML, encoding="utf-8")
    return p
