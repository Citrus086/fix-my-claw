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
from .base import require_runtime_hooks, write_stage_progress

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
        runtime = require_runtime_hooks(ctx)
        write_stage_progress(
            ctx.cfg.monitor.state_dir,
            "official",
            "running",
            str(ctx.attempt_dir.resolve()),
            runtime.write_repair_progress_fn,
        )
        steps, evaluation, break_reason = runtime.run_official_steps_fn(
            ctx.cfg,
            ctx.attempt_dir,
            break_on_healthy=True,
        )
        write_stage_progress(
            ctx.cfg.monitor.state_dir,
            "official",
            "completed",
            str(ctx.attempt_dir.resolve()),
            runtime.write_repair_progress_fn,
        )
        return StageResult(
            name="official",
            status="completed",
            payload=OfficialRepairStageData(
                steps=_coerce_execution_records(steps),
                break_reason=break_reason,
            ),
            evaluation=evaluation,
            context=runtime.collect_context_fn(evaluation, ctx.attempt_dir, stage_name="after_official"),
            stop_reason=break_reason,
        )
