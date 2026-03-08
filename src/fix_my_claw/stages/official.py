"""Official repair steps stage.

This module contains the stage that runs configured official repair steps.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..repair_types import (
    OfficialRepairStageData,
    StageResult,
    _coerce_execution_records,
)

if TYPE_CHECKING:
    from ..repair_types import RepairPipelineContext


@dataclass(frozen=True)
class OfficialRepairStage:
    """Stage that runs official repair steps.

    Executes configured repair commands in sequence, stopping early
    if health is restored.
    """

    def run(self, ctx: RepairPipelineContext) -> StageResult:
        """Run official repair steps.

        Args:
            ctx: Pipeline context.

        Returns:
            StageResult with OfficialRepairStageData and health evaluation.
        """
        from ..repair import _collect_context, _run_official_steps, write_repair_progress

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
