"""Anomaly detectors for loop detection."""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
from typing import Any, TYPE_CHECKING

from .models import Event, CycleMatch, StagnationMatch, DetectorFinding
from .role_cache import get_agent_roles, get_role_aliases
from .text_utils import (
    calc_similarity,
    contains_any,
    extract_progress_markers,
    find_token_index,
    normalize_loop_line,
    progress_markers_compatible,
)

if TYPE_CHECKING:
    from ..config import AppConfig


def find_similar_group(
    signature: str,
    groups: list[dict[str, Any]],
    threshold: float,
    progress_markers: tuple[str, ...],
) -> dict[str, Any] | None:
    """Find a similar group for a signature."""
    for group in groups:
        if not progress_markers_compatible(progress_markers, group["progress_markers"]):
            continue
        if calc_similarity(signature, group["representative"]) >= threshold:
            return group
    return None


def assign_clusters(cfg: "AppConfig", events: list[Event]) -> list[Event]:
    """Assign cluster keys to events based on similarity."""
    if not cfg.anomaly_guard.similarity_enabled:
        return events

    groups: list[dict[str, Any]] = []
    clustered: list[Event] = []
    for event in events:
        text = event.normalized_text
        if len(text) < cfg.anomaly_guard.similarity_min_chars:
            clustered.append(event)
            continue
        markers = extract_progress_markers(text)
        group = find_similar_group(
            text,
            groups,
            cfg.anomaly_guard.similarity_threshold,
            markers,
        )
        if group is None:
            group = {
                "key": f"cluster:{len(groups) + 1}",
                "representative": text,
                "progress_markers": markers,
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


def extract_handoff_target_role(
    line: str,
    cfg: "AppConfig",
    *,
    dispatch_tokens: list[str],
    speaker_role: str,
) -> str | None:
    """Extract target role from a dispatch line."""
    dispatch_hit: tuple[int, str] | None = None
    for token in dispatch_tokens:
        idx = find_token_index(line, token)
        if idx >= 0 and (dispatch_hit is None or idx < dispatch_hit[0]):
            dispatch_hit = (idx, token)
    if dispatch_hit is None:
        return None

    tail = line[dispatch_hit[0] + len(dispatch_hit[1]) :]
    target_hit: tuple[int, str] | None = None
    agent_roles = get_agent_roles(cfg)
    role_aliases = get_role_aliases(cfg)
    for role in agent_roles:
        if role == speaker_role:
            continue
        for alias in role_aliases.get(role, ()):
            idx = find_token_index(tail, alias)
            if idx >= 0 and (target_hit is None or idx < target_hit[0]):
                target_hit = (idx, role)
    return target_hit[1] if target_hit else None


def find_unexpected_post_dispatch_streak(
    events: list[Event],
    *,
    start_idx: int,
    start_line_index: int,
    expected_role: str,
    max_lines: int,
    min_turns: int,
) -> dict[str, Any] | None:
    """Find unexpected role streak after dispatch."""
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


def find_cycle_match(
    events: list[Event],
    *,
    key_fn: Any,
    min_period: int,
    max_period: int,
) -> CycleMatch | None:
    """Find cycle pattern in events."""
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


def build_evidence(line_indexes: tuple[int, ...], raw_lines: tuple[str, ...]) -> tuple[dict[str, Any], ...]:
    """Build evidence from line indexes and raw lines."""
    return tuple(
        {
            "line_index": line_index,
            "raw_text": raw_text,
        }
        for line_index, raw_text in zip(line_indexes, raw_lines)
    )


def cycle_match_to_dict(match: CycleMatch | None) -> dict[str, Any] | None:
    """Convert CycleMatch to dictionary."""
    if match is None:
        return None
    evidence = list(build_evidence(match.line_indexes, match.raw_lines))
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


def find_stagnation_match(
    events: list[Event],
    *,
    min_events: int,
    min_roles: int,
    max_novel_cluster_ratio: float,
) -> StagnationMatch | None:
    """Find stagnation pattern in events."""
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


def stagnation_match_to_dict(match: StagnationMatch | None) -> dict[str, Any] | None:
    """Convert StagnationMatch to dictionary."""
    if match is None:
        return None
    evidence = list(build_evidence(match.line_indexes, match.raw_lines))
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


def scan_anomaly_guard_events(
    cfg: "AppConfig",
    events: list[Event],
    *,
    stop_tokens: list[str],
    repeat_tokens: list[str],
    dispatch_tokens: list[str],
) -> dict[str, Any]:
    """Scan events for anomaly signals."""
    stop_signals = 0
    stop_roles: set[str] = set()
    repeat_signals = 0
    repeat_roles: set[str] = set()
    signatures: Counter[str] = Counter()
    dispatch_events: list[dict[str, Any]] = []

    for event_idx, event in enumerate(events):
        token_text = normalize_loop_line(event.content_text or event.raw_text)
        is_stop = contains_any(token_text, stop_tokens)
        is_repeat = contains_any(token_text, repeat_tokens)

        if is_stop:
            stop_signals += 1
            stop_roles.add(event.speaker_role)
        if is_repeat:
            repeat_signals += 1
            repeat_roles.add(event.speaker_role)

        if len(event.normalized_text) >= cfg.anomaly_guard.min_signature_chars:
            sig_key = f"{event.speaker_role}|{event.normalized_text}"
            signatures[sig_key] += 1

        if cfg.anomaly_guard.auto_dispatch_check and contains_any(token_text, dispatch_tokens):
            target_role = extract_handoff_target_role(
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


def run_self_repeat_detector(cfg: "AppConfig", events: list[Event], *, signatures: Counter[str]) -> dict[str, Any]:
    """Run self-repeat detector."""
    exact_repeat_match = find_cycle_match(
        events,
        key_fn=lambda event: (event.speaker_role, event.normalized_text),
        min_period=1,
        max_period=1,
    )
    similar_repeat_match = find_cycle_match(
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
            evidence=build_evidence(exact_repeat_match.line_indexes, exact_repeat_match.raw_lines)
            if exact_repeat_match is not None
            else (),
            details={
                "period": 1,
                "repetitions": exact_repeat_match.repetitions if exact_repeat_match is not None else 0,
                "repeated_turns": exact_repeat_match.repeated_turns if exact_repeat_match is not None else 0,
                "event": cycle_match_to_dict(exact_repeat_match),
            },
        ),
        DetectorFinding(
            detector="similar_repeat",
            triggered=similar_repeat_trigger,
            involved_roles=similar_repeat_match.involved_roles if similar_repeat_match is not None else (),
            evidence=build_evidence(similar_repeat_match.line_indexes, similar_repeat_match.raw_lines)
            if similar_repeat_match is not None
            else (),
            details={
                "period": 1,
                "repetitions": similar_repeat_match.repetitions if similar_repeat_match is not None else 0,
                "repeated_turns": similar_repeat_match.repeated_turns if similar_repeat_match is not None else 0,
                "event": cycle_match_to_dict(similar_repeat_match),
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


def run_cycle_detector(cfg: "AppConfig", events: list[Event]) -> dict[str, Any]:
    """Run cycle detector."""
    cycle_match = find_cycle_match(
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
            evidence=build_evidence(cycle_match.line_indexes, cycle_match.raw_lines) if cycle_match is not None else (),
            details={
                "period": cycle_match.period if cycle_match is not None else 0,
                "repetitions": cycle_match.repetitions if cycle_match is not None else 0,
                "repeated_turns": cycle_match.repeated_turns if cycle_match is not None else 0,
                "ping_pong": ping_pong_trigger,
                "event": cycle_match_to_dict(cycle_match),
            },
        ),
    }


def run_handoff_violation_detector(
    cfg: "AppConfig",
    events: list[Event],
    *,
    dispatch_events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Run handoff violation detector."""
    auto_dispatch_trigger = False
    auto_dispatch_event: dict[str, Any] | None = None
    if cfg.anomaly_guard.auto_dispatch_check:
        for event in dispatch_events:
            unexpected = find_unexpected_post_dispatch_streak(
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


def run_stagnation_detector(cfg: "AppConfig", events: list[Event]) -> dict[str, Any]:
    """Run stagnation detector."""
    stagnation_match = (
        find_stagnation_match(
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
            evidence=build_evidence(stagnation_match.line_indexes, stagnation_match.raw_lines)
            if stagnation_match is not None
            else (),
            details={"event": stagnation_match_to_dict(stagnation_match)},
        ),
    }
