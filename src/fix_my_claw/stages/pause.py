"""Pause assessment repair stage.

This module contains the stage that evaluates system health after
a soft pause has been applied.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..repair_types import (
    PauseCheckStageData,
    SessionStageData,
    StageResult,
    _require_stage_payload,
)

if TYPE_CHECKING:
    from ..repair_types import RepairPipelineContext


@dataclass(frozen=True)
class PauseAssessmentStage:
    """Stage that assesses system health after soft pause.

    Waits for a configurable period after pause, then evaluates health
    to determine if the pause was sufficient to resolve the issue.
    """

    def run(
        self,
        ctx: RepairPipelineContext,
        *,
        previous_stage: StageResult,
    ) -> StageResult:
        """Assess health after pause.

        Args:
            ctx: Pipeline context.
            previous_stage: The pause stage result.

        Returns:
            StageResult with PauseCheckStageData and health evaluation.
        """
        from ..repair import _evaluate_with_context

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
