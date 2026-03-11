"""Main anomaly detection service entry point."""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

from ..shared import redact_text
from .cluster import assign_clusters
from .detectors import (
    assign_clusters as detectors_assign_clusters,
    cycle_match_to_dict,
    run_cycle_detector,
    run_handoff_violation_detector,
    run_self_repeat_detector,
    run_stagnation_detector,
    scan_anomaly_guard_events,
    stagnation_match_to_dict,
)
from .extractors import extract_events, build_transcript_snapshot, build_log_snapshot
from .models import DetectorFinding

if TYPE_CHECKING:
    from ..config import AppConfig
    from ..runtime import CmdResult


def _analyze_from_lines(
    cfg: "AppConfig",
    *,
    lines_all: list[str],
    source: str,
    probe_ok: bool,
    probe_exit_code: int | None = None,
    probe_error: str | None = None,
    extra_metrics: dict[str, Any] | None = None,
    extra_signals: dict[str, bool] | None = None,
    extra_findings: tuple[DetectorFinding, ...] = (),
) -> dict:
    """Analyze lines for anomalies."""
    lines = lines_all[-cfg.anomaly_guard.window_lines :]
    events = detectors_assign_clusters(cfg, extract_events(lines, cfg))

    stop_tokens = [x.lower() for x in cfg.anomaly_guard.keywords_stop if x]
    repeat_tokens = [x.lower() for x in cfg.anomaly_guard.keywords_repeat if x]
    dispatch_tokens = [x.lower() for x in cfg.anomaly_guard.keywords_dispatch if x]

    signal_scan = scan_anomaly_guard_events(
        cfg,
        events,
        stop_tokens=stop_tokens,
        repeat_tokens=repeat_tokens,
        dispatch_tokens=dispatch_tokens,
    )
    self_repeat = run_self_repeat_detector(cfg, events, signatures=signal_scan["signatures"])
    cycle = run_cycle_detector(cfg, events)
    handoff = run_handoff_violation_detector(
        cfg,
        events,
        dispatch_events=signal_scan["dispatch_events"],
    )
    stagnation = run_stagnation_detector(cfg, events)

    triggered = (
        cycle["cycle_trigger"]
        or handoff["trigger"]
        or self_repeat["repeat_trigger"]
        or self_repeat["similar_repeat_trigger"]
        or stagnation["trigger"]
        or any(finding.triggered for finding in extra_findings)
    )
    detectors = [
        finding.to_json()
        for finding in [
            *self_repeat["findings"],
            cycle["finding"],
            handoff["finding"],
            stagnation["finding"],
            *extra_findings,
        ]
    ]

    metrics = {
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
        "cycle_event": cycle_match_to_dict(cycle["match"]),
        "repeat_event": cycle_match_to_dict(self_repeat["exact_match"]),
        "similar_repeat_event": cycle_match_to_dict(self_repeat["similar_match"]),
        "stagnation_event": stagnation_match_to_dict(stagnation["match"]),
        "auto_dispatch_event": handoff["event"],
    }
    if extra_metrics:
        metrics.update(extra_metrics)

    signals = {
        "repeat_trigger": self_repeat["repeat_trigger"],
        "similar_repeat_trigger": self_repeat["similar_repeat_trigger"],
        "ping_pong_trigger": cycle["ping_pong_trigger"],
        "cycle_trigger": cycle["cycle_trigger"],
        "stagnation_trigger": stagnation["trigger"],
        "auto_dispatch_trigger": handoff["trigger"],
    }
    if extra_signals:
        signals.update(extra_signals)

    result = {
        "enabled": True,
        "triggered": triggered,
        "source": source,
        "probe_ok": probe_ok,
        "metrics": metrics,
        "signals": signals,
        "detectors": detectors,
    }
    if probe_exit_code is not None:
        result["probe_exit_code"] = probe_exit_code
    if probe_error is not None:
        result["probe_error"] = probe_error
    return result


def _analyze_anomaly_guard(
    cfg: "AppConfig",
    *,
    logs: "CmdResult | None" = None,
    transcripts: list[dict[str, Any]] | None = None,
) -> dict:
    """Main entry point for anomaly detection.

    Args:
        cfg: Application configuration
        logs: Optional log command result
        transcripts: Optional list of transcript dictionaries

    Returns:
        Anomaly detection result dictionary
    """
    log_metrics: dict[str, Any] = {}
    log_findings: tuple[DetectorFinding, ...] = ()
    log_signals: dict[str, bool] = {}
    log_lines_all: list[str] | None = None
    logs_available = False

    if logs is not None:
        log_result = logs
        if not log_result.ok:
            if not transcripts:
                return {
                    "enabled": True,
                    "triggered": False,
                    "source": "logs",
                    "sources": ["logs"],
                    "probe_ok": False,
                    "probe_exit_code": log_result.exit_code,
                    "probe_error": redact_text(log_result.stderr or log_result.stdout),
                }
        else:
            logs_available = True
            merged = log_result.stdout + (("\n" + log_result.stderr) if log_result.stderr else "")
            log_lines_all = [ln for ln in merged.splitlines() if ln.strip()]
            log_metrics, log_findings, log_signals = build_log_snapshot(cfg, log_lines_all)

    if transcripts:
        transcript_lines, transcript_metrics, transcript_findings, transcript_signals = build_transcript_snapshot(
            cfg,
            transcripts,
        )
        combined_metrics = dict(transcript_metrics)
        combined_metrics.update(log_metrics)
        combined_signals = dict(transcript_signals)
        combined_signals.update(log_signals)
        combined_findings = (*transcript_findings, *log_findings)
        return _analyze_from_lines(
            cfg,
            lines_all=transcript_lines,
            source="combined" if logs_available else "transcript",
            probe_ok=True,
            extra_metrics=combined_metrics,
            extra_signals=combined_signals,
            extra_findings=combined_findings,
        )

    if logs is None:
        raise ValueError("anomaly guard requires logs or transcripts")
    return _analyze_from_lines(
        cfg,
        lines_all=log_lines_all or [],
        source="logs",
        probe_ok=True,
        probe_exit_code=log_result.exit_code,
        extra_metrics=log_metrics,
        extra_signals=log_signals,
        extra_findings=log_findings,
    )
