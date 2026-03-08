from __future__ import annotations

import logging
import time
from dataclasses import dataclass
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
from .shared import (
    _parse_json_maybe,
    _write_attempt_file,
    clear_repair_progress,
    ensure_dir,
    redact_text,
    truncate_for_log,
    write_repair_progress,
)
from .state import StateStore, _now_ts

__all__ = [
    "AiDecision",
    "AiRepairStageData",
    "BackupArtifact",
    "CommandExecutionRecord",
    "OfficialRepairStageData",
    "PauseCheckStageData",
    "RepairOutcome",
    "RepairPipelineContext",
    "RepairResult",
    "SessionStageData",
    "StagePayload",
    "StageResult",
    "_cmd_result_to_json",
    "_coerce_execution_records",
    "_records_to_json",
    "_require_stage_payload",
    "NOTIFY_LEVEL_ALL",
    "NOTIFY_LEVEL_IMPORTANT",
    "NOTIFY_LEVEL_CRITICAL",
    "_should_notify",
    "_notify_send_with_level",
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
    "probe_health",
    "probe_logs",
    "probe_status",
    "_notify_send",
    "run_cmd",
    "HealthEvaluation",
    "CmdResult",
    "_analyze_anomaly_guard",
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



@dataclass(frozen=True)
class SessionPauseStage:
    def run(self, ctx: RepairPipelineContext) -> StageResult:
        write_repair_progress(
            ctx.cfg.monitor.state_dir,
            stage="pause",
            status="running",
            attempt_dir=str(ctx.attempt_dir.resolve()),
        )
        commands = _coerce_execution_records(
            _run_session_command_stage(
                ctx.cfg,
                ctx.attempt_dir,
                stage_name="pause",
                message_text=ctx.cfg.repair.pause_message,
            )
        )
        write_repair_progress(
            ctx.cfg.monitor.state_dir,
            stage="pause",
            status="completed",
            attempt_dir=str(ctx.attempt_dir.resolve()),
        )
        return StageResult(
            name="pause",
            status="completed",
            payload=SessionStageData(stage_name="pause", commands=commands),
        )


@dataclass(frozen=True)
class PauseAssessmentStage:
    def run(self, ctx: RepairPipelineContext, *, previous_stage: StageResult) -> StageResult:
        waited_before_seconds = 0
        payload = _require_stage_payload(previous_stage, SessionStageData)
        if payload.commands and ctx.cfg.repair.pause_wait_seconds > 0:
            time.sleep(ctx.cfg.repair.pause_wait_seconds)
            waited_before_seconds = ctx.cfg.repair.pause_wait_seconds
        evaluation, context = _evaluate_with_context(
            ctx.cfg,
            ctx.attempt_dir,
            stage_name="after_pause",
        )
        return StageResult(
            name="pause_check",
            status="completed",
            payload=PauseCheckStageData(waited_before_seconds=waited_before_seconds),
            evaluation=evaluation,
            context=context,
            stop_reason="healthy_after_pause" if evaluation.effective_healthy else "still_unhealthy_after_pause",
        )


@dataclass(frozen=True)
class SessionTerminateStage:
    def run(self, ctx: RepairPipelineContext) -> StageResult:
        commands = _coerce_execution_records(
            _run_session_command_stage(
                ctx.cfg,
                ctx.attempt_dir,
                stage_name="terminate",
                message_text=ctx.cfg.repair.terminate_message,
            )
        )
        return StageResult(
            name="terminate",
            status="completed",
            payload=SessionStageData(stage_name="terminate", commands=commands),
        )


@dataclass(frozen=True)
class SessionResetStage:
    def run(self, ctx: RepairPipelineContext, *, previous_stage: StageResult | None) -> StageResult:
        waited_before_seconds = 0
        if previous_stage is not None:
            payload = _require_stage_payload(previous_stage, SessionStageData)
            if payload.commands and ctx.cfg.repair.session_stage_wait_seconds > 0:
                time.sleep(ctx.cfg.repair.session_stage_wait_seconds)
                waited_before_seconds = ctx.cfg.repair.session_stage_wait_seconds
        commands = _coerce_execution_records(
            _run_session_command_stage(
                ctx.cfg,
                ctx.attempt_dir,
                stage_name="new",
                message_text=ctx.cfg.repair.new_message,
            )
        )
        return StageResult(
            name="new",
            status="completed",
            payload=SessionStageData(
                stage_name="new",
                commands=commands,
                waited_before_seconds=waited_before_seconds,
            ),
        )


@dataclass(frozen=True)
class OfficialRepairStage:
    def run(self, ctx: RepairPipelineContext) -> StageResult:
        write_repair_progress(
            ctx.cfg.monitor.state_dir,
            stage="official",
            status="running",
            attempt_dir=str(ctx.attempt_dir.resolve()),
        )
        steps, evaluation, break_reason = _run_official_steps(
            ctx.cfg,
            ctx.attempt_dir,
            break_on_healthy=True,
        )
        write_repair_progress(
            ctx.cfg.monitor.state_dir,
            stage="official",
            status="completed",
            attempt_dir=str(ctx.attempt_dir.resolve()),
        )
        return StageResult(
            name="official",
            status="completed",
            payload=OfficialRepairStageData(
                steps=_coerce_execution_records(steps),
                break_reason=break_reason,
            ),
            evaluation=evaluation,
            context=_collect_context(evaluation, ctx.attempt_dir, stage_name="after_official"),
            stop_reason=break_reason,
        )


@dataclass(frozen=True)
class AiDecisionStage:
    preset: dict[str, Any] | None = None

    def run(self, ctx: RepairPipelineContext) -> StageResult:
        write_repair_progress(
            ctx.cfg.monitor.state_dir,
            stage="ai_decision",
            status="running",
            attempt_dir=str(ctx.attempt_dir.resolve()),
        )
        decision = self.preset or _ask_user_enable_ai(ctx.cfg, ctx.attempt_dir)
        payload = AiDecision.from_mapping(decision)
        notification_text = _ai_decision_notification_text(payload)
        write_repair_progress(
            ctx.cfg.monitor.state_dir,
            stage="ai_decision",
            status="completed",
            attempt_dir=str(ctx.attempt_dir.resolve()),
        )
        return StageResult(
            name="ai_decision",
            status="completed",
            payload=payload,
            notification=(
                _notify_send_with_level(ctx.cfg, notification_text, NOTIFY_LEVEL_ALL, silent=False)
                if notification_text is not None
                else None
            ),
        )


@dataclass(frozen=True)
class BackupStage:
    def run(self, ctx: RepairPipelineContext) -> StageResult:
        write_repair_progress(
            ctx.cfg.monitor.state_dir,
            stage="backup",
            status="running",
            attempt_dir=str(ctx.attempt_dir.resolve()),
        )
        try:
            artifact = BackupArtifact.from_mapping(_backup_openclaw_state(ctx.cfg, ctx.attempt_dir))
        except Exception as exc:
            write_repair_progress(
                ctx.cfg.monitor.state_dir,
                stage="backup",
                status="failed",
                attempt_dir=str(ctx.attempt_dir.resolve()),
            )
            return StageResult(
                name="backup",
                status="failed",
                payload=BackupArtifact(error=str(exc)),
                stop_reason="backup_error",
            )
        write_repair_progress(
            ctx.cfg.monitor.state_dir,
            stage="backup",
            status="completed",
            attempt_dir=str(ctx.attempt_dir.resolve()),
        )
        return StageResult(
            name="backup",
            status="completed",
            payload=artifact,
            notification=_notify_send_with_level(
                ctx.cfg,
                backup_completed(artifact.archive),
                NOTIFY_LEVEL_IMPORTANT,
                silent=False,
            ),
        )


@dataclass(frozen=True)
class AiRepairStage:
    code_stage: bool

    def run(self, ctx: RepairPipelineContext) -> StageResult:
        result = _run_ai_repair(ctx.cfg, ctx.attempt_dir, code_stage=self.code_stage)
        stage_suffix = "code" if self.code_stage else "config"
        evaluation, context = _evaluate_with_context(
            ctx.cfg,
            ctx.attempt_dir,
            stage_name=f"after_ai_{stage_suffix}",
        )
        return StageResult(
            name=f"ai_{stage_suffix}",
            status="completed",
            payload=AiRepairStageData(stage_name=stage_suffix, result=result),
            evaluation=evaluation,
            context=context,
            used_ai=True,
        )


@dataclass(frozen=True)
class FinalAssessmentStage:
    stage_name: str

    def run(self, ctx: RepairPipelineContext) -> StageResult:
        evaluation, context = _evaluate_with_context(
            ctx.cfg,
            ctx.attempt_dir,
            stage_name=self.stage_name,
        )
        return StageResult(
            name="final",
            status="completed",
            evaluation=evaluation,
            context=context,
        )


def _result_from_outcome(*, attempted: bool, outcome: RepairOutcome) -> RepairResult:
    return RepairResult(
        attempted=attempted,
        fixed=outcome.fixed,
        used_ai=outcome.used_ai,
        outcome=outcome,
    )


def attempt_repair(
    cfg: AppConfig,
    store: StateStore,
    *,
    force: bool,
    reason: str | None = None,
) -> RepairResult:
    repair_log = logging.getLogger("fix_my_claw.repair")
    initial_evaluation = _evaluate_health(
        cfg,
        log_probe_failures=False,
        capture_logs=True,
        logs_timeout_seconds=_context_logs_timeout_seconds(cfg),
    )
    if initial_evaluation.effective_healthy:
        repair_log.info("repair skipped: already healthy")
        clear_repair_progress(cfg.monitor.state_dir)
        return RepairResult(attempted=False, fixed=True, used_ai=False, details_data={"already_healthy": True})

    if not cfg.repair.enabled:
        repair_log.warning("repair skipped: disabled by config")
        clear_repair_progress(cfg.monitor.state_dir)
        return RepairResult(attempted=False, fixed=False, used_ai=False, details_data={"repair_disabled": True})

    if not store.can_attempt_repair(cfg.monitor.repair_cooldown_seconds, force=force):
        details: dict[str, object] = {"cooldown": True}
        state = store.load()
        if state.last_repair_ts is not None:
            elapsed = _now_ts() - state.last_repair_ts
            remaining = max(0, cfg.monitor.repair_cooldown_seconds - elapsed)
            details["cooldown_remaining_seconds"] = remaining
            repair_log.info("repair skipped: cooldown (%ss remaining)", remaining)
        else:
            repair_log.info("repair skipped: cooldown")
        clear_repair_progress(cfg.monitor.state_dir)
        return RepairResult(attempted=False, fixed=False, used_ai=False, details_data=details)

    attempt_dir = _attempt_dir(cfg)
    store.mark_repair_attempt()
    ctx = RepairPipelineContext(cfg=cfg, store=store, attempt_dir=attempt_dir)
    outcome = RepairOutcome(attempt_dir=str(attempt_dir.resolve()), reason=reason)
    repair_log.info("starting repair attempt: dir=%s", attempt_dir.resolve())
    
    # 写入初始进度
    write_repair_progress(
        cfg.monitor.state_dir,
        stage="starting",
        status="running",
        attempt_dir=str(attempt_dir.resolve()),
    )
    outcome.start_notification = _notify_send_with_level(
        cfg,
        REPAIR_STARTING,
        NOTIFY_LEVEL_IMPORTANT,
        silent=False,
    )

    outcome.before_context = _collect_context(initial_evaluation, attempt_dir, stage_name="before")
    if _should_try_soft_pause(cfg, initial_evaluation):
        pause_candidate = SessionPauseStage().run(ctx)
        pause_payload = _require_stage_payload(pause_candidate, SessionStageData)
        if pause_payload.commands:
            pause_stage = outcome.add_stage(pause_candidate)
            if _session_stage_has_successful_commands(pause_stage):
                pause_check_stage = outcome.add_stage(PauseAssessmentStage().run(ctx, previous_stage=pause_stage))
                if pause_check_stage.fixed:
                    outcome.final_stage = pause_check_stage
                    outcome.final_notification = _notify_send_with_level(
                        cfg,
                        REPAIR_RECOVERED_AFTER_PAUSE,
                        NOTIFY_LEVEL_IMPORTANT,
                    )
                    repair_log.info("recovered after soft pause: dir=%s", attempt_dir.resolve())
                    clear_repair_progress(cfg.monitor.state_dir)
                    return _result_from_outcome(attempted=True, outcome=outcome)
    terminate_stage = outcome.add_stage(SessionTerminateStage().run(ctx))
    outcome.add_stage(SessionResetStage().run(ctx, previous_stage=terminate_stage))
    official_stage = outcome.add_stage(OfficialRepairStage().run(ctx))

    if official_stage.fixed:
        outcome.final_stage = official_stage
        outcome.final_notification = _notify_send_with_level(
            cfg,
            REPAIR_RECOVERED_BY_OFFICIAL,
            NOTIFY_LEVEL_IMPORTANT,
        )
        repair_log.info("recovered by official steps: dir=%s", attempt_dir.resolve())
        clear_repair_progress(cfg.monitor.state_dir)
        return _result_from_outcome(attempted=True, outcome=outcome)

    if not cfg.ai.enabled:
        repair_log.info("Codex-assisted remediation disabled; leaving OpenClaw unhealthy")
        final_stage = outcome.add_stage(FinalAssessmentStage(stage_name="final_no_ai").run(ctx))
        outcome.final_stage = final_stage
        outcome.final_notification = _notify_send_with_level(
            cfg,
            REPAIR_AI_DISABLED,
            NOTIFY_LEVEL_IMPORTANT,
            silent=False,
        )
        clear_repair_progress(cfg.monitor.state_dir)
        return _result_from_outcome(attempted=True, outcome=outcome)

    if not store.can_attempt_ai(
        max_attempts_per_day=cfg.ai.max_attempts_per_day,
        cooldown_seconds=cfg.ai.cooldown_seconds,
    ):
        # 直接创建限流决策，不运行 stage（避免触发 GUI 标志检查）
        outcome.add_stage(StageResult(
            name="ai_decision",
            status="completed",
            payload=AiDecision.from_mapping({"asked": False, "decision": "rate_limited"}),
        ))
        final_stage = outcome.add_stage(FinalAssessmentStage(stage_name="final_rate_limited").run(ctx))
        outcome.final_stage = final_stage
        outcome.final_notification = _notify_send_with_level(
            cfg,
            REPAIR_AI_RATE_LIMITED,
            NOTIFY_LEVEL_ALL,
            silent=False,
        )
        clear_repair_progress(cfg.monitor.state_dir)
        return _result_from_outcome(attempted=True, outcome=outcome)

    ai_decision_stage = outcome.add_stage(AiDecisionStage().run(ctx))
    ai_decision = _require_stage_payload(ai_decision_stage, AiDecision)
    if ai_decision.decision != "yes":
        final_stage = outcome.add_stage(FinalAssessmentStage(stage_name="final_no_approval").run(ctx))
        outcome.final_stage = final_stage
        if ai_decision_stage.notification is not None:
            outcome.final_notification = ai_decision_stage.notification
        else:
            outcome.final_notification = _notify_send_with_level(
                cfg,
                REPAIR_NO_YES_RECEIVED,
                NOTIFY_LEVEL_IMPORTANT,
                silent=False,
            )
        clear_repair_progress(cfg.monitor.state_dir)
        return _result_from_outcome(attempted=True, outcome=outcome)

    backup_stage = outcome.add_stage(BackupStage().run(ctx))
    backup_artifact = _require_stage_payload(backup_stage, BackupArtifact)
    if backup_stage.status != "completed":
        outcome.final_stage = outcome.add_stage(FinalAssessmentStage(stage_name="final_backup_error").run(ctx))
        outcome.final_notification = _notify_send_with_level(
            cfg,
            repair_backup_failed(backup_artifact.error),
            NOTIFY_LEVEL_IMPORTANT,
            silent=False,
        )
        clear_repair_progress(cfg.monitor.state_dir)
        return _result_from_outcome(attempted=True, outcome=outcome)

    store.mark_ai_attempt()
    ai_config_stage = outcome.add_stage(AiRepairStage(code_stage=False).run(ctx))
    if ai_config_stage.fixed:
        outcome.final_stage = ai_config_stage
        outcome.final_notification = _notify_send_with_level(
            cfg,
            REPAIR_AI_CONFIG_SUCCESS,
            NOTIFY_LEVEL_IMPORTANT,
            silent=False,
        )
        repair_log.info("recovered by Codex-assisted remediation: dir=%s", attempt_dir.resolve())
        clear_repair_progress(cfg.monitor.state_dir)
        return _result_from_outcome(attempted=True, outcome=outcome)

    if cfg.ai.allow_code_changes:
        ai_code_stage = outcome.add_stage(AiRepairStage(code_stage=True).run(ctx))
        if ai_code_stage.fixed:
            outcome.final_stage = ai_code_stage
            outcome.final_notification = _notify_send_with_level(
                cfg,
                REPAIR_AI_CODE_SUCCESS,
                NOTIFY_LEVEL_IMPORTANT,
                silent=False,
            )
            repair_log.info("recovered by code-stage remediation: dir=%s", attempt_dir.resolve())
            clear_repair_progress(cfg.monitor.state_dir)
            return _result_from_outcome(attempted=True, outcome=outcome)

    final_stage = outcome.add_stage(FinalAssessmentStage(stage_name="final").run(ctx))
    outcome.final_stage = final_stage
    outcome.final_notification = _notify_send_with_level(
        cfg,
        REPAIR_FINAL_STILL_UNHEALTHY,
        NOTIFY_LEVEL_CRITICAL,
        silent=False,
    )
    repair_log.warning(
        "repair attempt finished: fixed=%s used_codex=%s dir=%s",
        outcome.fixed,
        outcome.used_ai,
        attempt_dir.resolve(),
    )
    clear_repair_progress(cfg.monitor.state_dir)
    return _result_from_outcome(attempted=True, outcome=outcome)
