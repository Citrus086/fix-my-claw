"""Final assessment repair stage.

This module contains the stage that performs final health evaluation
after all repair attempts.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..repair_types import RepairPipelineContext, StageResult


@dataclass(frozen=True)
class FinalAssessmentStage:
    """Stage that performs final health assessment.

    Evaluates system health at the end of the repair pipeline
    to determine if the repair was successful.
    """

    stage_name: str

    def run(self, ctx: RepairPipelineContext) -> StageResult:
        """Perform final health assessment.

        Args:
            ctx: Pipeline context.

        Returns:
            StageResult with health evaluation.
        """
        from ..repair import _evaluate_with_context
        from ..repair_types import StageResult

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
