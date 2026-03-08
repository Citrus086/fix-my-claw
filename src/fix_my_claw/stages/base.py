"""Lightweight base for repair stages.

This module provides minimal protocol/base class for stages.
Stages are NOT required to inherit from a heavy base class.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ..repair_types import RepairPipelineContext, StageResult


class RepairStage(Protocol):
    """Protocol for repair stages.

    Stages only need to implement the `run` method.
    No heavy base class inheritance required.
    """

    def run(self, ctx: RepairPipelineContext) -> StageResult:
        """Execute the stage and return result.

        Args:
            ctx: Pipeline context containing config, store, and attempt_dir.

        Returns:
            StageResult with name, status, payload, and optional evaluation.
        """
        ...


class StageWithProgress(Protocol):
    """Protocol for stages that write repair progress.

    Some stages need to write progress before/after execution.
    This is optional - only stages that need progress tracking implement this.
    """

    stage_name: str

    def run(self, ctx: RepairPipelineContext) -> StageResult:
        """Execute the stage and return result."""
        ...


def write_stage_progress(
    state_dir,
    stage_name: str,
    status: str,
    attempt_dir: str,
    write_repair_progress_fn,
) -> None:
    """Helper to write progress for stages that need it.

    Args:
        state_dir: State directory path.
        stage_name: Name of the stage.
        status: Status string (e.g., "running", "completed", "failed").
        attempt_dir: Attempt directory path.
        write_repair_progress_fn: Function to write progress.
    """
    write_repair_progress_fn(
        state_dir,
        stage=stage_name,
        status=status,
        attempt_dir=attempt_dir,
    )
