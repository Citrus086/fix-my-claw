"""Session-related repair stages.

This module contains stages that interact with OpenClaw sessions:
- SessionPauseStage: Send soft pause message to sessions
- SessionTerminateStage: Terminate existing sessions
- SessionResetStage: Create new sessions after termination
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..repair_types import (
    SessionStageData,
    StageResult,
    _coerce_execution_records,
    _require_stage_payload,
)

if TYPE_CHECKING:
    from ..repair_types import RepairPipelineContext, StagePayload


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
        from ..repair import _run_session_command_stage, write_repair_progress

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
        from ..repair import _run_session_command_stage

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
    """Stage that creates new OpenClaw sessions after termination.

    Optionally waits after the previous stage before creating new sessions.
    """

    def run(
        self,
        ctx: RepairPipelineContext,
        *,
        previous_stage: StageResult | None = None,
    ) -> StageResult:
        """Create new sessions.

        Args:
            ctx: Pipeline context.
            previous_stage: Optional previous stage result for timing.

        Returns:
            StageResult with SessionStageData containing command records.
        """
        from ..repair import _run_session_command_stage

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
