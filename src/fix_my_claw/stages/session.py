"""Session-related repair stages.

This module contains stages that interact with OpenClaw sessions:
- SessionPauseStage: Send soft pause message to sessions
- SessionTerminateStage: Terminate existing sessions
- SessionTerminateAssessmentStage: Recheck health after a hard stop
- SessionResetStage: Create new sessions after termination
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..repair_types import (
    SessionStageData,
    StageResult,
    _coerce_execution_records,
    _require_stage_payload,
)
from .base import require_runtime_hooks, write_stage_progress

if TYPE_CHECKING:
    from ..repair_types import RepairPipelineContext


@dataclass(frozen=True)
class SessionPauseStage:
    """Stage that sends pause message to active OpenClaw sessions.

    This is the "soft pause" approach - asks sessions to pause gracefully
    before attempting harder reset methods.
    """

    def run(self, ctx: RepairPipelineContext) -> StageResult:
        """Send pause message to sessions.

        Args:
            ctx: Pipeline context.

        Returns:
            StageResult with SessionStageData containing command records.
        """
        runtime = require_runtime_hooks(ctx)
        write_stage_progress(
            ctx.cfg.monitor.state_dir,
            "pause",
            "running",
            str(ctx.attempt_dir.resolve()),
            runtime.write_repair_progress_fn,
        )
        commands = _coerce_execution_records(
            runtime.run_session_command_stage_fn(
                ctx.cfg,
                ctx.attempt_dir,
                stage_name="pause",
                message_text=ctx.cfg.repair.pause_message,
            )
        )
        write_stage_progress(
            ctx.cfg.monitor.state_dir,
            "pause",
            "completed",
            str(ctx.attempt_dir.resolve()),
            runtime.write_repair_progress_fn,
        )
        return StageResult(
            name="pause",
            status="completed",
            payload=SessionStageData(commands=commands),
        )


@dataclass(frozen=True)
class SessionTerminateStage:
    """Stage that terminates all active OpenClaw sessions.

    This sends the terminate message to gracefully stop sessions.
    """

    def run(self, ctx: RepairPipelineContext) -> StageResult:
        """Terminate sessions.

        Args:
            ctx: Pipeline context.

        Returns:
            StageResult with SessionStageData containing command records.
        """
        runtime = require_runtime_hooks(ctx)
        commands = _coerce_execution_records(
            runtime.run_session_command_stage_fn(
                ctx.cfg,
                ctx.attempt_dir,
                stage_name="terminate",
                message_text=ctx.cfg.repair.terminate_message,
            )
        )
        return StageResult(
            name="terminate",
            status="completed",
            payload=SessionStageData(commands=commands),
        )


@dataclass(frozen=True)
class SessionTerminateAssessmentStage:
    """Stage that assesses system health after a hard stop.

    This is used for queue-contamination-style incidents where `/stop`
    should be allowed to settle before deciding whether `/new` is still needed.
    """

    def run(
        self,
        ctx: RepairPipelineContext,
        *,
        previous_stage: StageResult,
    ) -> StageResult:
        """Assess health after terminate.

        Args:
            ctx: Pipeline context.
            previous_stage: The terminate stage result.

        Returns:
            StageResult with health evaluation and captured context.
        """
        payload = _require_stage_payload(previous_stage, SessionStageData)
        runtime = require_runtime_hooks(ctx)
        if payload.commands and ctx.cfg.repair.session_stage_wait_seconds > 0:
            time.sleep(ctx.cfg.repair.session_stage_wait_seconds)
        evaluation, context = runtime.evaluate_with_context_fn(
            ctx.cfg,
            ctx.attempt_dir,
            stage_name="after_terminate",
        )
        return StageResult(
            name="terminate_check",
            status="completed",
            evaluation=evaluation,
            context=context,
            stop_reason="healthy_after_terminate" if evaluation.effective_healthy else "still_unhealthy_after_terminate",
        )


@dataclass(frozen=True)
class SessionResetStage:
    """Stage that creates new OpenClaw sessions after termination.

    Optionally waits after terminate before creating new sessions.
    """

    def run(
        self,
        ctx: RepairPipelineContext,
        *,
        previous_stage: StageResult,
        wait_before_reset: bool,
    ) -> StageResult:
        """Create new sessions.

        Args:
            ctx: Pipeline context.
            previous_stage: Terminate stage result.
            wait_before_reset: Whether to wait after terminate before sending `/new`.

        Returns:
            StageResult with SessionStageData containing command records.
        """
        runtime = require_runtime_hooks(ctx)
        if wait_before_reset:
            payload = _require_stage_payload(previous_stage, SessionStageData)
            if payload.commands and ctx.cfg.repair.session_stage_wait_seconds > 0:
                time.sleep(ctx.cfg.repair.session_stage_wait_seconds)
        commands = _coerce_execution_records(
            runtime.run_session_command_stage_fn(
                ctx.cfg,
                ctx.attempt_dir,
                stage_name="new",
                message_text=ctx.cfg.repair.new_message,
            )
        )
        return StageResult(
            name="new",
            status="completed",
            payload=SessionStageData(commands=commands),
        )
