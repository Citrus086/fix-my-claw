"""Text processing utilities for anomaly detection."""
from __future__ import annotations

import difflib
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import AppConfig


def normalize_loop_line(line: str) -> str:
    """Normalize a line for loop detection."""
    s = line.strip().lower()
    s = re.sub(r"\b[0-9a-f]{6,}\b", "<id>", s)
    s = re.sub(r"\b\d+\b", "<n>", s)
    s = re.sub(r"\s+", " ", s)
    return s


def strip_log_prefixes(line: str, cfg: "AppConfig") -> str:
    """Strip log prefixes (timestamps, brackets) from a line."""
    from .role_cache import get_all_aliases

    s = line.strip().lower()
    all_aliases = get_all_aliases(cfg)
    while True:
        stripped = False
        if bracket_match := re.match(r"^\[([^\]]+)\]\s*", s):
            prefix = bracket_match.group(1).strip()
            if prefix not in all_aliases:
                s = s[bracket_match.end() :]
                stripped = True
        if timestamp_match := re.match(r"^\d{4}-\d{2}-\d{2}[ t]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?\s+", s):
            s = s[timestamp_match.end() :]
            stripped = True
        if not stripped:
            break
    return s


def strip_speaker_prefix(line: str, speaker_role: str, cfg: "AppConfig") -> str:
    """Strip speaker prefix from a line."""
    from .role_cache import get_role_aliases

    s = strip_log_prefixes(line, cfg)
    role_aliases = get_role_aliases(cfg)
    for alias in role_aliases.get(speaker_role, ()):
        prefixes = (
            f"{alias}:",
            f"{alias}：",
            f"{alias} ",
            f"{alias}>",
            f"{alias}-",
            f"[{alias}]",
            f"[{alias}] ",
        )
        if s == alias:
            return ""
        for prefix in prefixes:
            if s.startswith(prefix):
                return s[len(prefix) :].strip()
    return s


def normalize_event_text(text: str) -> str:
    """Normalize event text for comparison."""
    s = text.strip().lower()
    s = re.sub(
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
        "<id>",
        s,
    )
    s = re.sub(r"\b[0-9a-f]{10,}\b", "<id>", s)
    s = re.sub(r"\b\d{4,}\b", "<big-n>", s)
    s = re.sub(r"\s+", " ", s)
    return s


def extract_progress_markers(text: str) -> tuple[str, ...]:
    """Extract progress markers from text."""
    markers = re.findall(
        r"\b(step|batch|phase|round|attempt|item|chunk|page|part|iteration|pass|stage)\s+(\d+)\b",
        text,
    )
    return tuple(f"{kind}:{number}" for kind, number in markers)


def progress_markers_compatible(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    """Check if two progress marker sets are compatible."""
    if not left and not right:
        return True
    return left == right


def find_token_index(text: str, token: str) -> int:
    """Find token index with word boundary checking."""
    if not token:
        return -1
    if re.search(r"[a-z0-9_]", token):
        match = re.search(rf"(?<![a-z0-9_]){re.escape(token)}(?![a-z0-9_])", text)
        return match.start() if match else -1
    return text.find(token)


def contains_any(text: str, tokens: list[str]) -> bool:
    """Check if text contains any of the tokens."""
    return any(find_token_index(text, t) >= 0 for t in tokens if t)


def calc_similarity(a: str, b: str) -> float:
    """Calculate similarity between two strings."""
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def extract_speaker_role(line: str, cfg: "AppConfig") -> str | None:
    """Extract speaker role from a line."""
    from .role_cache import get_role_aliases

    s = strip_log_prefixes(line, cfg)
    role_aliases = get_role_aliases(cfg)
    for role, aliases in role_aliases.items():
        for alias in aliases:
            prefixes = (
                f"{alias}:",
                f"{alias}：",
                f"{alias} ",
                f"{alias}>",
                f"{alias}-",
                f"[{alias}]",
                f"[{alias}] ",
            )
            if s == alias or any(s.startswith(prefix) for prefix in prefixes):
                return role
    return None


def extract_role(line: str, cfg: "AppConfig") -> str | None:
    """Extract role from a line (speaker or mentioned)."""
    from .role_cache import get_role_aliases

    speaker = extract_speaker_role(line, cfg)
    if speaker:
        return speaker
    role_aliases = get_role_aliases(cfg)
    for role, aliases in role_aliases.items():
        if any(find_token_index(line, alias) >= 0 for alias in aliases):
            return role
    return None
