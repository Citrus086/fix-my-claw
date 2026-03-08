from __future__ import annotations

import difflib
import re
import threading
from collections import Counter
from dataclasses import dataclass, field, replace
from typing import Any

from .config import AppConfig
from .runtime import CmdResult
from .shared import redact_text


def _build_role_aliases_from_config(cfg: AppConfig) -> dict[str, tuple[str, ...]]:
    """Build ROLE_ALIASES from config, with fallback to defaults."""
    return dict(cfg.agent_roles.roles)


def _build_agent_roles_from_config(cfg: AppConfig) -> frozenset[str]:
    """Build AGENT_ROLES (canonical role names) from config."""
    return cfg.agent_roles.get_canonical_roles()


def _build_all_aliases_from_config(cfg: AppConfig) -> frozenset[str]:
    """Build ALL_ROLE_ALIASES (all alias strings) from config."""
    return cfg.agent_roles.get_all_aliases()


# Module-level caches for performance (updated when config changes)
# Use config content hash as key instead of id() to avoid issues with object reuse
_cached_config_hash: str | None = None
_cached_role_aliases: dict[str, tuple[str, ...]] | None = None
_cached_agent_roles: frozenset[str] | None = None
_cached_all_aliases: frozenset[str] | None = None
_cache_lock = threading.Lock()


def _config_hash(cfg: AppConfig) -> str:
    """Compute a hash of the agent_roles config for cache invalidation.
    
    Using content hash instead of id() avoids issues where Python reuses
    memory addresses for different config objects.
    """
    # Hash based on agent_roles content since that's what we cache
    roles = cfg.agent_roles.roles
    # Sort for deterministic hash
    items = tuple((k, tuple(sorted(v))) for k, v in sorted(roles.items()))
    return str(hash(items))


def _refresh_caches_if_needed(cfg: AppConfig) -> None:
    """Refresh all caches if config has changed.

    This ensures all three caches are updated atomically when the config changes,
    preventing stale cache data from being used after a config switch.
    """
    global _cached_config_hash, _cached_role_aliases, _cached_agent_roles, _cached_all_aliases
    config_hash = _config_hash(cfg)
    with _cache_lock:
        if _cached_config_hash != config_hash:
            # Config changed - refresh ALL caches atomically
            _cached_config_hash = config_hash
            _cached_role_aliases = _build_role_aliases_from_config(cfg)
            _cached_agent_roles = _build_agent_roles_from_config(cfg)
            _cached_all_aliases = _build_all_aliases_from_config(cfg)


def _get_role_aliases(cfg: AppConfig) -> dict[str, tuple[str, ...]]:
    """Get role aliases, using cache if config hasn't changed."""
    _refresh_caches_if_needed(cfg)
    with _cache_lock:
        # Cache is guaranteed to be valid after refresh
        return _cached_role_aliases if _cached_role_aliases is not None else {}


def _get_agent_roles(cfg: AppConfig) -> frozenset[str]:
    """Get canonical agent roles, using cache if config hasn't changed."""
    _refresh_caches_if_needed(cfg)
    with _cache_lock:
        # Cache is guaranteed to be valid after refresh
        return _cached_agent_roles if _cached_agent_roles is not None else frozenset()


def _get_all_aliases(cfg: AppConfig) -> frozenset[str]:
    """Get all role aliases, using cache if config hasn't changed."""
    _refresh_caches_if_needed(cfg)
    with _cache_lock:
        # Cache is guaranteed to be valid after refresh
        return _cached_all_aliases if _cached_all_aliases is not None else frozenset()


@dataclass(frozen=True)
class Event:
    line_index: int
    speaker_role: str
    raw_text: str
    content_text: str
    normalized_text: str
    cluster_key: str = ""
    cluster_representative: str = ""


@dataclass(frozen=True)
class CycleMatch:
    period: int
    repetitions: int
    repeated_turns: int
    start_event_index: int
    end_event_index: int
    involved_roles: tuple[str, ...]
    line_indexes: tuple[int, ...]
    raw_lines: tuple[str, ...]
    pattern: tuple[tuple[str, str], ...]
    cluster_representatives: tuple[str, ...]


@dataclass(frozen=True)
class StagnationMatch:
    event_count: int
    distinct_cluster_count: int
    novel_cluster_ratio: float
    start_event_index: int
    end_event_index: int
    involved_roles: tuple[str, ...]
    line_indexes: tuple[int, ...]
    raw_lines: tuple[str, ...]
    cluster_representatives: tuple[str, ...]
    dominant_cluster_representative: str
    dominant_cluster_count: int


@dataclass(frozen=True)
class DetectorFinding:
    detector: str
    triggered: bool
    involved_roles: tuple[str, ...] = ()
    evidence: tuple[dict[str, Any], ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        out = {
            "detector": self.detector,
            "triggered": self.triggered,
            "involved_roles": list(self.involved_roles),
            "evidence": list(self.evidence),
        }
        out.update(self.details)
        return out


def _normalize_loop_line(line: str) -> str:
    s = line.strip().lower()
    s = re.sub(r"\b[0-9a-f]{6,}\b", "<id>", s)
    s = re.sub(r"\b\d+\b", "<n>", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _strip_log_prefixes(line: str, cfg: AppConfig) -> str:
    s = line.strip().lower()
    all_aliases = _get_all_aliases(cfg)
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


def _strip_speaker_prefix(line: str, speaker_role: str, cfg: AppConfig) -> str:
    s = _strip_log_prefixes(line, cfg)
    role_aliases = _get_role_aliases(cfg)
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


def _normalize_event_text(text: str) -> str:
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


def _extract_progress_markers(text: str) -> tuple[str, ...]:
    markers = re.findall(
        r"\b(step|batch|phase|round|attempt|item|chunk|page|part|iteration|pass|stage)\s+(\d+)\b",
        text,
    )
    return tuple(f"{kind}:{number}" for kind, number in markers)


def _progress_markers_compatible(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    if not left and not right:
        return True
    return left == right


def _extract_events(lines: list[str], cfg: AppConfig) -> list[Event]:
    events: list[Event] = []
    agent_roles = _get_agent_roles(cfg)
    for idx, raw in enumerate(lines):
        speaker_role = _extract_speaker_role(raw, cfg)
        if speaker_role not in agent_roles:
            continue
        content_text = _strip_speaker_prefix(raw, speaker_role, cfg)
        normalized_text = _normalize_event_text(content_text or raw)
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


def _find_token_index(text: str, token: str) -> int:
    if not token:
        return -1
    if re.search(r"[a-z0-9_]", token):
        match = re.search(rf"(?<![a-z0-9_]){re.escape(token)}(?![a-z0-9_])", text)
        return match.start() if match else -1
    return text.find(token)


def _extract_speaker_role(line: str, cfg: AppConfig) -> str | None:
    s = _strip_log_prefixes(line, cfg)
    role_aliases = _get_role_aliases(cfg)
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


def _extract_role(line: str, cfg: AppConfig) -> str | None:
    speaker = _extract_speaker_role(line, cfg)
    if speaker:
        return speaker
    role_aliases = _get_role_aliases(cfg)
    for role, aliases in role_aliases.items():
        if any(_find_token_index(line, alias) >= 0 for alias in aliases):
            return role
    return None


def _contains_any(text: str, tokens: list[str]) -> bool:
    return any(_find_token_index(text, t) >= 0 for t in tokens if t)


def _extract_handoff_target_role(
    line: str,
    cfg: AppConfig,
    *,
    dispatch_tokens: list[str],
    speaker_role: str,
) -> str | None:
    dispatch_hit: tuple[int, str] | None = None
    for token in dispatch_tokens:
        idx = _find_token_index(line, token)
        if idx >= 0 and (dispatch_hit is None or idx < dispatch_hit[0]):
            dispatch_hit = (idx, token)
    if dispatch_hit is None:
        return None

    tail = line[dispatch_hit[0] + len(dispatch_hit[1]) :]
    target_hit: tuple[int, str] | None = None
    agent_roles = _get_agent_roles(cfg)
    role_aliases = _get_role_aliases(cfg)
    for role in agent_roles:
        if role == speaker_role:
            continue
        for alias in role_aliases.get(role, ()):
            idx = _find_token_index(tail, alias)
            if idx >= 0 and (target_hit is None or idx < target_hit[0]):
                target_hit = (idx, role)
    return target_hit[1] if target_hit else None


def _find_unexpected_post_dispatch_streak(
    events: list[Event],
    *,
    start_idx: int,
    start_line_index: int,
    expected_role: str,
    max_lines: int,
    min_turns: int,
) -> dict[str, Any] | None:
    streak_role: str | None = None
    streak_count = 0
    for event in events[start_idx + 1 :]:
        if event.line_index - start_line_index > max_lines:
            break
        speaker_role = event.speaker_role
        if speaker_role == expected_role:
            streak_role = None
            streak_count = 0
            continue
        if speaker_role == streak_role:
            streak_count += 1
        else:
            streak_role = speaker_role
            streak_count = 1
        if streak_count >= min_turns:
            return {
                "unexpected_role": speaker_role,
                "turns": streak_count,
                "unexpected_line_index": event.line_index,
                "unexpected_line": event.raw_text,
            }
    return None


def _calc_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _find_similar_group(
    signature: str,
    groups: list[dict[str, Any]],
    threshold: float,
    progress_markers: tuple[str, ...],
) -> dict[str, Any] | None:
    for group in groups:
        if not _progress_markers_compatible(progress_markers, group["progress_markers"]):
            continue
        if _calc_similarity(signature, group["representative"]) >= threshold:
            return group
    return None


def _assign_clusters(cfg: AppConfig, events: list[Event]) -> list[Event]:
    if not cfg.anomaly_guard.similarity_enabled:
        return events

    groups: list[dict[str, Any]] = []
    clustered: list[Event] = []
    for event in events:
        text = event.normalized_text
        if len(text) < cfg.anomaly_guard.similarity_min_chars:
            clustered.append(event)
            continue
        progress_markers = _extract_progress_markers(text)
        group = _find_similar_group(
            text,
            groups,
            cfg.anomaly_guard.similarity_threshold,
            progress_markers,
        )
        if group is None:
            group = {
                "key": f"cluster:{len(groups) + 1}",
                "representative": text,
                "progress_markers": progress_markers,
            }
            groups.append(group)
        clustered.append(
            replace(
                event,
                cluster_key=str(group["key"]),
                cluster_representative=str(group["representative"]),
            )
        )
    return clustered


def _find_cycle_match(
    events: list[Event],
    *,
    key_fn: Any,
    min_period: int,
    max_period: int,
) -> CycleMatch | None:
    best: CycleMatch | None = None
    if len(events) < min_period * 2:
        return None

    for start_idx in range(len(events) - 1):
        longest_period = min(max_period, (len(events) - start_idx) // 2)
        for period in range(min_period, longest_period + 1):
            pattern = tuple(key_fn(event) for event in events[start_idx : start_idx + period])
            if not pattern or any(not entry for entry in pattern):
                continue
            repetitions = 1
            cursor = start_idx + period
            while cursor + period <= len(events):
                candidate = tuple(key_fn(event) for event in events[cursor : cursor + period])
                if candidate != pattern:
                    break
                repetitions += 1
                cursor += period
            if repetitions < 2:
                continue
            run_events = events[start_idx:cursor]
            match = CycleMatch(
                period=period,
                repetitions=repetitions,
                repeated_turns=len(run_events) - period,
                start_event_index=start_idx,
                end_event_index=cursor - 1,
                involved_roles=tuple(dict.fromkeys(event.speaker_role for event in run_events)),
                line_indexes=tuple(event.line_index for event in run_events),
                raw_lines=tuple(event.raw_text for event in run_events),
                pattern=pattern,
                cluster_representatives=tuple(event.cluster_representative for event in run_events[:period]),
            )
            if best is None or (
                match.repeated_turns,
                match.repetitions,
                -match.period,
                -match.start_event_index,
            ) > (
                best.repeated_turns,
                best.repetitions,
                -best.period,
                -best.start_event_index,
            ):
                best = match
    return best


def _build_evidence(line_indexes: tuple[int, ...], raw_lines: tuple[str, ...]) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "line_index": line_index,
            "raw_text": raw_text,
        }
        for line_index, raw_text in zip(line_indexes, raw_lines)
    )


def _cycle_match_to_dict(match: CycleMatch | None) -> dict[str, Any] | None:
    if match is None:
        return None
    evidence = list(_build_evidence(match.line_indexes, match.raw_lines))
    return {
        "period": match.period,
        "repetitions": match.repetitions,
        "repeated_turns": match.repeated_turns,
        "start_event_index": match.start_event_index,
        "end_event_index": match.end_event_index,
        "involved_roles": list(match.involved_roles),
        "line_indexes": list(match.line_indexes),
        "raw_lines": list(match.raw_lines),
        "cluster_representatives": list(match.cluster_representatives),
        "pattern": [
            {
                "speaker_role": speaker_role,
                "cluster_key": cluster_key,
            }
            for speaker_role, cluster_key in match.pattern
        ],
        "evidence": evidence,
    }


def _find_stagnation_match(
    events: list[Event],
    *,
    min_events: int,
    min_roles: int,
    max_novel_cluster_ratio: float,
) -> StagnationMatch | None:
    best: StagnationMatch | None = None
    if len(events) < min_events:
        return None

    for start_idx in range(0, len(events) - min_events + 1):
        window = events[start_idx:]
        involved_roles = tuple(dict.fromkeys(event.speaker_role for event in window))
        if len(involved_roles) < min_roles:
            continue
        cluster_counts = Counter(event.cluster_key for event in window)
        if not cluster_counts:
            continue
        distinct_cluster_count = len(cluster_counts)
        novel_cluster_ratio = distinct_cluster_count / len(window)
        if novel_cluster_ratio > max_novel_cluster_ratio:
            continue
        dominant_cluster_key, dominant_cluster_count = cluster_counts.most_common(1)[0]
        dominant_cluster_representative = next(
            event.cluster_representative for event in window if event.cluster_key == dominant_cluster_key
        )
        match = StagnationMatch(
            event_count=len(window),
            distinct_cluster_count=distinct_cluster_count,
            novel_cluster_ratio=novel_cluster_ratio,
            start_event_index=start_idx,
            end_event_index=len(events) - 1,
            involved_roles=involved_roles,
            line_indexes=tuple(event.line_index for event in window),
            raw_lines=tuple(event.raw_text for event in window),
            cluster_representatives=tuple(dict.fromkeys(event.cluster_representative for event in window)),
            dominant_cluster_representative=dominant_cluster_representative,
            dominant_cluster_count=dominant_cluster_count,
        )
        if best is None or (
            match.novel_cluster_ratio,
            -match.event_count,
            -match.start_event_index,
        ) < (
            best.novel_cluster_ratio,
            -best.event_count,
            -best.start_event_index,
        ):
            best = match
    return best


def _stagnation_match_to_dict(match: StagnationMatch | None) -> dict[str, Any] | None:
    if match is None:
        return None
    evidence = list(_build_evidence(match.line_indexes, match.raw_lines))
    return {
        "event_count": match.event_count,
        "distinct_cluster_count": match.distinct_cluster_count,
        "novel_cluster_ratio": round(match.novel_cluster_ratio, 4),
        "start_event_index": match.start_event_index,
        "end_event_index": match.end_event_index,
        "involved_roles": list(match.involved_roles),
        "line_indexes": list(match.line_indexes),
        "raw_lines": list(match.raw_lines),
        "cluster_representatives": list(match.cluster_representatives),
        "dominant_cluster_representative": match.dominant_cluster_representative,
        "dominant_cluster_count": match.dominant_cluster_count,
        "evidence": evidence,
    }


def _scan_anomaly_guard_events(
    cfg: AppConfig,
    events: list[Event],
    *,
    stop_tokens: list[str],
    repeat_tokens: list[str],
    dispatch_tokens: list[str],
) -> dict[str, Any]:
    stop_signals = 0
    stop_roles: set[str] = set()
    repeat_signals = 0
    repeat_roles: set[str] = set()
    signatures: Counter[str] = Counter()
    dispatch_events: list[dict[str, Any]] = []

    for event_idx, event in enumerate(events):
        token_text = _normalize_loop_line(event.content_text or event.raw_text)
        is_stop = _contains_any(token_text, stop_tokens)
        is_repeat = _contains_any(token_text, repeat_tokens)

        if is_stop:
            stop_signals += 1
            stop_roles.add(event.speaker_role)
        if is_repeat:
            repeat_signals += 1
            repeat_roles.add(event.speaker_role)

        if len(event.normalized_text) >= cfg.anomaly_guard.min_signature_chars:
            sig_key = f"{event.speaker_role}|{event.normalized_text}"
            signatures[sig_key] += 1

        if cfg.anomaly_guard.auto_dispatch_check and _contains_any(token_text, dispatch_tokens):
            target_role = _extract_handoff_target_role(
                token_text,
                cfg,
                dispatch_tokens=dispatch_tokens,
                speaker_role=event.speaker_role,
            )
            if target_role:
                dispatch_events.append(
                    {
                        "dispatch_event_index": event_idx,
                        "dispatch_line_index": event.line_index,
                        "initiator_role": event.speaker_role,
                        "target_role": target_role,
                        "dispatch_line": event.raw_text,
                    }
                )

    return {
        "stop_signals": stop_signals,
        "stop_roles": tuple(sorted(stop_roles)),
        "repeat_signals": repeat_signals,
        "repeat_roles": tuple(sorted(repeat_roles)),
        "signatures": signatures,
        "dispatch_events": dispatch_events,
    }


def _run_self_repeat_detector(cfg: AppConfig, events: list[Event], *, signatures: Counter[str]) -> dict[str, Any]:
    exact_repeat_match = _find_cycle_match(
        events,
        key_fn=lambda event: (event.speaker_role, event.normalized_text),
        min_period=1,
        max_period=1,
    )
    similar_repeat_match = _find_cycle_match(
        events,
        key_fn=lambda event: (event.speaker_role, event.cluster_key),
        min_period=1,
        max_period=1,
    )

    max_repeat_same_signature = exact_repeat_match.repetitions if exact_repeat_match is not None else 0
    top_signature = signatures.most_common(1)[0][0] if signatures else None
    max_similar_repeats = similar_repeat_match.repetitions if similar_repeat_match is not None else 0
    repeat_trigger = max_repeat_same_signature >= cfg.anomaly_guard.max_repeat_same_signature
    similar_repeat_trigger = (
        cfg.anomaly_guard.similarity_enabled
        and max_similar_repeats >= cfg.anomaly_guard.max_similar_repeat
    )
    top_similar_group: dict[str, Any] | None = None
    if similar_repeat_match is not None:
        top_similar_group = {
            "role": similar_repeat_match.involved_roles[0],
            "representative": similar_repeat_match.cluster_representatives[0],
            "count": similar_repeat_match.repetitions,
        }

    findings = [
        DetectorFinding(
            detector="repeat",
            triggered=repeat_trigger,
            involved_roles=exact_repeat_match.involved_roles if exact_repeat_match is not None else (),
            evidence=_build_evidence(exact_repeat_match.line_indexes, exact_repeat_match.raw_lines)
            if exact_repeat_match is not None
            else (),
            details={
                "period": 1,
                "repetitions": exact_repeat_match.repetitions if exact_repeat_match is not None else 0,
                "repeated_turns": exact_repeat_match.repeated_turns if exact_repeat_match is not None else 0,
                "event": _cycle_match_to_dict(exact_repeat_match),
            },
        ),
        DetectorFinding(
            detector="similar_repeat",
            triggered=similar_repeat_trigger,
            involved_roles=similar_repeat_match.involved_roles if similar_repeat_match is not None else (),
            evidence=_build_evidence(similar_repeat_match.line_indexes, similar_repeat_match.raw_lines)
            if similar_repeat_match is not None
            else (),
            details={
                "period": 1,
                "repetitions": similar_repeat_match.repetitions if similar_repeat_match is not None else 0,
                "repeated_turns": similar_repeat_match.repeated_turns if similar_repeat_match is not None else 0,
                "event": _cycle_match_to_dict(similar_repeat_match),
            },
        ),
    ]
    return {
        "exact_match": exact_repeat_match,
        "similar_match": similar_repeat_match,
        "max_repeat_same_signature": max_repeat_same_signature,
        "top_signature": top_signature,
        "max_similar_repeats": max_similar_repeats,
        "top_similar_group": top_similar_group,
        "repeat_trigger": repeat_trigger,
        "similar_repeat_trigger": similar_repeat_trigger,
        "findings": findings,
    }


def _run_cycle_detector(cfg: AppConfig, events: list[Event]) -> dict[str, Any]:
    cycle_match = _find_cycle_match(
        events,
        key_fn=lambda event: (event.speaker_role, event.cluster_key),
        min_period=2,
        max_period=max(2, cfg.anomaly_guard.max_cycle_period),
    )
    cycle_trigger = (
        cycle_match is not None
        and cycle_match.repeated_turns >= cfg.anomaly_guard.min_cycle_repeated_turns
    )
    ping_pong_trigger = (
        cycle_match is not None
        and cycle_match.period == 2
        and cycle_match.repeated_turns >= cfg.anomaly_guard.min_cycle_repeated_turns
    )
    return {
        "match": cycle_match,
        "cycle_trigger": cycle_trigger,
        "ping_pong_trigger": ping_pong_trigger,
        "cycle_repeated_turns": cycle_match.repeated_turns if cycle_match is not None else 0,
        "ping_pong_turns": cycle_match.repeated_turns if cycle_match is not None and cycle_match.period == 2 else 0,
        "finding": DetectorFinding(
            detector="cycle",
            triggered=cycle_trigger,
            involved_roles=cycle_match.involved_roles if cycle_match is not None else (),
            evidence=_build_evidence(cycle_match.line_indexes, cycle_match.raw_lines) if cycle_match is not None else (),
            details={
                "period": cycle_match.period if cycle_match is not None else 0,
                "repetitions": cycle_match.repetitions if cycle_match is not None else 0,
                "repeated_turns": cycle_match.repeated_turns if cycle_match is not None else 0,
                "ping_pong": ping_pong_trigger,
                "event": _cycle_match_to_dict(cycle_match),
            },
        ),
    }


def _run_handoff_violation_detector(
    cfg: AppConfig,
    events: list[Event],
    *,
    dispatch_events: list[dict[str, Any]],
) -> dict[str, Any]:
    auto_dispatch_trigger = False
    auto_dispatch_event: dict[str, Any] | None = None
    if cfg.anomaly_guard.auto_dispatch_check:
        for event in dispatch_events:
            unexpected = _find_unexpected_post_dispatch_streak(
                events,
                start_idx=int(event["dispatch_event_index"]),
                start_line_index=int(event["dispatch_line_index"]),
                expected_role=str(event["target_role"]),
                max_lines=cfg.anomaly_guard.dispatch_window_lines,
                min_turns=cfg.anomaly_guard.min_post_dispatch_unexpected_turns,
            )
            if unexpected is not None:
                auto_dispatch_trigger = True
                auto_dispatch_event = {k: v for k, v in event.items() if k != "dispatch_event_index"}
                auto_dispatch_event.update(unexpected)
                break

    involved_roles: tuple[str, ...] = ()
    evidence: tuple[dict[str, Any], ...] = ()
    if auto_dispatch_event is not None:
        involved = [
            str(auto_dispatch_event["initiator_role"]),
            str(auto_dispatch_event["target_role"]),
            str(auto_dispatch_event["unexpected_role"]),
        ]
        involved_roles = tuple(dict.fromkeys(involved))
        evidence = (
            {
                "line_index": int(auto_dispatch_event["dispatch_line_index"]),
                "raw_text": str(auto_dispatch_event["dispatch_line"]),
            },
            {
                "line_index": int(auto_dispatch_event["unexpected_line_index"]),
                "raw_text": str(auto_dispatch_event["unexpected_line"]),
            },
        )
    return {
        "trigger": auto_dispatch_trigger,
        "event": auto_dispatch_event,
        "finding": DetectorFinding(
            detector="handoff_violation",
            triggered=auto_dispatch_trigger,
            involved_roles=involved_roles,
            evidence=evidence,
            details={"event": auto_dispatch_event},
        ),
    }


def _run_stagnation_detector(cfg: AppConfig, events: list[Event]) -> dict[str, Any]:
    stagnation_match = (
        _find_stagnation_match(
            events,
            min_events=cfg.anomaly_guard.stagnation_min_events,
            min_roles=cfg.anomaly_guard.stagnation_min_roles,
            max_novel_cluster_ratio=cfg.anomaly_guard.stagnation_max_novel_cluster_ratio,
        )
        if cfg.anomaly_guard.stagnation_enabled
        else None
    )
    stagnation_trigger = stagnation_match is not None
    return {
        "match": stagnation_match,
        "trigger": stagnation_trigger,
        "finding": DetectorFinding(
            detector="stagnation",
            triggered=stagnation_trigger,
            involved_roles=stagnation_match.involved_roles if stagnation_match is not None else (),
            evidence=_build_evidence(stagnation_match.line_indexes, stagnation_match.raw_lines)
            if stagnation_match is not None
            else (),
            details={"event": _stagnation_match_to_dict(stagnation_match)},
        ),
    }


def _analyze_anomaly_guard(cfg: AppConfig, *, logs: CmdResult) -> dict:
    log_result = logs
    merged = log_result.stdout + (("\n" + log_result.stderr) if log_result.stderr else "")
    lines_all = [ln for ln in merged.splitlines() if ln.strip()]
    lines = lines_all[-cfg.anomaly_guard.window_lines :]
    events = _assign_clusters(cfg, _extract_events(lines, cfg))

    stop_tokens = [x.lower() for x in cfg.anomaly_guard.keywords_stop if x]
    repeat_tokens = [x.lower() for x in cfg.anomaly_guard.keywords_repeat if x]
    dispatch_tokens = [x.lower() for x in cfg.anomaly_guard.keywords_dispatch if x]

    if not log_result.ok:
        return {
            "enabled": True,
            "triggered": False,
            "probe_ok": False,
            "probe_exit_code": log_result.exit_code,
            "probe_error": redact_text(log_result.stderr or log_result.stdout),
        }

    signal_scan = _scan_anomaly_guard_events(
        cfg,
        events,
        stop_tokens=stop_tokens,
        repeat_tokens=repeat_tokens,
        dispatch_tokens=dispatch_tokens,
    )
    self_repeat = _run_self_repeat_detector(cfg, events, signatures=signal_scan["signatures"])
    cycle = _run_cycle_detector(cfg, events)
    handoff = _run_handoff_violation_detector(
        cfg,
        events,
        dispatch_events=signal_scan["dispatch_events"],
    )
    stagnation = _run_stagnation_detector(cfg, events)

    triggered = (
        cycle["cycle_trigger"]
        or handoff["trigger"]
        or self_repeat["repeat_trigger"]
        or self_repeat["similar_repeat_trigger"]
        or stagnation["trigger"]
    )
    detectors = [
        finding.to_json()
        for finding in [
            *self_repeat["findings"],
            cycle["finding"],
            handoff["finding"],
            stagnation["finding"],
        ]
    ]

    return {
        "enabled": True,
        "triggered": triggered,
        "probe_ok": True,
        "metrics": {
            "lines_analyzed": len(lines),
            "events_analyzed": len(events),
            "stop_signals": signal_scan["stop_signals"],
            "distinct_stop_roles": list(signal_scan["stop_roles"]),
            "repeat_signals": signal_scan["repeat_signals"],
            "distinct_repeat_roles": list(signal_scan["repeat_roles"]),
            "max_exact_repeat_run_repetitions": self_repeat["max_repeat_same_signature"],
            "max_repeat_same_signature": self_repeat["max_repeat_same_signature"],
            "cycle_repeated_turns": cycle["cycle_repeated_turns"],
            "ping_pong_turns": cycle["ping_pong_turns"],
            "most_common_signature_in_window": self_repeat["top_signature"],
            "top_signature": self_repeat["top_signature"],
            "max_similar_repeat_run_repetitions": self_repeat["max_similar_repeats"],
            "max_similar_repeats": self_repeat["max_similar_repeats"],
            "top_similar_group": self_repeat["top_similar_group"],
            "cycle_event": _cycle_match_to_dict(cycle["match"]),
            "repeat_event": _cycle_match_to_dict(self_repeat["exact_match"]),
            "similar_repeat_event": _cycle_match_to_dict(self_repeat["similar_match"]),
            "stagnation_event": _stagnation_match_to_dict(stagnation["match"]),
            "auto_dispatch_event": handoff["event"],
        },
        "signals": {
            "repeat_trigger": self_repeat["repeat_trigger"],
            "similar_repeat_trigger": self_repeat["similar_repeat_trigger"],
            "ping_pong_trigger": cycle["ping_pong_trigger"],
            "cycle_trigger": cycle["cycle_trigger"],
            "stagnation_trigger": stagnation["trigger"],
            "auto_dispatch_trigger": handoff["trigger"],
        },
        "detectors": detectors,
    }
