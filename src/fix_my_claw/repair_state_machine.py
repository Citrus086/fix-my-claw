"""Repair orchestration state machine.

This module owns the control-flow transitions for the repair pipeline.
It does not implement stage behavior itself; instead, it receives
patch-sensitive helpers and stage classes from `repair.py`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .config import AppConfig
from .health import HealthEvaluation
from .notification_events import emit_repair_result_event
from .repair_types import (
    AiDecision,
    BackupArtifact,
    RepairOutcome,
    RepairPipelineContext,
    RepairResult,
    SessionStageData,
    StageResult,
)
from .shared import clear_repair_result, write_repair_result
from .state import StateStore


class RepairMachineState(str, Enum):
    CHECK_INITIAL_HEALTH = "check_initial_health"
    CHECK_REPAIR_ENABLED = "check_repair_enabled"
    CHECK_REPAIR_COOLDOWN = "check_repair_cooldown"
    START_ATTEMPT = "start_attempt"
    CHECK_SOFT_PAUSE = "check_soft_pause"
    RUN_PAUSE = "run_pause"
    RUN_PAUSE_ASSESSMENT = "run_pause_assessment"
    RUN_TERMINATE = "run_terminate"
    RUN_TERMINATE_ASSESSMENT = "run_terminate_assessment"
    RUN_RESET = "run_reset"
    RUN_OFFICIAL = "run_official"
    CHECK_OFFICIAL_RESULT = "check_official_result"
    CHECK_AI_ENABLED = "check_ai_enabled"
    CHECK_AI_RATE_LIMIT = "check_ai_rate_limit"
    RUN_RATE_LIMIT_EXIT = "run_rate_limit_exit"
    RUN_AI_DECISION = "run_ai_decision"
    CHECK_AI_DECISION = "check_ai_decision"
    RUN_NO_APPROVAL_EXIT = "run_no_approval_exit"
    RUN_BACKUP = "run_backup"
    CHECK_BACKUP_RESULT = "check_backup_result"
    RUN_BACKUP_ERROR_EXIT = "run_backup_error_exit"
    MARK_AI_ATTEMPT = "mark_ai_attempt"
    RUN_AI_CONFIG = "run_ai_config"
    CHECK_AI_CONFIG_RESULT = "check_ai_config_result"
    RUN_AI_CONFIG_SUCCESS_EXIT = "run_ai_config_success_exit"
    CHECK_AI_CODE_ALLOWED = "check_ai_code_allowed"
    RUN_AI_CODE = "run_ai_code"
    CHECK_AI_CODE_RESULT = "check_ai_code_result"
    RUN_AI_CODE_SUCCESS_EXIT = "run_ai_code_success_exit"
    RUN_AI_DISABLED_EXIT = "run_ai_disabled_exit"
    RUN_FINAL_ASSESSMENT = "run_final_assessment"
    DONE = "done"


@dataclass(frozen=True)
class RepairRuntimeHooks:
    attempt_dir_fn: Callable[[AppConfig], Path]
    clear_repair_progress_fn: Callable[[Path], None]
    collect_context_fn: Callable[..., dict[str, Any]]
    context_logs_timeout_seconds_fn: Callable[[AppConfig], int]
    evaluate_health_fn: Callable[..., HealthEvaluation]
    dispatch_notification_fn: Callable[..., dict[str, Any] | None]
    now_ts_fn: Callable[[], int]
    require_stage_payload_fn: Callable[[StageResult, type[Any]], Any]
    result_from_outcome_fn: Callable[..., RepairResult]
    session_stage_has_successful_commands_fn: Callable[[StageResult], bool]
    should_try_soft_pause_fn: Callable[[AppConfig, HealthEvaluation], bool]
    write_repair_progress_fn: Callable[..., None]


@dataclass(frozen=True)
class RepairMessageHooks:
    repair_starting_message: str
    repair_starting_manual_message: str
    recovered_after_pause_message: str
    recovered_after_stop_message: str
    recovered_by_official_message: str
    ai_disabled_message: str
    ai_rate_limited_message: str
    no_yes_received_message: str
    ai_config_success_message: str
    ai_code_success_message: str
    final_still_unhealthy_message: str
    repair_backup_failed_fn: Callable[[str | None], str]
    notify_level_all: str
    notify_level_important: str
    notify_level_critical: str


@dataclass(frozen=True)
class RepairStageHooks:
    session_pause_stage_cls: type[Any]
    pause_assessment_stage_cls: type[Any]
    session_terminate_stage_cls: type[Any]
    terminate_assessment_stage_cls: type[Any]
    session_reset_stage_cls: type[Any]
    official_repair_stage_cls: type[Any]
    ai_decision_stage_cls: type[Any]
    backup_stage_cls: type[Any]
    ai_repair_stage_cls: type[Any]
    final_assessment_stage_cls: type[Any]


@dataclass(frozen=True)
class RepairStateMachineHooks:
    runtime: RepairRuntimeHooks
    messages: RepairMessageHooks
    stages: RepairStageHooks


@dataclass
class RepairStateMachine:
    cfg: AppConfig
    store: StateStore
    force: bool
    reason: str | None
    manual_start: bool
    reassess_after_terminate: bool
    hooks: RepairStateMachineHooks
    state: RepairMachineState = RepairMachineState.CHECK_INITIAL_HEALTH
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("fix_my_claw.repair"))
    initial_evaluation: HealthEvaluation | None = None
    ctx: RepairPipelineContext | None = None
    outcome: RepairOutcome | None = None
    pause_stage: StageResult | None = None
    terminate_stage: StageResult | None = None
    official_stage: StageResult | None = None
    ai_decision_stage: StageResult | None = None
    backup_stage: StageResult | None = None
    ai_config_stage: StageResult | None = None
    ai_code_stage: StageResult | None = None
    terminal_result: RepairResult | None = None

    @property
    def runtime(self) -> RepairRuntimeHooks:
        return self.hooks.runtime

    @property
    def messages(self) -> RepairMessageHooks:
        return self.hooks.messages

    @property
    def stages(self) -> RepairStageHooks:
        return self.hooks.stages

    def run(self) -> RepairResult:
        clear_repair_result(self.cfg.monitor.state_dir)
        while self.state is not RepairMachineState.DONE:
            self.state = self._advance()
        if self.terminal_result is None:
            raise RuntimeError("repair state machine reached DONE without a result")
        write_repair_result(
            self.cfg.monitor.state_dir,
            result=self.terminal_result.to_json(),
        )
        emit_repair_result_event(self.cfg.monitor.state_dir, result=self.terminal_result)
        return self.terminal_result

    def _advance(self) -> RepairMachineState:
        match self.state:
            case RepairMachineState.CHECK_INITIAL_HEALTH:
                return self._check_initial_health()
            case RepairMachineState.CHECK_REPAIR_ENABLED:
                return self._check_repair_enabled()
            case RepairMachineState.CHECK_REPAIR_COOLDOWN:
                return self._check_repair_cooldown()
            case RepairMachineState.START_ATTEMPT:
                return self._start_attempt()
            case RepairMachineState.CHECK_SOFT_PAUSE:
                return self._check_soft_pause()
            case RepairMachineState.RUN_PAUSE:
                return self._run_pause()
            case RepairMachineState.RUN_PAUSE_ASSESSMENT:
                return self._run_pause_assessment()
            case RepairMachineState.RUN_TERMINATE:
                return self._run_terminate()
            case RepairMachineState.RUN_TERMINATE_ASSESSMENT:
                return self._run_terminate_assessment()
            case RepairMachineState.RUN_RESET:
                return self._run_reset()
            case RepairMachineState.RUN_OFFICIAL:
                return self._run_official()
            case RepairMachineState.CHECK_OFFICIAL_RESULT:
                return self._check_official_result()
            case RepairMachineState.CHECK_AI_ENABLED:
                return self._check_ai_enabled()
            case RepairMachineState.CHECK_AI_RATE_LIMIT:
                return self._check_ai_rate_limit()
            case RepairMachineState.RUN_RATE_LIMIT_EXIT:
                return self._run_rate_limit_exit()
            case RepairMachineState.RUN_AI_DECISION:
                return self._run_ai_decision()
            case RepairMachineState.CHECK_AI_DECISION:
                return self._check_ai_decision()
            case RepairMachineState.RUN_NO_APPROVAL_EXIT:
                return self._run_no_approval_exit()
            case RepairMachineState.RUN_BACKUP:
                return self._run_backup()
            case RepairMachineState.CHECK_BACKUP_RESULT:
                return self._check_backup_result()
            case RepairMachineState.RUN_BACKUP_ERROR_EXIT:
                return self._run_backup_error_exit()
            case RepairMachineState.MARK_AI_ATTEMPT:
                return self._mark_ai_attempt()
            case RepairMachineState.RUN_AI_CONFIG:
                return self._run_ai_config()
            case RepairMachineState.CHECK_AI_CONFIG_RESULT:
                return self._check_ai_config_result()
            case RepairMachineState.RUN_AI_CONFIG_SUCCESS_EXIT:
                return self._run_ai_config_success_exit()
            case RepairMachineState.CHECK_AI_CODE_ALLOWED:
                return self._check_ai_code_allowed()
            case RepairMachineState.RUN_AI_CODE:
                return self._run_ai_code()
            case RepairMachineState.CHECK_AI_CODE_RESULT:
                return self._check_ai_code_result()
            case RepairMachineState.RUN_AI_CODE_SUCCESS_EXIT:
                return self._run_ai_code_success_exit()
            case RepairMachineState.RUN_AI_DISABLED_EXIT:
                return self._run_ai_disabled_exit()
            case RepairMachineState.RUN_FINAL_ASSESSMENT:
                return self._run_final_assessment()
            case RepairMachineState.DONE:
                return RepairMachineState.DONE
        raise AssertionError(f"unexpected repair state: {self.state}")

    def _check_initial_health(self) -> RepairMachineState:
        self.initial_evaluation = self.runtime.evaluate_health_fn(
            self.cfg,
            log_probe_failures=False,
            capture_logs=True,
            logs_timeout_seconds=self.runtime.context_logs_timeout_seconds_fn(self.cfg),
        )
        if self.initial_evaluation.effective_healthy:
            if self.manual_start:
                self.logger.info("manual repair requested while already healthy; continuing full workflow")
                return RepairMachineState.CHECK_REPAIR_ENABLED
            self.logger.info("repair skipped: already healthy")
            self.runtime.clear_repair_progress_fn(self.cfg.monitor.state_dir)
            self.terminal_result = RepairResult(
                attempted=False,
                fixed=True,
                used_ai=False,
                details_data={"already_healthy": True},
            )
            return RepairMachineState.DONE
        return RepairMachineState.CHECK_REPAIR_ENABLED

    def _check_repair_enabled(self) -> RepairMachineState:
        if self.cfg.repair.enabled:
            return RepairMachineState.CHECK_REPAIR_COOLDOWN
        self.logger.warning("repair skipped: disabled by config")
        self.runtime.clear_repair_progress_fn(self.cfg.monitor.state_dir)
        self.terminal_result = RepairResult(
            attempted=False,
            fixed=False,
            used_ai=False,
            details_data={"repair_disabled": True},
        )
        return RepairMachineState.DONE

    def _check_repair_cooldown(self) -> RepairMachineState:
        if self.store.can_attempt_repair(self.cfg.monitor.repair_cooldown_seconds, force=self.force):
            return RepairMachineState.START_ATTEMPT
        details: dict[str, object] = {"cooldown": True}
        state = self.store.load()
        if state.last_repair_ts is not None:
            elapsed = self.runtime.now_ts_fn() - state.last_repair_ts
            remaining = max(0, self.cfg.monitor.repair_cooldown_seconds - elapsed)
            details["cooldown_remaining_seconds"] = remaining
            self.logger.info("repair skipped: cooldown (%ss remaining)", remaining)
        else:
            self.logger.info("repair skipped: cooldown")
        self.runtime.clear_repair_progress_fn(self.cfg.monitor.state_dir)
        self.terminal_result = RepairResult(
            attempted=False,
            fixed=False,
            used_ai=False,
            details_data=details,
        )
        return RepairMachineState.DONE

    def _start_attempt(self) -> RepairMachineState:
        initial_evaluation = self._initial_evaluation()
        attempt_dir = self.runtime.attempt_dir_fn(self.cfg)
        self.store.mark_repair_attempt()
        self.ctx = RepairPipelineContext(
            cfg=self.cfg,
            store=self.store,
            attempt_dir=attempt_dir,
        )
        self.outcome = RepairOutcome(attempt_dir=str(attempt_dir.resolve()), reason=self.reason)
        self.logger.info("starting repair attempt: dir=%s", attempt_dir.resolve())
        self.runtime.write_repair_progress_fn(
            self.cfg.monitor.state_dir,
            stage="starting",
            status="running",
            attempt_dir=str(attempt_dir.resolve()),
        )
        # Use manual repair message if triggered manually
        start_message = (
            self.messages.repair_starting_manual_message
            if self.manual_start
            else self.messages.repair_starting_message
        )
        self._outcome().start_notification = self.runtime.dispatch_notification_fn(
            self.cfg,
            kind="repair_started",
            source="repair",
            text=start_message,
            level=self.messages.notify_level_important,
            silent=False,
            local_title="🔧 修复已启动",
            local_body="修复正在后台运行，请稍候...",
            dedupe_key=f"repair_started:{attempt_dir.resolve()}",
        )
        self._outcome().before_context = self.runtime.collect_context_fn(initial_evaluation, attempt_dir, stage_name="before")
        return RepairMachineState.CHECK_SOFT_PAUSE

    def _check_soft_pause(self) -> RepairMachineState:
        if self.runtime.should_try_soft_pause_fn(self.cfg, self._initial_evaluation()):
            return RepairMachineState.RUN_PAUSE
        return RepairMachineState.RUN_TERMINATE

    def _run_pause(self) -> RepairMachineState:
        pause_candidate = self.stages.session_pause_stage_cls().run(self._ctx())
        pause_payload = self.runtime.require_stage_payload_fn(pause_candidate, SessionStageData)
        if pause_payload.commands:
            self.pause_stage = self._outcome().add_stage(pause_candidate)
            if self.runtime.session_stage_has_successful_commands_fn(self.pause_stage):
                return RepairMachineState.RUN_PAUSE_ASSESSMENT
        return RepairMachineState.RUN_TERMINATE

    def _run_pause_assessment(self) -> RepairMachineState:
        if self.pause_stage is None:
            raise RuntimeError("pause assessment requires a pause stage result")
        pause_check_stage = self._outcome().add_stage(
            self.stages.pause_assessment_stage_cls().run(self._ctx(), previous_stage=self.pause_stage)
        )
        if not pause_check_stage.fixed:
            return RepairMachineState.RUN_TERMINATE
        self._outcome().final_stage = pause_check_stage
        self._outcome().final_notification = self.runtime.dispatch_notification_fn(
            self.cfg,
            kind="repair_status",
            source="repair",
            text=self.messages.recovered_after_pause_message,
            level=self.messages.notify_level_important,
            dedupe_key=f"repair_status:{self._ctx().attempt_dir.resolve()}:recovered_after_pause",
        )
        self.logger.info("recovered after soft pause: dir=%s", self._ctx().attempt_dir.resolve())
        self._finish_attempt()
        return RepairMachineState.DONE

    def _run_terminate(self) -> RepairMachineState:
        self.terminate_stage = self._outcome().add_stage(self.stages.session_terminate_stage_cls().run(self._ctx()))
        if self.reassess_after_terminate:
            if self.runtime.session_stage_has_successful_commands_fn(self.terminate_stage):
                return RepairMachineState.RUN_TERMINATE_ASSESSMENT
            return RepairMachineState.RUN_OFFICIAL
        return RepairMachineState.RUN_RESET

    def _run_terminate_assessment(self) -> RepairMachineState:
        if self.terminate_stage is None:
            raise RuntimeError("terminate assessment requires a terminate stage result")
        terminate_check_stage = self._outcome().add_stage(
            self.stages.terminate_assessment_stage_cls().run(self._ctx(), previous_stage=self.terminate_stage)
        )
        if not terminate_check_stage.fixed:
            return RepairMachineState.RUN_RESET
        self._outcome().final_stage = terminate_check_stage
        self._outcome().final_notification = self.runtime.dispatch_notification_fn(
            self.cfg,
            kind="repair_status",
            source="repair",
            text=self.messages.recovered_after_stop_message,
            level=self.messages.notify_level_important,
            dedupe_key=f"repair_status:{self._ctx().attempt_dir.resolve()}:recovered_after_stop",
        )
        self.logger.info("recovered after hard stop: dir=%s", self._ctx().attempt_dir.resolve())
        self._finish_attempt()
        return RepairMachineState.DONE

    def _run_reset(self) -> RepairMachineState:
        if self.terminate_stage is None:
            raise RuntimeError("reset requires a terminate stage result")
        self._outcome().add_stage(
            self.stages.session_reset_stage_cls().run(
                self._ctx(),
                previous_stage=self.terminate_stage,
                wait_before_reset=not self.reassess_after_terminate,
            )
        )
        return RepairMachineState.RUN_OFFICIAL

    def _run_official(self) -> RepairMachineState:
        self.official_stage = self._outcome().add_stage(self.stages.official_repair_stage_cls().run(self._ctx()))
        return RepairMachineState.CHECK_OFFICIAL_RESULT

    def _check_official_result(self) -> RepairMachineState:
        if self.official_stage is None:
            raise RuntimeError("official result check requires an official stage result")
        if not self.official_stage.fixed:
            return RepairMachineState.CHECK_AI_ENABLED
        self._outcome().final_stage = self.official_stage
        self._outcome().final_notification = self.runtime.dispatch_notification_fn(
            self.cfg,
            kind="repair_status",
            source="repair",
            text=self.messages.recovered_by_official_message,
            level=self.messages.notify_level_important,
            dedupe_key=f"repair_status:{self._ctx().attempt_dir.resolve()}:recovered_by_official",
        )
        self.logger.info("recovered by official steps: dir=%s", self._ctx().attempt_dir.resolve())
        self._finish_attempt()
        return RepairMachineState.DONE

    def _check_ai_enabled(self) -> RepairMachineState:
        if self.cfg.ai.enabled:
            return RepairMachineState.CHECK_AI_RATE_LIMIT
        return RepairMachineState.RUN_AI_DISABLED_EXIT

    def _run_ai_disabled_exit(self) -> RepairMachineState:
        self.logger.info("Codex-assisted remediation disabled; leaving OpenClaw unhealthy")
        final_stage = self._outcome().add_stage(self.stages.final_assessment_stage_cls(stage_name="final_no_ai").run(self._ctx()))
        self._outcome().final_stage = final_stage
        self._outcome().final_notification = self.runtime.dispatch_notification_fn(
            self.cfg,
            kind="repair_status",
            source="repair",
            text=self.messages.ai_disabled_message,
            level=self.messages.notify_level_important,
            silent=False,
            dedupe_key=f"repair_status:{self._ctx().attempt_dir.resolve()}:ai_disabled",
        )
        self._finish_attempt()
        return RepairMachineState.DONE

    def _check_ai_rate_limit(self) -> RepairMachineState:
        if self.store.can_attempt_ai(
            max_attempts_per_day=self.cfg.ai.max_attempts_per_day,
            cooldown_seconds=self.cfg.ai.cooldown_seconds,
        ):
            return RepairMachineState.RUN_AI_DECISION
        return RepairMachineState.RUN_RATE_LIMIT_EXIT

    def _run_rate_limit_exit(self) -> RepairMachineState:
        self._outcome().add_stage(
            StageResult(
                name="ai_decision",
                status="completed",
                payload=AiDecision.from_mapping({"asked": False, "decision": "rate_limited"}),
            )
        )
        final_stage = self._outcome().add_stage(
            self.stages.final_assessment_stage_cls(stage_name="final_rate_limited").run(self._ctx())
        )
        self._outcome().final_stage = final_stage
        self._outcome().final_notification = self.runtime.dispatch_notification_fn(
            self.cfg,
            kind="repair_status",
            source="repair",
            text=self.messages.ai_rate_limited_message,
            level=self.messages.notify_level_all,
            silent=False,
            dedupe_key=f"repair_status:{self._ctx().attempt_dir.resolve()}:ai_rate_limited",
        )
        self._finish_attempt()
        return RepairMachineState.DONE

    def _run_ai_decision(self) -> RepairMachineState:
        self.ai_decision_stage = self._outcome().add_stage(self.stages.ai_decision_stage_cls().run(self._ctx()))
        return RepairMachineState.CHECK_AI_DECISION

    def _check_ai_decision(self) -> RepairMachineState:
        if self.ai_decision_stage is None:
            raise RuntimeError("AI decision check requires an AI decision stage result")
        ai_decision = self.runtime.require_stage_payload_fn(self.ai_decision_stage, AiDecision)
        if ai_decision.decision == "yes":
            return RepairMachineState.RUN_BACKUP
        return RepairMachineState.RUN_NO_APPROVAL_EXIT

    def _run_no_approval_exit(self) -> RepairMachineState:
        if self.ai_decision_stage is None:
            raise RuntimeError("no-approval exit requires an AI decision stage result")
        final_stage = self._outcome().add_stage(self.stages.final_assessment_stage_cls(stage_name="final_no_approval").run(self._ctx()))
        self._outcome().final_stage = final_stage
        if self.ai_decision_stage.notification is not None:
            self._outcome().final_notification = self.ai_decision_stage.notification
        else:
            self._outcome().final_notification = self.runtime.dispatch_notification_fn(
                self.cfg,
                kind="repair_status",
                source="repair",
                text=self.messages.no_yes_received_message,
                level=self.messages.notify_level_important,
                silent=False,
                dedupe_key=f"repair_status:{self._ctx().attempt_dir.resolve()}:no_yes_received",
            )
        self._finish_attempt()
        return RepairMachineState.DONE

    def _run_backup(self) -> RepairMachineState:
        self.backup_stage = self._outcome().add_stage(self.stages.backup_stage_cls().run(self._ctx()))
        return RepairMachineState.CHECK_BACKUP_RESULT

    def _check_backup_result(self) -> RepairMachineState:
        if self.backup_stage is None:
            raise RuntimeError("backup result check requires a backup stage result")
        if self.backup_stage.status == "completed":
            return RepairMachineState.MARK_AI_ATTEMPT
        return RepairMachineState.RUN_BACKUP_ERROR_EXIT

    def _run_backup_error_exit(self) -> RepairMachineState:
        if self.backup_stage is None:
            raise RuntimeError("backup-error exit requires a backup stage result")
        backup_artifact = self.runtime.require_stage_payload_fn(self.backup_stage, BackupArtifact)
        self._outcome().final_stage = self._outcome().add_stage(
            self.stages.final_assessment_stage_cls(stage_name="final_backup_error").run(self._ctx())
        )
        self._outcome().final_notification = self.runtime.dispatch_notification_fn(
            self.cfg,
            kind="repair_status",
            source="repair",
            text=self.messages.repair_backup_failed_fn(backup_artifact.error),
            level=self.messages.notify_level_important,
            silent=False,
            dedupe_key=f"repair_status:{self._ctx().attempt_dir.resolve()}:backup_failed",
        )
        self._finish_attempt()
        return RepairMachineState.DONE

    def _mark_ai_attempt(self) -> RepairMachineState:
        self.store.mark_ai_attempt()
        return RepairMachineState.RUN_AI_CONFIG

    def _run_ai_config(self) -> RepairMachineState:
        self.ai_config_stage = self._outcome().add_stage(self.stages.ai_repair_stage_cls(code_stage=False).run(self._ctx()))
        return RepairMachineState.CHECK_AI_CONFIG_RESULT

    def _check_ai_config_result(self) -> RepairMachineState:
        if self.ai_config_stage is None:
            raise RuntimeError("AI config result check requires an AI config stage result")
        if self.ai_config_stage.fixed:
            return RepairMachineState.RUN_AI_CONFIG_SUCCESS_EXIT
        return RepairMachineState.CHECK_AI_CODE_ALLOWED

    def _run_ai_config_success_exit(self) -> RepairMachineState:
        if self.ai_config_stage is None:
            raise RuntimeError("AI config success exit requires an AI config stage result")
        self._outcome().final_stage = self.ai_config_stage
        self._outcome().final_notification = self.runtime.dispatch_notification_fn(
            self.cfg,
            kind="repair_status",
            source="repair",
            text=self.messages.ai_config_success_message,
            level=self.messages.notify_level_important,
            silent=False,
            dedupe_key=f"repair_status:{self._ctx().attempt_dir.resolve()}:ai_config_success",
        )
        self.logger.info("recovered by Codex-assisted remediation: dir=%s", self._ctx().attempt_dir.resolve())
        self._finish_attempt()
        return RepairMachineState.DONE

    def _check_ai_code_allowed(self) -> RepairMachineState:
        if self.cfg.ai.allow_code_changes:
            return RepairMachineState.RUN_AI_CODE
        return RepairMachineState.RUN_FINAL_ASSESSMENT

    def _run_ai_code(self) -> RepairMachineState:
        self.ai_code_stage = self._outcome().add_stage(self.stages.ai_repair_stage_cls(code_stage=True).run(self._ctx()))
        return RepairMachineState.CHECK_AI_CODE_RESULT

    def _check_ai_code_result(self) -> RepairMachineState:
        if self.ai_code_stage is None:
            raise RuntimeError("AI code result check requires an AI code stage result")
        if self.ai_code_stage.fixed:
            return RepairMachineState.RUN_AI_CODE_SUCCESS_EXIT
        return RepairMachineState.RUN_FINAL_ASSESSMENT

    def _run_ai_code_success_exit(self) -> RepairMachineState:
        if self.ai_code_stage is None:
            raise RuntimeError("AI code success exit requires an AI code stage result")
        self._outcome().final_stage = self.ai_code_stage
        self._outcome().final_notification = self.runtime.dispatch_notification_fn(
            self.cfg,
            kind="repair_status",
            source="repair",
            text=self.messages.ai_code_success_message,
            level=self.messages.notify_level_important,
            silent=False,
            dedupe_key=f"repair_status:{self._ctx().attempt_dir.resolve()}:ai_code_success",
        )
        self.logger.info("recovered by code-stage remediation: dir=%s", self._ctx().attempt_dir.resolve())
        self._finish_attempt()
        return RepairMachineState.DONE

    def _run_final_assessment(self) -> RepairMachineState:
        final_stage = self._outcome().add_stage(self.stages.final_assessment_stage_cls(stage_name="final").run(self._ctx()))
        self._outcome().final_stage = final_stage
        self._outcome().final_notification = self.runtime.dispatch_notification_fn(
            self.cfg,
            kind="repair_status",
            source="repair",
            text=self.messages.final_still_unhealthy_message,
            level=self.messages.notify_level_critical,
            silent=False,
            dedupe_key=f"repair_status:{self._ctx().attempt_dir.resolve()}:final_unhealthy",
        )
        self.logger.warning(
            "repair attempt finished: fixed=%s used_codex=%s dir=%s",
            self._outcome().fixed,
            self._outcome().used_ai,
            self._ctx().attempt_dir.resolve(),
        )
        self._finish_attempt()
        return RepairMachineState.DONE

    def _finish_attempt(self) -> None:
        self.runtime.clear_repair_progress_fn(self.cfg.monitor.state_dir)
        self.terminal_result = self.runtime.result_from_outcome_fn(
            attempted=True,
            outcome=self._outcome(),
        )

    def _initial_evaluation(self) -> HealthEvaluation:
        if self.initial_evaluation is None:
            raise RuntimeError("initial evaluation is not available")
        return self.initial_evaluation

    def _ctx(self) -> RepairPipelineContext:
        if self.ctx is None:
            raise RuntimeError("repair pipeline context is not available")
        return self.ctx

    def _outcome(self) -> RepairOutcome:
        if self.outcome is None:
            raise RuntimeError("repair outcome is not available")
        return self.outcome
