"""Repair module facade.

This module serves as the public entry point for repair functionality.
All types, helpers, and stages are defined in separate modules:
- repair_types.py: Result models and type helpers
- repair_ops.py: Operational helper implementations
- repair_hooks.py: Hook assembly for the state machine
- stages/: Individual stage implementations

The module re-exports everything needed for backward compatibility.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from . import repair_ops
from .anomaly_guard import _analyze_anomaly_guard
from .config import AppConfig
from .health import HealthEvaluation, probe_health, probe_logs, probe_status
from .notification_events import dispatch_notification_event
from .notify import _ask_user_enable_ai, _notify_send
from .repair_hooks import (
    NOTIFY_LEVEL_ALL,
    NOTIFY_LEVEL_CRITICAL,
    NOTIFY_LEVEL_IMPORTANT,
    _should_notify,
    build_repair_state_machine_hooks,
)
from .repair_types import (
    AiDecision,
    AiRepairStageData,
    BackupArtifact,
    CommandExecutionRecord,
    OfficialRepairStageData,
    PauseCheckStageData,
    RepairOutcome,
    RepairPipelineContext,
    RepairResult,
    SessionStageData,
    StagePayload,
    StageResult,
    _cmd_result_to_json,
    _coerce_execution_records,
    _records_to_json,
    _require_stage_payload,
)
from .runtime import CmdResult, run_cmd
from .repair_state_machine import (
    RepairMessageHooks,
    RepairRuntimeHooks,
    RepairStageHooks,
    RepairStateMachine,
    RepairStateMachineHooks,
)
from .shared import (
    _parse_json_maybe,
    _write_attempt_file,
    clear_repair_progress,
    ensure_dir,
    redact_text,
    truncate_for_log,
    write_repair_progress as _write_repair_progress_impl,
)

# Re-export write_repair_progress for stages to use (test compatibility)
write_repair_progress = _write_repair_progress_impl

from .stages import (
    AiDecisionStage,
    AiRepairStage,
    BackupStage,
    FinalAssessmentStage,
    OfficialRepairStage,
    PauseAssessmentStage,
    SessionPauseStage,
    SessionResetStage,
    SessionTerminateAssessmentStage,
    SessionTerminateStage,
)
from .state import StateStore, _now_ts

# =============================================================================
# Public API - primary exports for external callers
# =============================================================================

PUBLIC_API_EXPORTS = [
    "attempt_repair",
    "RepairResult",
    "RepairOutcome",
    "RepairPipelineContext",
    "StageResult",
    "write_repair_progress",
    "clear_repair_progress",
]

# =============================================================================
# Compat Type Exports - dataclass models from repair_types.py
# =============================================================================

COMPAT_TYPE_EXPORTS = [
    "AiDecision",
    "AiRepairStageData",
    "BackupArtifact",
    "CommandExecutionRecord",
    "OfficialRepairStageData",
    "PauseCheckStageData",
    "SessionStageData",
    "StagePayload",
]

COMPAT_TYPE_HELPER_EXPORTS = [
    "_cmd_result_to_json",
    "_coerce_execution_records",
    "_records_to_json",
    "_require_stage_payload",
]

# =============================================================================
# Compat Notify Exports - notification helpers from repair_hooks.py
# =============================================================================

COMPAT_NOTIFY_EXPORTS = [
    "NOTIFY_LEVEL_ALL",
    "NOTIFY_LEVEL_IMPORTANT",
    "NOTIFY_LEVEL_CRITICAL",
    "_should_notify",
    "_dispatch_notification",
    "_ask_user_enable_ai",
]

# =============================================================================
# Compat Operation Exports - wrappers around repair_ops.py
# =============================================================================

COMPAT_OPERATION_EXPORTS = [
    "_parse_agent_id_from_session_key",
    "_list_active_sessions",
    "_probe_session_transcripts",
    "_backup_openclaw_state",
    "_run_session_command_stage",
    "_attempt_dir",
    "_context_logs_timeout_seconds",
    "_evaluate_with_context",
    "_collect_context",
    "_evaluate_health",
    "_run_official_steps",
    "_load_prompt_text",
    "_build_ai_cmd",
    "_run_ai_repair",
    "_session_stage_has_successful_commands",
    "_should_try_soft_pause",
    "_ai_decision_source_label",
    "_ai_decision_notification_text",
]

# =============================================================================
# Compat Dependency Exports - re-exports from other modules
# =============================================================================

COMPAT_DEPENDENCY_EXPORTS = [
    "probe_health",
    "probe_logs",
    "probe_status",
    "_notify_send",
    "run_cmd",
    "HealthEvaluation",
    "CmdResult",
    "_analyze_anomaly_guard",
    "_now_ts",
]

# =============================================================================
# Compat Stage Exports - stage classes from stages/
# =============================================================================

COMPAT_STAGE_EXPORTS = [
    "SessionPauseStage",
    "SessionTerminateStage",
    "SessionResetStage",
    "PauseAssessmentStage",
    "OfficialRepairStage",
    "AiDecisionStage",
    "BackupStage",
    "AiRepairStage",
    "FinalAssessmentStage",
]

__all__ = [
    *PUBLIC_API_EXPORTS,
    *COMPAT_TYPE_EXPORTS,
    *COMPAT_TYPE_HELPER_EXPORTS,
    *COMPAT_NOTIFY_EXPORTS,
    *COMPAT_OPERATION_EXPORTS,
    *COMPAT_DEPENDENCY_EXPORTS,
    *COMPAT_STAGE_EXPORTS,
]

# =============================================================================
# Re-exports from repair_ops.py
# =============================================================================

_ai_decision_source_label = repair_ops._ai_decision_source_label
_ai_decision_notification_text = repair_ops._ai_decision_notification_text
_build_ai_cmd = repair_ops._build_ai_cmd
_context_logs_timeout_seconds = repair_ops._context_logs_timeout_seconds
_load_prompt_text = repair_ops._load_prompt_text
_parse_agent_id_from_session_key = repair_ops._parse_agent_id_from_session_key
_session_stage_has_successful_commands = repair_ops._session_stage_has_successful_commands
_should_try_soft_pause = repair_ops._should_try_soft_pause


# =============================================================================
# Notification Dispatch
# =============================================================================


def _dispatch_notification(
    cfg: AppConfig,
    *,
    kind: str,
    source: str,
    text: str,
    level: str,
    silent: bool | None = None,
    local_title: str | None = None,
    local_body: str | None = None,
    dedupe_key: str | None = None,
) -> dict[str, Any] | None:
    return dispatch_notification_event(
        cfg.monitor.state_dir,
        kind=kind,
        source=source,
        level=level,
        message_text=text,
        send_channel=_should_notify(cfg, level),
        notify_channel_fn=_notify_send,
        cfg=cfg,
        silent=silent,
        local_title=local_title,
        local_body=local_body,
        dedupe_key=dedupe_key,
    )


# =============================================================================
# Operation Wrappers - inject dependencies into repair_ops functions
# =============================================================================


def _list_active_sessions(cfg: AppConfig, *, active_minutes: int) -> list[dict[str, Any]]:
    return repair_ops._list_active_sessions(
        cfg,
        active_minutes=active_minutes,
        run_cmd_fn=run_cmd,
        parse_json_maybe_fn=_parse_json_maybe,
    )


def _backup_openclaw_state(cfg: AppConfig, attempt_dir: Path) -> dict[str, Any]:
    return repair_ops._backup_openclaw_state(
        cfg,
        attempt_dir,
        write_attempt_file_fn=_write_attempt_file,
    )


def _probe_session_transcripts(cfg: AppConfig) -> list[dict[str, Any]]:
    return repair_ops._probe_session_transcripts(
        cfg,
        list_active_sessions_fn=_list_active_sessions,
    )


def _run_session_command_stage(
    cfg: AppConfig,
    attempt_dir: Path,
    *,
    stage_name: str,
    message_text: str,
) -> list[dict[str, Any]]:
    return repair_ops._run_session_command_stage(
        cfg,
        attempt_dir,
        stage_name=stage_name,
        message_text=message_text,
        list_active_sessions_fn=_list_active_sessions,
        parse_agent_id_from_session_key_fn=_parse_agent_id_from_session_key,
        run_cmd_fn=run_cmd,
        write_attempt_file_fn=_write_attempt_file,
        redact_text_fn=redact_text,
    )


def _attempt_dir(cfg: AppConfig) -> Path:
    return repair_ops._attempt_dir(cfg, ensure_dir_fn=ensure_dir)


def _collect_context(evaluation: HealthEvaluation, attempt_dir: Path, *, stage_name: str) -> dict[str, Any]:
    return repair_ops._collect_context(
        evaluation,
        attempt_dir,
        stage_name=stage_name,
        write_attempt_file_fn=_write_attempt_file,
        redact_text_fn=redact_text,
    )


def _evaluate_health(
    cfg: AppConfig,
    *,
    log_probe_failures: bool = False,
    capture_logs: bool = False,
    logs_timeout_seconds: int | None = None,
) -> HealthEvaluation:
    return repair_ops._evaluate_health(
        cfg,
        log_probe_failures=log_probe_failures,
        capture_logs=capture_logs,
        logs_timeout_seconds=logs_timeout_seconds,
        probe_health_fn=probe_health,
        probe_status_fn=probe_status,
        probe_logs_fn=probe_logs,
        probe_session_transcripts_fn=_probe_session_transcripts,
        analyze_anomaly_guard_fn=_analyze_anomaly_guard,
    )


def _evaluate_with_context(
    cfg: AppConfig,
    attempt_dir: Path,
    *,
    stage_name: str,
    log_probe_failures: bool = False,
) -> tuple[HealthEvaluation, dict[str, Any]]:
    return repair_ops._evaluate_with_context(
        cfg,
        attempt_dir,
        stage_name=stage_name,
        log_probe_failures=log_probe_failures,
        evaluate_health_fn=_evaluate_health,
        context_logs_timeout_seconds_fn=_context_logs_timeout_seconds,
        collect_context_fn=_collect_context,
    )


def _run_official_steps(
    cfg: AppConfig,
    attempt_dir: Path,
    *,
    break_on_healthy: bool = True,
) -> tuple[list[dict[str, Any]], HealthEvaluation, str]:
    return repair_ops._run_official_steps(
        cfg,
        attempt_dir,
        break_on_healthy=break_on_healthy,
        run_cmd_fn=run_cmd,
        write_attempt_file_fn=_write_attempt_file,
        redact_text_fn=redact_text,
        truncate_for_log_fn=truncate_for_log,
        evaluate_health_fn=_evaluate_health,
        context_logs_timeout_seconds_fn=_context_logs_timeout_seconds,
        sleep_fn=time.sleep,
    )


def _run_ai_repair(cfg: AppConfig, attempt_dir: Path, *, code_stage: bool) -> CmdResult:
    return repair_ops._run_ai_repair(
        cfg,
        attempt_dir,
        code_stage=code_stage,
        load_prompt_text_fn=_load_prompt_text,
        build_ai_cmd_fn=_build_ai_cmd,
        run_cmd_fn=run_cmd,
        write_attempt_file_fn=_write_attempt_file,
        redact_text_fn=redact_text,
        truncate_for_log_fn=truncate_for_log,
    )


def _result_from_outcome(*, attempted: bool, outcome: RepairOutcome) -> RepairResult:
    return RepairResult(
        attempted=attempted,
        fixed=outcome.fixed,
        used_ai=outcome.used_ai,
        outcome=outcome,
    )


# =============================================================================
# Hook Assembly
# =============================================================================


def _build_repair_state_machine_hooks() -> RepairStateMachineHooks:
    """Build hooks for RepairStateMachine using local wrappers."""
    return build_repair_state_machine_hooks(
        # Runtime hooks
        attempt_dir_fn=_attempt_dir,
        clear_repair_progress_fn=clear_repair_progress,
        collect_context_fn=_collect_context,
        context_logs_timeout_seconds_fn=_context_logs_timeout_seconds,
        evaluate_health_fn=_evaluate_health,
        dispatch_notification_fn=_dispatch_notification,
        now_ts_fn=_now_ts,
        require_stage_payload_fn=_require_stage_payload,
        result_from_outcome_fn=_result_from_outcome,
        session_stage_has_successful_commands_fn=_session_stage_has_successful_commands,
        should_try_soft_pause_fn=_should_try_soft_pause,
        write_repair_progress_fn=write_repair_progress,
        # Stage classes
        session_pause_stage_cls=SessionPauseStage,
        pause_assessment_stage_cls=PauseAssessmentStage,
        session_terminate_stage_cls=SessionTerminateStage,
        terminate_assessment_stage_cls=SessionTerminateAssessmentStage,
        session_reset_stage_cls=SessionResetStage,
        official_repair_stage_cls=OfficialRepairStage,
        ai_decision_stage_cls=AiDecisionStage,
        backup_stage_cls=BackupStage,
        ai_repair_stage_cls=AiRepairStage,
        final_assessment_stage_cls=FinalAssessmentStage,
    )


# =============================================================================
# Public Entry Point
# =============================================================================


def attempt_repair(
    cfg: AppConfig,
    store: StateStore,
    *,
    force: bool,
    reason: str | None = None,
) -> RepairResult:
    """Attempt to repair OpenClaw using the configured repair pipeline."""
    return RepairStateMachine(
        cfg=cfg,
        store=store,
        force=force,
        reason=reason,
        manual_start=bool(reason and reason.startswith("manual_")),
        reassess_after_terminate=(reason == repair_ops.QUEUE_CONTAMINATION_REPAIR_REASON),
        hooks=_build_repair_state_machine_hooks(),
    ).run()
