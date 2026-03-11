"""Event and snapshot extraction for anomaly detection."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, TYPE_CHECKING

from .models import Event, DetectorFinding
from .role_cache import get_agent_roles, get_role_aliases
from .text_utils import (
    extract_progress_markers,
    extract_speaker_role,
    normalize_event_text,
    strip_speaker_prefix,
)

if TYPE_CHECKING:
    from ..config import AppConfig
    from ..runtime import CmdResult


def extract_events(lines: list[str], cfg: "AppConfig") -> list[Event]:
    """Extract events from log lines."""
    events: list[Event] = []
    agent_roles = get_agent_roles(cfg)
    for idx, raw in enumerate(lines):
        speaker_role = extract_speaker_role(raw, cfg)
        if speaker_role not in agent_roles:
            continue
        content_text = strip_speaker_prefix(raw, speaker_role, cfg)
        normalized_text = normalize_event_text(content_text or raw)
        if not normalized_text:
            continue
        events.append(
            Event(
                line_index=idx,
                speaker_role=speaker_role,
                raw_text=raw,
                content_text=content_text,
                normalized_text=normalized_text,
                cluster_key=normalized_text,
                cluster_representative=normalized_text,
            )
        )
    return events


def resolve_transcript_agent_role(agent_id: str, cfg: "AppConfig") -> str | None:
    """Resolve agent ID to canonical role from transcript."""
    token = agent_id.strip().lower()
    if not token:
        return None
    role_aliases = get_role_aliases(cfg)
    for role, aliases in role_aliases.items():
        if token == role or token in aliases:
            return role
    return None


def extract_transcript_message_text(message: dict[str, Any]) -> str:
    """Extract text content from a transcript message."""
    content = message.get("content", [])
    if not isinstance(content, list):
        return ""
    chunks: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        content_type = str(item.get("type", "")).strip().lower()
        if content_type == "text":
            text = item.get("text")
        elif content_type == "thinking":
            text = item.get("thinking")
        else:
            text = None
        if isinstance(text, str) and text.strip():
            chunks.append(text.strip())
    return "\n".join(chunks)


def extract_sender_id_from_transcript_text(text: str) -> str | None:
    """Extract sender_id from transcript text."""
    match = re.search(r'"sender_id"\s*:\s*"([^"]+)"', text)
    if not match:
        return None
    sender_id = match.group(1).strip()
    return sender_id or None


def extract_sender_metadata_values_from_transcript_text(text: str) -> tuple[str, ...]:
    """Extract sender metadata values from transcript text."""
    values: list[str] = []
    for key in ("sender_id", "id", "sender", "label", "name", "username", "tag"):
        for match in re.finditer(rf'"{key}"\s*:\s*"([^"]+)"', text):
            value = re.sub(r"\s+", " ", match.group(1).strip())
            if value:
                values.append(value)
    return tuple(dict.fromkeys(values))


def sender_metadata_matches_transcript_agent(
    sender_values: tuple[str, ...],
    *,
    agent_id: str,
    speaker_role: str | None,
    cfg: "AppConfig",
) -> bool:
    """Check if sender metadata matches transcript agent."""
    from .text_utils import find_token_index

    if speaker_role is None or not sender_values:
        return False
    candidates = {
        speaker_role,
        agent_id,
        *get_role_aliases(cfg).get(speaker_role, ()),
    }
    normalized_candidates = {
        re.sub(r"\s+", " ", candidate.strip().lower())
        for candidate in candidates
        if isinstance(candidate, str) and candidate.strip()
    }
    if not normalized_candidates:
        return False
    for value in sender_values:
        normalized_value = re.sub(r"\s+", " ", value.strip().lower())
        if not normalized_value:
            continue
        for candidate in normalized_candidates:
            if normalized_value == candidate or find_token_index(normalized_value, candidate) >= 0:
                return True
    return False


def is_reset_marker_text(text: str) -> bool:
    """Check if text is a reset marker."""
    normalized = text.strip().lower()
    return "a new session was started via /new or /reset" in normalized


def is_queued_backfill_text(text: str) -> bool:
    """Check if text is a queued backfill message."""
    normalized = text.strip().lower()
    return "[queued messages while agent was busy]" in normalized or "queued #1" in normalized


def build_transcript_snapshot(
    cfg: "AppConfig",
    transcripts: list[dict[str, Any]],
) -> tuple[list[str], dict[str, Any], tuple[DetectorFinding, ...], dict[str, bool]]:
    """Build snapshot from transcripts."""
    synthesized_lines: list[str] = []
    session_ids: list[str] = []
    session_keys: list[str] = []
    transcript_paths: list[str] = []
    sender_ids: set[str] = set()

    message_count = 0
    assistant_message_count = 0
    user_message_count = 0
    reset_markers = 0
    queued_backfill_messages = 0
    reset_backfill_event: dict[str, Any] | None = None
    self_sender_messages = 0
    self_sender_session_starts = 0
    self_sender_ids: set[str] = set()
    self_sender_events: list[dict[str, Any]] = []

    for transcript in transcripts:
        agent_id = str(transcript.get("agent_id", "")).strip()
        session_id = str(transcript.get("session_id", "")).strip()
        session_key = str(transcript.get("session_key", "")).strip()
        transcript_path = str(transcript.get("transcript_path", "")).strip()
        entries = transcript.get("entries", [])
        if not isinstance(entries, list):
            continue

        if session_id:
            session_ids.append(session_id)
        if session_key:
            session_keys.append(session_key)
        if transcript_path:
            transcript_paths.append(transcript_path)

        speaker_role = resolve_transcript_agent_role(agent_id, cfg)
        pending_reset: dict[str, Any] | None = None
        user_message_ordinal = 0
        for entry_index, entry in enumerate(entries):
            if not isinstance(entry, dict) or entry.get("type") != "message":
                continue
            message = entry.get("message", {})
            if not isinstance(message, dict):
                continue

            message_role = str(message.get("role", "")).strip().lower()
            text = extract_transcript_message_text(message)
            if not text:
                continue
            text_single_line = re.sub(r"\s+", " ", text).strip()
            if not text_single_line:
                continue

            message_count += 1
            if message_role == "assistant":
                assistant_message_count += 1
                if speaker_role is not None:
                    synthesized_lines.append(f"{speaker_role}: {text_single_line}")
                continue

            if message_role != "user":
                continue

            user_message_count += 1
            user_message_ordinal += 1
            sender_id = extract_sender_id_from_transcript_text(text)
            if sender_id:
                sender_ids.add(sender_id)
            sender_values = extract_sender_metadata_values_from_transcript_text(text)

            if sender_metadata_matches_transcript_agent(
                sender_values,
                agent_id=agent_id,
                speaker_role=speaker_role,
                cfg=cfg,
            ):
                self_sender_messages += 1
                if sender_id:
                    self_sender_ids.add(sender_id)
                self_sender_event = {
                    "session_id": session_id or None,
                    "session_key": session_key or None,
                    "transcript_path": transcript_path or None,
                    "message_index": entry_index,
                    "message": text_single_line,
                    "sender_id": sender_id,
                    "sender_values": list(sender_values),
                    "agent_id": agent_id or None,
                    "speaker_role": speaker_role,
                    "first_user_message_in_transcript": user_message_ordinal == 1,
                }
                if len(self_sender_events) < 2:
                    self_sender_events.append(self_sender_event)
                if user_message_ordinal == 1:
                    self_sender_session_starts += 1

            if is_reset_marker_text(text):
                reset_markers += 1
                pending_reset = {
                    "session_id": session_id or None,
                    "session_key": session_key or None,
                    "transcript_path": transcript_path or None,
                    "reset_message_index": entry_index,
                    "reset_message": text_single_line,
                }
                continue

            if is_queued_backfill_text(text):
                queued_backfill_messages += 1
                if pending_reset is not None and reset_backfill_event is None:
                    reset_backfill_event = {
                        **pending_reset,
                        "queued_message_index": entry_index,
                        "queued_message": text_single_line,
                        "queued_sender_id": sender_id,
                    }

    reset_backfill_trigger = reset_backfill_event is not None
    self_sender_ingress_trigger = self_sender_messages >= 2 or self_sender_session_starts >= 1
    evidence: tuple[dict[str, Any], ...] = ()
    if reset_backfill_event is not None:
        evidence = (
            {
                "line_index": int(reset_backfill_event["reset_message_index"]),
                "raw_text": str(reset_backfill_event["reset_message"]),
            },
            {
                "line_index": int(reset_backfill_event["queued_message_index"]),
                "raw_text": str(reset_backfill_event["queued_message"]),
            },
        )
    self_sender_evidence = tuple(
        {
            "line_index": int(event["message_index"]),
            "raw_text": str(event["message"]),
        }
        for event in self_sender_events
    )

    findings = (
        DetectorFinding(
            detector="reset_backfill",
            triggered=reset_backfill_trigger,
            kind="root_cause",
            evidence=evidence,
            details={"event": reset_backfill_event},
        ),
        DetectorFinding(
            detector="self_sender_ingress",
            triggered=self_sender_ingress_trigger,
            kind="root_cause",
            evidence=self_sender_evidence,
            details={
                "event": self_sender_events[0] if self_sender_events else None,
                "events": self_sender_events,
                "sender_ids": sorted(self_sender_ids),
                "session_starts": self_sender_session_starts,
            },
        ),
    )
    metrics = {
        "transcripts_analyzed": len(transcripts),
        "session_boundaries": len(transcripts),
        "transcript_messages_analyzed": message_count,
        "assistant_messages_analyzed": assistant_message_count,
        "user_messages_analyzed": user_message_count,
        "distinct_sender_ids": len(sender_ids),
        "sender_ids": sorted(sender_ids),
        "reset_markers": reset_markers,
        "queued_backfill_messages": queued_backfill_messages,
        "self_sender_messages": self_sender_messages,
        "self_sender_session_starts": self_sender_session_starts,
        "self_sender_ids": sorted(self_sender_ids),
        "self_sender_event": self_sender_events[0] if self_sender_events else None,
        "source_session_ids": session_ids,
        "source_session_keys": session_keys,
        "source_transcript_paths": transcript_paths,
        "reset_backfill_event": reset_backfill_event,
    }
    signals = {
        "reset_backfill_trigger": reset_backfill_trigger,
        "self_sender_ingress_trigger": self_sender_ingress_trigger,
    }
    return synthesized_lines, metrics, findings, signals


def parse_log_timestamp(line: str) -> datetime | None:
    """Parse timestamp from a log line."""
    token = line.strip().split(" ", 1)[0].strip()
    if not token:
        return None
    try:
        parsed = datetime.fromisoformat(token.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def is_discord_identity_degraded_line(line: str) -> bool:
    """Check if line indicates Discord identity degradation."""
    normalized = line.strip().lower()
    return "[discord]" in normalized and "logged in to discord" in normalized and "logged in to discord as " not in normalized


def build_log_snapshot(
    cfg: "AppConfig",
    lines_all: list[str],
    *,
    now: datetime | None = None,
) -> tuple[dict[str, Any], tuple[DetectorFinding, ...], dict[str, bool]]:
    """Build snapshot from log lines."""
    now_utc = now.astimezone(timezone.utc) if now is not None else datetime.now(timezone.utc)
    recent_cutoff = now_utc - timedelta(minutes=30)
    lines = lines_all[-cfg.anomaly_guard.window_lines :]
    identity_events: list[dict[str, Any]] = []

    for line_index, raw_line in enumerate(lines):
        if not is_discord_identity_degraded_line(raw_line):
            continue
        timestamp = parse_log_timestamp(raw_line)
        if timestamp is not None and timestamp < recent_cutoff:
            continue
        identity_events.append(
            {
                "line_index": line_index,
                "raw_text": raw_line,
                "timestamp": timestamp.isoformat() if timestamp is not None else None,
            }
        )

    identity_trigger = bool(identity_events)
    findings = (
        DetectorFinding(
            detector="discord_identity_degraded",
            triggered=identity_trigger,
            kind="root_cause",
            evidence=tuple(
                {
                    "line_index": int(event["line_index"]),
                    "raw_text": str(event["raw_text"]),
                }
                for event in identity_events[:2]
            ),
            details={
                "event": identity_events[0] if identity_events else None,
                "events": identity_events[:2],
            },
        ),
    )
    metrics = {
        "discord_identity_degraded_events": len(identity_events),
        "discord_identity_degraded_event": identity_events[0] if identity_events else None,
        "logs_recent_window_minutes": 30,
    }
    signals = {
        "discord_identity_degraded_trigger": identity_trigger,
    }
    return metrics, findings, signals
