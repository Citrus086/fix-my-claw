from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import Any

from .shared import _read_json_file, _write_json_file, ensure_dir

_NOTIFICATION_EVENTS_NAME = "notification_events.json"
_NOTIFICATION_EVENTS_LOCK_NAME = "notification_events.lock"
_MAX_NOTIFICATION_EVENTS = 200


def _notification_events_path(state_dir: Path) -> Path:
    return state_dir / _NOTIFICATION_EVENTS_NAME


def _notification_events_lock_path(state_dir: Path) -> Path:
    return state_dir / _NOTIFICATION_EVENTS_LOCK_NAME


def _load_notification_events_unlocked(path: Path) -> list[dict[str, Any]]:
    payload = _read_json_file(path)
    if not isinstance(payload, dict):
        return []
    raw_events = payload.get("events")
    if not isinstance(raw_events, list):
        return []
    events: list[dict[str, Any]] = []
    for item in raw_events:
        if isinstance(item, dict):
            events.append(dict(item))
    events.sort(key=lambda item: int(item.get("sequence") or 0))
    return events


def list_notification_events(state_dir: Path) -> list[dict[str, Any]]:
    return _load_notification_events_unlocked(_notification_events_path(state_dir))


def _find_latest_event_by_dedupe_key(state_dir: Path, *, dedupe_key: str | None) -> dict[str, Any] | None:
    if not dedupe_key:
        return None
    events = list_notification_events(state_dir)
    if not events:
        return None
    latest = events[-1]
    if str(latest.get("dedupe_key") or "").strip() != dedupe_key:
        return None
    return latest


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def _acquire_notification_events_lock(state_dir: Path) -> int:
    ensure_dir(state_dir)
    lock_path = _notification_events_lock_path(state_dir)
    last_error: FileExistsError | None = None
    for _ in range(100):
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            last_error = exc
            time.sleep(0.05)
            continue
        os.write(fd, str(os.getpid()).encode("utf-8"))
        return fd
    raise TimeoutError(f"timed out waiting for notification events lock: {lock_path}") from last_error


def _release_notification_events_lock(state_dir: Path, fd: int) -> None:
    try:
        os.close(fd)
    except OSError:
        pass
    _notification_events_lock_path(state_dir).unlink(missing_ok=True)


def _append_notification_event(
    state_dir: Path,
    *,
    kind: str,
    source: str,
    level: str | None = None,
    message_text: str | None = None,
    local_title: str | None = None,
    local_body: str | None = None,
    channel: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
) -> dict[str, Any]:
    ensure_dir(state_dir)
    lock_fd = _acquire_notification_events_lock(state_dir)
    try:
        path = _notification_events_path(state_dir)
        events = _load_notification_events_unlocked(path)
        last_sequence = int(events[-1].get("sequence") or 0) if events else 0
        event = {
            "sequence": last_sequence + 1,
            "event_id": uuid.uuid4().hex,
            "timestamp": time.time(),
            "kind": kind,
            "source": source,
        }
        if level:
            event["level"] = level
        if message_text:
            event["message_text"] = message_text
        if local_title:
            event["local_title"] = local_title
        if local_body:
            event["local_body"] = local_body
        if channel is not None:
            event["channel"] = _json_safe(channel)
        if dedupe_key:
            event["dedupe_key"] = dedupe_key

        events.append(event)
        if len(events) > _MAX_NOTIFICATION_EVENTS:
            events = events[-_MAX_NOTIFICATION_EVENTS:]
        _write_json_file(path, {"events": events})
        return event
    finally:
        _release_notification_events_lock(state_dir, lock_fd)


def emit_local_notification_event(
    state_dir: Path,
    *,
    kind: str,
    source: str,
    local_title: str,
    local_body: str,
    message_text: str | None = None,
    dedupe_key: str | None = None,
) -> dict[str, Any]:
    duplicate = _find_latest_event_by_dedupe_key(state_dir, dedupe_key=dedupe_key)
    if duplicate is not None:
        return duplicate
    return _append_notification_event(
        state_dir,
        kind=kind,
        source=source,
        message_text=message_text,
        local_title=local_title,
        local_body=local_body,
        dedupe_key=dedupe_key,
    )


def dispatch_notification_event(
    state_dir: Path,
    *,
    kind: str,
    source: str,
    level: str | None,
    message_text: str,
    send_channel: bool,
    notify_channel_fn: Any,
    cfg: Any,
    silent: bool | None = None,
    local_title: str | None = None,
    local_body: str | None = None,
    dedupe_key: str | None = None,
) -> dict[str, Any] | None:
    duplicate = _find_latest_event_by_dedupe_key(state_dir, dedupe_key=dedupe_key)
    if duplicate is not None:
        channel = duplicate.get("channel")
        return channel if isinstance(channel, dict) else None
    channel_result: dict[str, Any] | None = None
    if send_channel:
        channel_result = notify_channel_fn(cfg, message_text, silent=silent)
        if not isinstance(channel_result, dict):
            channel_result = None
    event = _append_notification_event(
        state_dir,
        kind=kind,
        source=source,
        level=level,
        message_text=message_text,
        local_title=local_title,
        local_body=local_body,
        channel=channel_result,
        dedupe_key=dedupe_key,
    )
    if channel_result is None:
        return None
    return {
        **channel_result,
        "event_id": event["event_id"],
        "sequence": event["sequence"],
    }


def _clean_fix_my_claw_message(text: str | None) -> str | None:
    if text is None:
        return None
    cleaned = text.strip()
    if not cleaned:
        return None
    prefix = "fix-my-claw:"
    if cleaned.startswith(prefix):
        cleaned = cleaned[len(prefix):].strip()
    return cleaned or None


def _extract_message_text_from_notification_payload(payload: dict[str, Any] | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    argv = payload.get("argv")
    if not isinstance(argv, list):
        return None
    try:
        message_index = argv.index("--message") + 1
    except ValueError:
        return None
    if message_index >= len(argv):
        return None
    message_text = argv[message_index]
    if not isinstance(message_text, str):
        return None
    return message_text


def _repair_result_identity_key(details: dict[str, Any], *, attempted: bool, fixed: bool, used_ai: bool) -> str:
    attempt_dir = str(details.get("attempt_dir") or "").strip()
    if attempt_dir:
        return f"attempt:{attempt_dir}"
    if details.get("already_healthy"):
        return "already_healthy"
    if details.get("repair_disabled"):
        return "repair_disabled"
    if details.get("cooldown"):
        return f"cooldown:{details.get('cooldown_remaining_seconds')}"
    return f"attempted:{attempted}:fixed:{fixed}:used_ai:{used_ai}"


def _build_repair_result_local_notification(result: Any) -> tuple[str, str]:
    details = getattr(result, "details", {}) or {}
    final_notice = _clean_fix_my_claw_message(
        _extract_message_text_from_notification_payload(details.get("notify_final"))
    )

    if details.get("already_healthy"):
        return ("ℹ️ 无需修复", final_notice or "系统已处于健康状态，本轮未执行修复。")
    if details.get("repair_disabled"):
        return ("⏸️ 自动修复已禁用", final_notice or "repair.enabled=false，本轮未执行修复。")
    if details.get("cooldown"):
        remaining = details.get("cooldown_remaining_seconds")
        remaining_text = f"{remaining} 秒" if remaining is not None else "未知"
        return ("⏳ 修复冷却中", f"修复冷却期尚未结束，剩余 {remaining_text}。")
    backup_error = str(details.get("backup_before_ai_error") or "").strip()
    if backup_error:
        return ("❌ 备份失败", final_notice or f"已收到 AI 修复批准，但备份失败：{backup_error}")
    ai_stage = str(details.get("ai_stage") or "").strip()
    official_break_reason = str(details.get("official_break_reason") or "").strip()
    if getattr(result, "fixed", False):
        if ai_stage == "code":
            return ("✅ AI 代码修复成功", final_notice or "AI 代码修复后系统恢复健康。")
        if ai_stage == "config":
            return ("✅ AI 配置修复成功", final_notice or "AI 配置修复后系统恢复健康。")
        if official_break_reason == "healthy":
            return ("✅ 官方修复成功", final_notice or "官方修复后系统恢复健康。")
        if details.get("pause_wait_seconds") is not None:
            return ("✅ PAUSE 后已恢复", final_notice or "发送 PAUSE 并复检后系统恢复健康。")
        return ("✅ 修复成功", final_notice or "系统恢复健康。")

    ai_decision = details.get("ai_decision")
    decision = str(ai_decision.get("decision") or "").strip() if isinstance(ai_decision, dict) else ""
    if decision == "rate_limited":
        return ("⏳ AI 修复已限流", final_notice or "已达到 AI 修复次数或冷却限制，本轮不进入 AI 修复。")
    if decision == "no":
        return ("⏭️ 已拒绝 AI 修复", final_notice or "收到明确 no，本轮不进入 AI 修复。")
    if decision == "timeout":
        return ("⏱️ AI 审批超时", final_notice or "等待 AI 审批超时，本轮不进入 AI 修复。")
    if decision == "invalid_limit":
        invalid_replies = ai_decision.get("invalid_replies") if isinstance(ai_decision, dict) else None
        invalid_text = str(invalid_replies) if invalid_replies is not None else "多次"
        return ("⚠️ AI 审批无效", final_notice or f"连续 {invalid_text} 次收到无效回复，本轮不进入 AI 修复。")
    if decision == "send_failed":
        error = str(ai_decision.get("error") or "未知错误") if isinstance(ai_decision, dict) else "未知错误"
        return ("❌ 审批消息发送失败", final_notice or f"无法发送 AI 审批消息：{error}")
    if decision == "skip":
        return ("⏭️ 已跳过 AI 审批", final_notice or "notify.ask_enable_ai=false，本轮跳过 AI 修复审批。")
    if getattr(result, "attempted", False):
        return ("❌ 修复结束但仍异常", final_notice or "本轮修复已结束，但系统仍未恢复健康。")
    return ("ℹ️ 修复结果已更新", final_notice or "已收到修复结果。")


def emit_repair_result_event(state_dir: Path, *, result: Any) -> dict[str, Any]:
    title, body = _build_repair_result_local_notification(result)
    details = getattr(result, "details", {}) or {}
    return emit_local_notification_event(
        state_dir,
        kind="repair_result",
        source="repair",
        local_title=title,
        local_body=body,
        dedupe_key=_repair_result_identity_key(
            details,
            attempted=bool(getattr(result, "attempted", False)),
            fixed=bool(getattr(result, "fixed", False)),
            used_ai=bool(getattr(result, "used_ai", False)),
        ),
    )
