from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from .config import AppConfig
from .messages import ask_enable_ai_prompt, ask_invalid_reply
from .runtime import run_cmd
from .shared import (
    _claim_ai_approval_decision,
    _clear_ai_approval_request,
    _create_ai_approval_request,
    _parse_json_maybe,
    _read_json_file,
    _read_ai_approval_decision,
    _write_json_file,
    _write_attempt_file,
    redact_text,
)

_MANUAL_REPAIR_CURSOR_NAME = "notify.manual_repair.cursor.json"
_KNOWN_NOTIFY_ACCOUNT_IDS = {
    "fixmyclaw": "1479170394580848660",
}


def _get_manual_repair_tokens(cfg: AppConfig) -> frozenset[str]:
    """Get manual repair command tokens from config."""
    return frozenset(cfg.notify.manual_repair_keywords)


def _get_ai_approve_tokens(cfg: AppConfig) -> frozenset[str]:
    """Get AI approval (yes) tokens from config."""
    return frozenset(cfg.notify.ai_approve_keywords)


def _get_ai_reject_tokens(cfg: AppConfig) -> frozenset[str]:
    """Get AI rejection (no) tokens from config."""
    return frozenset(cfg.notify.ai_reject_keywords)


def _notify_send(cfg: AppConfig, text: str, *, silent: bool | None = None) -> dict[str, Any]:
    argv = [
        cfg.openclaw.command,
        "message",
        "send",
        "--channel",
        cfg.notify.channel,
        "--account",
        cfg.notify.account,
        "--target",
        cfg.notify.target,
        "--message",
        text,
        "--json",
    ]
    use_silent = cfg.notify.silent if silent is None else silent
    if use_silent:
        argv.append("--silent")
    cwd = cfg.openclaw.workspace_dir if cfg.openclaw.workspace_dir.exists() else None
    res = run_cmd(argv, timeout_seconds=cfg.notify.send_timeout_seconds, cwd=cwd)
    parsed = _parse_json_maybe(res.stdout)
    message_id = None
    if isinstance(parsed, dict):
        payload = parsed.get("payload")
        if isinstance(payload, dict):
            result = payload.get("result")
            if isinstance(result, dict):
                message_id = result.get("messageId")
    return {
        "sent": res.ok,
        "message_id": str(message_id) if message_id else None,
        "exit_code": res.exit_code,
        "argv": res.argv,
        "stderr": redact_text(res.stderr),
        "stdout": redact_text(res.stdout),
    }


def _notify_read_messages(cfg: AppConfig, *, after_id: str | None = None) -> list[dict[str, Any]]:
    argv = [
        cfg.openclaw.command,
        "message",
        "read",
        "--channel",
        cfg.notify.channel,
        "--account",
        cfg.notify.account,
        "--target",
        cfg.notify.target,
        "--limit",
        str(cfg.notify.read_limit),
        "--json",
    ]
    if after_id:
        argv += ["--after", after_id]
    cwd = cfg.openclaw.workspace_dir if cfg.openclaw.workspace_dir.exists() else None
    res = run_cmd(argv, timeout_seconds=cfg.notify.read_timeout_seconds, cwd=cwd)
    if not res.ok:
        return []
    parsed = _parse_json_maybe(res.stdout)
    if not isinstance(parsed, dict):
        return []
    payload = parsed.get("payload")
    if not isinstance(payload, dict):
        return []
    messages = payload.get("messages", [])
    if not isinstance(messages, list):
        return []
    out: list[dict[str, Any]] = []
    for item in messages:
        if isinstance(item, dict):
            out.append(item)
    return out


def _normalize_name_key(value: str) -> str:
    return re.sub(r"[\s_\-]+", "", value.strip().lower())


def _max_message_id(current: str | None, candidate: str | None) -> str | None:
    ids = [x for x in (current, candidate) if x]
    if not ids:
        return None
    return max(ids, key=lambda x: (1, int(x)) if x.isdigit() else (0, x))


def _normalize_ai_reply_token(text: str) -> str:
    t = re.sub(r"<@!?\d+>", " ", text.strip().lower())
    t = re.sub(r"[ \t\r\n]+", " ", t).strip()
    t = re.sub(r"[。！？!?.,，]+$", "", t).strip()
    return t


def _message_mentions_notify_account(
    cfg: AppConfig, message: dict[str, Any], *, required_mention_id: str | None
) -> bool:
    mentions = message.get("mentions")
    mention_list = mentions if isinstance(mentions, list) else []

    account_key = _normalize_name_key(cfg.notify.account)
    for mention in mention_list:
        if not isinstance(mention, dict):
            continue
        mention_id = str(mention.get("id", "")).strip()
        if required_mention_id and mention_id and mention_id == required_mention_id:
            return True
        for key in ("username", "global_name", "name", "display_name", "nick"):
            raw = mention.get(key)
            if isinstance(raw, str) and raw.strip() and _normalize_name_key(raw) == account_key:
                return True

    if required_mention_id:
        content = str(message.get("content", ""))
        if re.search(rf"<@!?{re.escape(required_mention_id)}>", content):
            return True
    return False


def _default_required_mention_id(cfg: AppConfig) -> str | None:
    configured = cfg.notify.required_mention_id.strip()
    if configured:
        return configured
    return _KNOWN_NOTIFY_ACCOUNT_IDS.get(_normalize_name_key(cfg.notify.account))


def _resolve_sent_message_author_id(cfg: AppConfig, message_id: str | None) -> str | None:
    if not message_id:
        return None
    target = str(message_id).strip()
    if not target:
        return None
    for _ in range(3):
        for msg in _notify_read_messages(cfg):
            if str(msg.get("id", "")).strip() != target:
                continue
            author = msg.get("author")
            if isinstance(author, dict):
                author_id = str(author.get("id", "")).strip()
                if author_id:
                    return author_id
        time.sleep(0.5)
    return None


def _is_ai_reply_candidate(
    cfg: AppConfig, message: dict[str, Any], *, required_mention_id: str | None = None
) -> bool:
    content = str(message.get("content", "")).strip()
    if not content:
        return False
    author = message.get("author", {})
    author_id = str(author.get("id", "")) if isinstance(author, dict) else ""
    is_bot = bool(author.get("bot")) if isinstance(author, dict) else False
    if is_bot:
        return False
    if cfg.notify.operator_user_ids and author_id not in set(cfg.notify.operator_user_ids):
        return False
    if cfg.notify.target.strip().lower().startswith("channel:") and not _message_mentions_notify_account(
        cfg,
        message,
        required_mention_id=required_mention_id,
    ):
        return False
    return True


def _extract_ai_decision(
    cfg: AppConfig, message: dict[str, Any], *, required_mention_id: str | None = None
) -> str | None:
    if not _is_ai_reply_candidate(cfg, message, required_mention_id=required_mention_id):
        return None
    content = _normalize_ai_reply_token(str(message.get("content", "")))
    if content in _get_ai_approve_tokens(cfg):
        return "yes"
    if content in _get_ai_reject_tokens(cfg):
        return "no"
    return None


def _decision_from_shared_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    decision = str(payload.get("decision", "")).strip()
    if not decision:
        return None
    out = dict(payload)
    out["asked"] = True
    out["decision"] = decision
    return out


def _manual_repair_cursor_path(state_dir: Path) -> Path:
    return state_dir / _MANUAL_REPAIR_CURSOR_NAME


def _read_manual_repair_cursor(state_dir: Path) -> str | None:
    payload = _read_json_file(_manual_repair_cursor_path(state_dir))
    if not isinstance(payload, dict):
        return None
    message_id = str(payload.get("last_seen_message_id", "")).strip()
    return message_id or None


def _write_manual_repair_cursor(state_dir: Path, *, last_seen_message_id: str | None) -> None:
    message_id = str(last_seen_message_id or "").strip()
    if not message_id:
        return
    _write_json_file(
        _manual_repair_cursor_path(state_dir),
        {
            "last_seen_message_id": message_id,
            "updated_at": time.time(),
        },
    )


def _extract_manual_repair_command(
    cfg: AppConfig, message: dict[str, Any], *, required_mention_id: str | None = None
) -> dict[str, Any] | None:
    required_mention_id = required_mention_id or _default_required_mention_id(cfg)
    if not _is_ai_reply_candidate(cfg, message, required_mention_id=required_mention_id):
        return None
    content = _normalize_ai_reply_token(str(message.get("content", "")))
    if content not in _get_manual_repair_tokens(cfg):
        return None
    author = message.get("author")
    return {
        "command": "manual_repair",
        "source": "discord",
        "message_id": str(message.get("id", "")).strip() or None,
        "author_id": str((author or {}).get("id", "")).strip() if isinstance(author, dict) else None,
        "content": content,
    }


def _poll_manual_repair_command(cfg: AppConfig) -> dict[str, Any] | None:
    last_seen = _read_manual_repair_cursor(cfg.monitor.state_dir)
    messages = _notify_read_messages(cfg, after_id=last_seen)
    if not messages:
        return None

    next_last_seen = last_seen
    matched_command: dict[str, Any] | None = None
    for msg in messages:
        msg_id = str(msg.get("id", "")).strip()
        if msg_id:
            next_last_seen = _max_message_id(next_last_seen, msg_id)
        if matched_command is None:
            matched_command = _extract_manual_repair_command(cfg, msg)

    if next_last_seen and next_last_seen != last_seen:
        _write_manual_repair_cursor(cfg.monitor.state_dir, last_seen_message_id=next_last_seen)
    return matched_command


def _ask_user_enable_ai(cfg: AppConfig, attempt_dir: Path) -> dict[str, Any]:
    if not cfg.notify.ask_enable_ai:
        return {"asked": False, "decision": "skip"}
    max_invalid_replies = cfg.notify.max_invalid_replies
    prompt = ask_enable_ai_prompt(
        cfg.notify.account,
        yes_keywords=cfg.notify.ai_approve_keywords,
        no_keywords=cfg.notify.ai_reject_keywords,
    )
    try:
        sent = _notify_send(cfg, prompt, silent=False)
    except Exception as exc:
        _write_attempt_file(
            attempt_dir,
            "notify.ask.error.json",
            json.dumps({"error": str(exc), "stage": "send_prompt"}, ensure_ascii=False, indent=2),
        )
        return {"asked": False, "decision": "send_failed", "error": str(exc)}
    message_id = sent.get("message_id")
    try:
        required_mention_id = _resolve_sent_message_author_id(
            cfg,
            str(message_id) if message_id else None,
        )
    except Exception:
        required_mention_id = None
    request_id = f"{attempt_dir.name}-{time.time_ns()}"
    request_payload = _create_ai_approval_request(
        cfg.monitor.state_dir,
        request_id=request_id,
        attempt_dir=attempt_dir,
        prompt=prompt,
        metadata={
            "notify_message_id": str(message_id) if message_id else None,
            "required_mention_id": required_mention_id,
            "notify_account": cfg.notify.account,
        },
    )
    _write_attempt_file(
        attempt_dir,
        "notify.ask.json",
        json.dumps(
            {
                **sent,
                "request_id": request_id,
                "approval_request_path": str((cfg.monitor.state_dir / "ai_approval.active.json").resolve()),
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    _write_attempt_file(
        attempt_dir,
        "notify.ask.mention.json",
        json.dumps(
            {
                "request_id": request_id,
                "required_mention_id": required_mention_id,
                "notify_account": cfg.notify.account,
                "approval_request": request_payload,
            },
            ensure_ascii=False,
            indent=2,
        ),
    )

    deadline = time.monotonic() + cfg.notify.ask_timeout_seconds
    last_seen = str(message_id) if message_id else None
    invalid_replies = 0
    while time.monotonic() < deadline:
        shared_decision = _decision_from_shared_payload(_read_ai_approval_decision(cfg.monitor.state_dir))
        if shared_decision and str(shared_decision.get("request_id", "")).strip() == request_id:
            _write_attempt_file(
                attempt_dir,
                "notify.ask.decision.json",
                json.dumps(shared_decision, ensure_ascii=False, indent=2),
            )
            _clear_ai_approval_request(cfg.monitor.state_dir, request_id=request_id, clear_decision=False)
            return shared_decision
        messages = _notify_read_messages(cfg, after_id=last_seen)
        next_last_seen = last_seen
        for msg in messages:
            msg_id = str(msg.get("id", "")).strip()
            if msg_id:
                next_last_seen = _max_message_id(next_last_seen, msg_id)
            decision = _extract_ai_decision(cfg, msg, required_mention_id=required_mention_id)
            if decision:
                claimed, payload = _claim_ai_approval_decision(
                    cfg.monitor.state_dir,
                    request_id=request_id,
                    decision=decision,
                    source="discord",
                    metadata={
                        "reply_message_id": str(msg.get("id", "")),
                        "reply_author_id": str((msg.get("author") or {}).get("id", "")),
                    },
                )
                out = _decision_from_shared_payload(payload)
                if not out:
                    continue
                if str(out.get("request_id", "")).strip() != request_id:
                    continue
                out["won"] = claimed
                _write_attempt_file(
                    attempt_dir,
                    "notify.ask.decision.json",
                    json.dumps(out, ensure_ascii=False, indent=2),
                )
                return out
            if _is_ai_reply_candidate(
                cfg,
                msg,
                required_mention_id=required_mention_id,
            ):
                invalid_replies += 1
                if invalid_replies >= max_invalid_replies:
                    out = {
                        "asked": True,
                        "decision": "invalid_limit",
                        "invalid_replies": invalid_replies,
                        "reply_message_id": str(msg.get("id", "")),
                        "reply_author_id": str((msg.get("author") or {}).get("id", "")),
                    }
                    _write_attempt_file(
                        attempt_dir,
                        "notify.ask.decision.json",
                        json.dumps(out, ensure_ascii=False, indent=2),
                    )
                    _clear_ai_approval_request(cfg.monitor.state_dir, request_id=request_id, clear_decision=False)
                    return out
                remaining = max_invalid_replies - invalid_replies
                try:
                    _notify_send(
                        cfg,
                        ask_invalid_reply(
                            remaining,
                            yes_keywords=cfg.notify.ai_approve_keywords,
                            no_keywords=cfg.notify.ai_reject_keywords,
                        ),
                        silent=False,
                    )
                except Exception as notify_exc:
                    _write_attempt_file(
                        attempt_dir,
                        "notify.ask.error.json",
                        json.dumps(
                            {"error": str(notify_exc), "stage": "invalid_reply_prompt"},
                            ensure_ascii=False,
                            indent=2,
                        ),
                    )
        last_seen = next_last_seen
        time.sleep(cfg.notify.poll_interval_seconds)

    out = {"asked": True, "decision": "timeout"}
    _write_attempt_file(
        attempt_dir,
        "notify.ask.decision.json",
        json.dumps(out, ensure_ascii=False, indent=2),
    )
    _clear_ai_approval_request(cfg.monitor.state_dir, request_id=request_id, clear_decision=False)
    return out
