"""Public repair entry points."""

from __future__ import annotations

from . import repair_ops
from . import repair_runtime
from . import shared as shared_module
from .config import AppConfig
from .repair_state_machine import RepairStateMachine
from .repair_types import RepairPipelineContext, RepairResult, RepairOutcome, StageResult
from .state import StateStore

clear_repair_progress = shared_module.clear_repair_progress
write_repair_progress = shared_module.write_repair_progress

__all__ = [
    "attempt_repair",
    "RepairResult",
    "RepairOutcome",
    "RepairPipelineContext",
    "StageResult",
    "write_repair_progress",
    "clear_repair_progress",
]


def attempt_repair(
    cfg: AppConfig,
    store: StateStore,
    *,
    force: bool,
    reason: str | None = None,
) -> RepairResult:
    """Attempt to repair OpenClaw using the configured repair pipeline."""
    return RepairStateMachine(
        cfg=cfg,
        store=store,
        force=force,
        reason=reason,
        manual_start=bool(reason and reason.startswith("manual_")),
        reassess_after_terminate=(reason == repair_ops.QUEUE_CONTAMINATION_REPAIR_REASON),
        hooks=repair_runtime._build_repair_state_machine_hooks(),
    ).run()
