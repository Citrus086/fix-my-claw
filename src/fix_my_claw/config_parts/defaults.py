"""Default values and constants for configuration."""
from __future__ import annotations

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
# OpenClaw accountId used for `openclaw message send/read --account`.
# This is NOT the Discord bot user id / mention id.
# Target for notifications. For Discord, use "channel:YOUR_CHANNEL_ID" or "user:YOUR_USER_ID".
# You must configure this to receive alerts.
target = "channel:YOUR_DISCORD_CHANNEL_ID"
# Discord user id that channel replies must explicitly mention.
# When target is channel:..., fill this explicitly; fix-my-claw no longer auto-detects it.
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
# If target is channel:..., reply should mention required_mention_id (for example, "<@BOT_USER_ID> yes").
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
