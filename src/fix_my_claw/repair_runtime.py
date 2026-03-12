"""Internal runtime-backed helpers for the repair pipeline.

These helpers keep dependency injection close to the implementation layer so
production code can avoid importing the public ``repair`` facade.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from . import notify as notify_module
from . import repair_ops
from . import shared as shared_module
from . import stages as stages_module
from . import state as state_module
from .anomaly_guard import _analyze_anomaly_guard
from .config import AppConfig
from .health import HealthEvaluation, probe_health, probe_logs, probe_status
from .notification_events import dispatch_notification_event
from .notify import _notify_send
from .repair_hooks import _should_notify, build_repair_state_machine_hooks
from .repair_state_machine import RepairStateMachineHooks
from .repair_types import RepairOutcome, RepairResult, _require_stage_payload
from .runtime import CmdResult, run_cmd
from .shared import (
    _parse_json_maybe,
    _write_attempt_file,
    ensure_dir,
    redact_text,
    truncate_for_log,
)


def _result_from_outcome(*, attempted: bool, outcome: RepairOutcome) -> RepairResult:
    return RepairResult(
        attempted=attempted,
        fixed=outcome.fixed,
        used_ai=outcome.used_ai,
        outcome=outcome,
    )


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
        parse_agent_id_from_session_key_fn=repair_ops._parse_agent_id_from_session_key,
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
        context_logs_timeout_seconds_fn=repair_ops._context_logs_timeout_seconds,
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
        context_logs_timeout_seconds_fn=repair_ops._context_logs_timeout_seconds,
        sleep_fn=time.sleep,
    )


def _run_ai_repair(cfg: AppConfig, attempt_dir: Path, *, code_stage: bool) -> CmdResult:
    return repair_ops._run_ai_repair(
        cfg,
        attempt_dir,
        code_stage=code_stage,
        load_prompt_text_fn=repair_ops._load_prompt_text,
        build_ai_cmd_fn=repair_ops._build_ai_cmd,
        run_cmd_fn=run_cmd,
        write_attempt_file_fn=_write_attempt_file,
        redact_text_fn=redact_text,
        truncate_for_log_fn=truncate_for_log,
    )


def _build_repair_state_machine_hooks() -> RepairStateMachineHooks:
    return build_repair_state_machine_hooks(
        ai_decision_notification_text_fn=repair_ops._ai_decision_notification_text,
        ask_user_enable_ai_fn=notify_module._ask_user_enable_ai,
        attempt_dir_fn=_attempt_dir,
        backup_openclaw_state_fn=_backup_openclaw_state,
        clear_repair_progress_fn=shared_module.clear_repair_progress,
        collect_context_fn=_collect_context,
        context_logs_timeout_seconds_fn=repair_ops._context_logs_timeout_seconds,
        evaluate_health_fn=_evaluate_health,
        evaluate_with_context_fn=_evaluate_with_context,
        dispatch_notification_fn=_dispatch_notification,
        now_ts_fn=state_module._now_ts,
        require_stage_payload_fn=_require_stage_payload,
        result_from_outcome_fn=_result_from_outcome,
        run_ai_repair_fn=_run_ai_repair,
        run_official_steps_fn=_run_official_steps,
        run_session_command_stage_fn=_run_session_command_stage,
        session_stage_has_successful_commands_fn=repair_ops._session_stage_has_successful_commands,
        should_try_soft_pause_fn=repair_ops._should_try_soft_pause,
        write_repair_progress_fn=shared_module.write_repair_progress,
        session_pause_stage_cls=stages_module.SessionPauseStage,
        pause_assessment_stage_cls=stages_module.PauseAssessmentStage,
        session_terminate_stage_cls=stages_module.SessionTerminateStage,
        terminate_assessment_stage_cls=stages_module.SessionTerminateAssessmentStage,
        session_reset_stage_cls=stages_module.SessionResetStage,
        official_repair_stage_cls=stages_module.OfficialRepairStage,
        ai_decision_stage_cls=stages_module.AiDecisionStage,
        backup_stage_cls=stages_module.BackupStage,
        ai_repair_stage_cls=stages_module.AiRepairStage,
        final_assessment_stage_cls=stages_module.FinalAssessmentStage,
    )


__all__ = [
    "_build_repair_state_machine_hooks",
    "_attempt_dir",
    "_backup_openclaw_state",
    "_collect_context",
    "_dispatch_notification",
    "_evaluate_health",
    "_evaluate_with_context",
    "_list_active_sessions",
    "_probe_session_transcripts",
    "_run_ai_repair",
    "_run_official_steps",
    "_run_session_command_stage",
]
