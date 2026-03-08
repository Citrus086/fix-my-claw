"""Repair module facade.

This module serves as the public entry point for repair functionality.
All types, helpers, and stages are defined in separate modules:
- repair_types.py: Result models and type helpers
- repair_ops.py: Operational helper implementations
- stages/: Individual stage implementations

The module re-exports everything needed for backward compatibility.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from . import repair_ops
from .anomaly_guard import _analyze_anomaly_guard
from .config import AppConfig
from .health import HealthEvaluation, probe_health, probe_logs, probe_status
from .messages import (
    REPAIR_AI_CODE_SUCCESS,
    REPAIR_AI_CONFIG_SUCCESS,
    REPAIR_AI_DISABLED,
    REPAIR_AI_RATE_LIMITED,
    REPAIR_FINAL_STILL_UNHEALTHY,
    REPAIR_NO_YES_RECEIVED,
    REPAIR_RECOVERED_AFTER_PAUSE,
    REPAIR_RECOVERED_BY_OFFICIAL,
    REPAIR_STARTING,
    REPAIR_STARTING_MANUAL,
    backup_completed,
    repair_backup_failed,
)
from .notify import _ask_user_enable_ai, _notify_send
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
    SessionTerminateStage,
)
from .state import StateStore, _now_ts

PUBLIC_API_EXPORTS = [
    "attempt_repair",
    "RepairResult",
    "RepairOutcome",
    "RepairPipelineContext",
    "StageResult",
    "write_repair_progress",
    "clear_repair_progress",
]

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

COMPAT_NOTIFY_EXPORTS = [
    "NOTIFY_LEVEL_ALL",
    "NOTIFY_LEVEL_IMPORTANT",
    "NOTIFY_LEVEL_CRITICAL",
    "_should_notify",
    "_notify_send_with_level",
    "_ask_user_enable_ai",
]

COMPAT_OPERATION_EXPORTS = [
    "_parse_agent_id_from_session_key",
    "_list_active_sessions",
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

COMPAT_DEPENDENCY_EXPORTS = [
    "probe_health",
    "probe_logs",
    "probe_status",
    "_notify_send",
    "run_cmd",
    "HealthEvaluation",
    "CmdResult",
    "_analyze_anomaly_guard",
]

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

NOTIFY_LEVEL_ALL = repair_ops.NOTIFY_LEVEL_ALL
NOTIFY_LEVEL_IMPORTANT = repair_ops.NOTIFY_LEVEL_IMPORTANT
NOTIFY_LEVEL_CRITICAL = repair_ops.NOTIFY_LEVEL_CRITICAL
_ai_decision_source_label = repair_ops._ai_decision_source_label
_ai_decision_notification_text = repair_ops._ai_decision_notification_text
_build_ai_cmd = repair_ops._build_ai_cmd
_context_logs_timeout_seconds = repair_ops._context_logs_timeout_seconds
_load_prompt_text = repair_ops._load_prompt_text
_parse_agent_id_from_session_key = repair_ops._parse_agent_id_from_session_key
_session_stage_has_successful_commands = repair_ops._session_stage_has_successful_commands
_should_try_soft_pause = repair_ops._should_try_soft_pause


def _should_notify(cfg: AppConfig, level: str) -> bool:
    configured_level = cfg.notify.level.strip().lower()
    if configured_level == NOTIFY_LEVEL_ALL:
        return True
    if configured_level == NOTIFY_LEVEL_IMPORTANT:
        return level in {NOTIFY_LEVEL_IMPORTANT, NOTIFY_LEVEL_CRITICAL}
    if configured_level == NOTIFY_LEVEL_CRITICAL:
        return level == NOTIFY_LEVEL_CRITICAL
    return True


def _notify_send_with_level(cfg: AppConfig, text: str, level: str, *, silent: bool | None = None) -> dict[str, Any] | None:
    if not _should_notify(cfg, level):
        return None
    return _notify_send(cfg, text, silent=silent)


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


def _build_repair_state_machine_hooks() -> RepairStateMachineHooks:
    return RepairStateMachineHooks(
        runtime=RepairRuntimeHooks(
            attempt_dir_fn=_attempt_dir,
            clear_repair_progress_fn=clear_repair_progress,
            collect_context_fn=_collect_context,
            context_logs_timeout_seconds_fn=_context_logs_timeout_seconds,
            evaluate_health_fn=_evaluate_health,
            notify_send_with_level_fn=_notify_send_with_level,
            now_ts_fn=_now_ts,
            require_stage_payload_fn=_require_stage_payload,
            result_from_outcome_fn=_result_from_outcome,
            session_stage_has_successful_commands_fn=_session_stage_has_successful_commands,
            should_try_soft_pause_fn=_should_try_soft_pause,
            write_repair_progress_fn=write_repair_progress,
        ),
        messages=RepairMessageHooks(
            repair_starting_message=REPAIR_STARTING,
            repair_starting_manual_message=REPAIR_STARTING_MANUAL,
            recovered_after_pause_message=REPAIR_RECOVERED_AFTER_PAUSE,
            recovered_by_official_message=REPAIR_RECOVERED_BY_OFFICIAL,
            ai_disabled_message=REPAIR_AI_DISABLED,
            ai_rate_limited_message=REPAIR_AI_RATE_LIMITED,
            no_yes_received_message=REPAIR_NO_YES_RECEIVED,
            ai_config_success_message=REPAIR_AI_CONFIG_SUCCESS,
            ai_code_success_message=REPAIR_AI_CODE_SUCCESS,
            final_still_unhealthy_message=REPAIR_FINAL_STILL_UNHEALTHY,
            repair_backup_failed_fn=repair_backup_failed,
            notify_level_all=NOTIFY_LEVEL_ALL,
            notify_level_important=NOTIFY_LEVEL_IMPORTANT,
            notify_level_critical=NOTIFY_LEVEL_CRITICAL,
        ),
        stages=RepairStageHooks(
            session_pause_stage_cls=SessionPauseStage,
            pause_assessment_stage_cls=PauseAssessmentStage,
            session_terminate_stage_cls=SessionTerminateStage,
            session_reset_stage_cls=SessionResetStage,
            official_repair_stage_cls=OfficialRepairStage,
            ai_decision_stage_cls=AiDecisionStage,
            backup_stage_cls=BackupStage,
            ai_repair_stage_cls=AiRepairStage,
            final_assessment_stage_cls=FinalAssessmentStage,
        ),
    )


def attempt_repair(
    cfg: AppConfig,
    store: StateStore,
    *,
    force: bool,
    reason: str | None = None,
) -> RepairResult:
    return RepairStateMachine(
        cfg=cfg,
        store=store,
        force=force,
        reason=reason,
        hooks=_build_repair_state_machine_hooks(),
    ).run()
