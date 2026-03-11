"""Repair stages module.

This module exports all repair stage classes. Stages are responsible
for executing individual steps in the repair pipeline.

Stage categories:
- Session stages: Handle OpenClaw session lifecycle
- Pause stage: Assess health after soft pause
- Official stage: Run configured repair commands
- AI stages: AI-assisted remediation (decision, backup, repair)
- Final stage: Final health assessment
"""

from .ai import AiDecisionStage, AiRepairStage, BackupStage
from .base import RepairStage, StageWithProgress, write_stage_progress
from .final import FinalAssessmentStage
from .official import OfficialRepairStage
from .pause import PauseAssessmentStage
from .session import (
    SessionPauseStage,
    SessionResetStage,
    SessionTerminateAssessmentStage,
    SessionTerminateStage,
)

__all__ = [
    # Base
    "RepairStage",
    "StageWithProgress",
    "write_stage_progress",
    # Session stages
    "SessionPauseStage",
    "SessionTerminateStage",
    "SessionTerminateAssessmentStage",
    "SessionResetStage",
    # Pause stage
    "PauseAssessmentStage",
    # Official stage
    "OfficialRepairStage",
    # AI stages
    "AiDecisionStage",
    "BackupStage",
    "AiRepairStage",
    # Final stage
    "FinalAssessmentStage",
]
