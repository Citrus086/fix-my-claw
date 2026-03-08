"""
Centralized notification message constants for fix-my-claw.

All user-visible notification texts starting with 'fix-my-claw:' are defined here.
This module only contains message strings and simple formatting functions.
"""

# AI decision notification messages
def ai_decision_yes(source: str) -> str:
    """Notification text when user approves AI repair."""
    return f"fix-my-claw: 已收到 {source} 的 yes，开始备份并准备 Codex 修复。"


def ai_decision_no(source: str) -> str:
    """Notification text when user declines AI repair."""
    return f"fix-my-claw: 已收到 {source} 的 no，本轮不会启用 Codex 修复。"


# Backup stage messages
def backup_completed(archive_path: str) -> str:
    """Notification text when backup is completed."""
    return f"fix-my-claw: 已完成备份，开始 Codex 修复。备份文件：{archive_path}"


# Repair pipeline messages
REPAIR_STARTING = (
    "fix-my-claw: 检测到异常，开始分层修复"
    "（会话可达时先发送 PAUSE 保留现场；若仍异常，再升级到 /stop -> /new -> 官方结构修复）。"
)

REPAIR_STARTING_MANUAL = (
    "fix-my-claw: 收到手动修复命令，开始分层修复"
    "（会话可达时先发送 PAUSE 保留现场；若仍异常，再升级到 /stop -> /new -> 官方结构修复）。"
)

REPAIR_RECOVERED_AFTER_PAUSE = (
    "fix-my-claw: 已发送 PAUSE 并完成复检，系统恢复健康，跳过 /stop、/new 与结构修复。"
)

REPAIR_RECOVERED_BY_OFFICIAL = (
    "fix-my-claw: 分层修复已完成，系统恢复健康，无需启用 Codex 修复。"
)

REPAIR_AI_DISABLED = (
    "fix-my-claw: 官方修复后仍异常，且 ai.enabled=false，"
    "本轮不会发起 yes/no 与 Codex 修复，请人工介入。"
)

REPAIR_AI_RATE_LIMITED = (
    "fix-my-claw: Codex 修复被限流（每日次数或冷却期），本轮跳过。"
)

REPAIR_NO_YES_RECEIVED = (
    "fix-my-claw: 未收到 yes（含 no/timeout/发送失败/多次无效回复），"
    "本轮不会启用 Codex 修复。"
)

def repair_backup_failed(error: str) -> str:
    """Notification text when backup fails."""
    return f"fix-my-claw: 收到 yes，但备份失败，已停止 Codex 修复。错误：{error}"


REPAIR_AI_CONFIG_SUCCESS = (
    "fix-my-claw: Codex 配置阶段修复成功，系统恢复健康。"
)

REPAIR_AI_CODE_SUCCESS = (
    "fix-my-claw: Codex 代码阶段修复成功，系统恢复健康。"
)

REPAIR_FINAL_STILL_UNHEALTHY = (
    "fix-my-claw: 本轮修复结束，但系统仍异常，请人工介入排查。"
)


# AI approval request messages (used in notify.py)
def ask_enable_ai_prompt(account: str) -> str:
    """Prompt message for asking user to enable AI repair."""
    return (
        "fix-my-claw: 已执行分层修复（必要时含 PAUSE 复检、/stop、/new 与官方结构修复），当前仍异常。"
        f"是否启用 Codex 修复？请 @{account} 回复 是/否（Please answer with yes/no）。"
        "（回复 yes/是 将先备份整个 ~/.openclaw 到其上级目录）"
    )


def ask_invalid_reply(remaining: int) -> str:
    """Notification text when user sends an invalid reply."""
    return f"fix-my-claw: 未识别到有效回复。请仅回复 是/否（Please answer with yes/no）。剩余 {remaining} 次。"


def manual_repair_acknowledged(command: str) -> str:
    """Notification text when manual repair command is received."""
    return f"fix-my-claw: 收到手动修复命令「{command}」，立即开始修复流程。"
