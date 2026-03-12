"""AI-assisted repair stages.

This module contains stages related to AI-assisted remediation:
- AiDecisionStage: Ask user whether to proceed with AI repair
- BackupStage: Backup OpenClaw state before AI modifications
- AiRepairStage: Execute AI repair commands (config or code)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..messages import backup_completed
from ..repair_types import (
    AiDecision,
    AiRepairStageData,
    BackupArtifact,
    StageResult,
)
from .base import require_runtime_hooks, write_stage_progress

if TYPE_CHECKING:
    from ..repair_types import RepairPipelineContext


NOTIFY_LEVEL_ALL = "all"
NOTIFY_LEVEL_IMPORTANT = "important"


@dataclass(frozen=True)
class AiDecisionStage:
    """Stage that asks user whether to proceed with AI repair.

    Can be preset with a decision for testing purposes.
    """

    preset: dict[str, Any] | None = None

    def run(self, ctx: RepairPipelineContext) -> StageResult:
        """Get AI repair decision from user.

        Args:
            ctx: Pipeline context.

        Returns:
            StageResult with AiDecision payload.
        """
        runtime = require_runtime_hooks(ctx)
        write_stage_progress(
            ctx.cfg.monitor.state_dir,
            "ai_decision",
            "running",
            str(ctx.attempt_dir.resolve()),
            runtime.write_repair_progress_fn,
        )
        decision = self.preset or runtime.ask_user_enable_ai_fn(ctx.cfg, ctx.attempt_dir)
        payload = AiDecision.from_mapping(decision)
        notification_text = runtime.ai_decision_notification_text_fn(payload)
        write_stage_progress(
            ctx.cfg.monitor.state_dir,
            "ai_decision",
            "completed",
            str(ctx.attempt_dir.resolve()),
            runtime.write_repair_progress_fn,
        )
        return StageResult(
            name="ai_decision",
            status="completed",
            payload=payload,
            notification=(
                runtime.dispatch_notification_fn(
                    ctx.cfg,
                    kind="ai_approval_status",
                    source="ai_approval",
                    text=notification_text,
                    level=NOTIFY_LEVEL_ALL,
                    silent=False,
                    dedupe_key=f"ai_approval_status:{ctx.attempt_dir.resolve()}:{payload.decision}",
                )
                if notification_text is not None
                else None
            ),
        )


@dataclass(frozen=True)
class BackupStage:
    """Stage that backs up OpenClaw state before AI modifications.

    Creates a backup archive that can be used to restore if AI
    modifications cause issues.
    """

    def run(self, ctx: RepairPipelineContext) -> StageResult:
        """Backup OpenClaw state.

        Args:
            ctx: Pipeline context.

        Returns:
            StageResult with BackupArtifact payload.
        """
        runtime = require_runtime_hooks(ctx)
        write_stage_progress(
            ctx.cfg.monitor.state_dir,
            "backup",
            "running",
            str(ctx.attempt_dir.resolve()),
            runtime.write_repair_progress_fn,
        )
        try:
            artifact = BackupArtifact.from_mapping(runtime.backup_openclaw_state_fn(ctx.cfg, ctx.attempt_dir))
        except Exception as exc:
            write_stage_progress(
                ctx.cfg.monitor.state_dir,
                "backup",
                "failed",
                str(ctx.attempt_dir.resolve()),
                runtime.write_repair_progress_fn,
            )
            return StageResult(
                name="backup",
                status="failed",
                payload=BackupArtifact(error=str(exc)),
                stop_reason="backup_error",
            )
        write_stage_progress(
            ctx.cfg.monitor.state_dir,
            "backup",
            "completed",
            str(ctx.attempt_dir.resolve()),
            runtime.write_repair_progress_fn,
        )
        return StageResult(
            name="backup",
            status="completed",
            payload=artifact,
            notification=runtime.dispatch_notification_fn(
                ctx.cfg,
                kind="ai_approval_status",
                source="ai_approval",
                text=backup_completed(artifact.archive),
                level=NOTIFY_LEVEL_IMPORTANT,
                silent=False,
                dedupe_key=f"ai_approval_status:{ctx.attempt_dir.resolve()}:backup_completed",
            ),
        )


@dataclass(frozen=True)
class AiRepairStage:
    """Stage that executes AI repair commands.

    Runs either config-stage or code-stage AI remediation based on
    the code_stage parameter.
    """

    code_stage: bool

    def run(self, ctx: RepairPipelineContext) -> StageResult:
        """Execute AI repair.

        Args:
            ctx: Pipeline context.

        Returns:
            StageResult with AiRepairStageData and health evaluation.
        """
        runtime = require_runtime_hooks(ctx)
        result = runtime.run_ai_repair_fn(ctx.cfg, ctx.attempt_dir, code_stage=self.code_stage)
        stage_suffix = "code" if self.code_stage else "config"
        evaluation, context = runtime.evaluate_with_context_fn(
            ctx.cfg,
            ctx.attempt_dir,
            stage_name=f"after_ai_{stage_suffix}",
        )
        return StageResult(
            name=f"ai_{stage_suffix}",
            status="completed",
            payload=AiRepairStageData(result=result),
            evaluation=evaluation,
            context=context,
            used_ai=True,
        )
