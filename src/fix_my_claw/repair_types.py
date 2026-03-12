"""Repair pipeline type definitions and legacy details conversion helpers.

This module contains:
- Result models: RepairResult, RepairOutcome
- Stage payload dataclasses: SessionStageData, PauseCheckStageData, etc.
- Stage result types: StageResult, StagePayload
- Context types: RepairPipelineContext
- Legacy details conversion helpers

These types are shared across the repair state machine, runtime hooks,
and individual stage implementations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import AppConfig
from .health import HealthEvaluation
from .runtime import CmdResult
from .state import StateStore


@dataclass(frozen=True)
class CommandExecutionRecord:
    argv: list[str]
    exit_code: int
    duration_ms: int
    stdout_path: str
    stderr_path: str
    agent: str | None = None
    session_id: str | None = None

    @staticmethod
    def from_mapping(data: dict[str, Any]) -> "CommandExecutionRecord":
        return CommandExecutionRecord(
            argv=list(data.get("argv", [])),
            exit_code=int(data.get("exit_code", 0)),
            duration_ms=int(data.get("duration_ms", 0)),
            stdout_path=str(data.get("stdout_path", "")),
            stderr_path=str(data.get("stderr_path", "")),
            agent=str(data["agent"]) if data.get("agent") is not None else None,
            session_id=str(data["session_id"]) if data.get("session_id") is not None else None,
        )

    def to_json(self) -> dict[str, Any]:
        out = {
            "argv": self.argv,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "stdout_path": self.stdout_path,
            "stderr_path": self.stderr_path,
        }
        if self.agent is not None:
            out["agent"] = self.agent
        if self.session_id is not None:
            out["session_id"] = self.session_id
        return out


@dataclass(frozen=True)
class SessionStageData:
    commands: tuple[CommandExecutionRecord, ...]


@dataclass(frozen=True)
class PauseCheckStageData:
    waited_before_seconds: int = 0


@dataclass(frozen=True)
class OfficialRepairStageData:
    steps: tuple[CommandExecutionRecord, ...]
    break_reason: str


@dataclass(frozen=True)
class AiDecision:
    asked: bool
    decision: str
    raw: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_mapping(data: dict[str, Any]) -> "AiDecision":
        asked = bool(data.get("asked"))
        decision = str(data.get("decision", ""))
        raw = dict(data)
        raw.setdefault("asked", asked)
        raw.setdefault("decision", decision)
        return AiDecision(asked=asked, decision=decision, raw=raw)

    def to_json(self) -> dict[str, Any]:
        return dict(self.raw)


@dataclass(frozen=True)
class BackupArtifact:
    source: str | None = None
    archive: str | None = None
    error: str | None = None

    @staticmethod
    def from_mapping(data: dict[str, Any]) -> "BackupArtifact":
        return BackupArtifact(
            source=str(data["source"]) if data.get("source") is not None else None,
            archive=str(data["archive"]) if data.get("archive") is not None else None,
        )

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.source is not None:
            out["source"] = self.source
        if self.archive is not None:
            out["archive"] = self.archive
        if self.error is not None:
            out["error"] = self.error
        return out


@dataclass(frozen=True)
class AiRepairStageData:
    result: CmdResult


StagePayload = SessionStageData | PauseCheckStageData | OfficialRepairStageData | AiDecision | BackupArtifact | AiRepairStageData | None


@dataclass(frozen=True)
class StageResult:
    name: str
    status: str
    payload: StagePayload = None
    evaluation: HealthEvaluation | None = None
    context: dict[str, Any] | None = None
    notification: dict[str, Any] | None = None
    stop_reason: str | None = None
    used_ai: bool = False

    @property
    def fixed(self) -> bool:
        return bool(self.evaluation and self.evaluation.effective_healthy)


@dataclass(frozen=True)
class RepairPipelineContext:
    cfg: AppConfig
    store: StateStore
    attempt_dir: Path
    runtime: Any | None = None


@dataclass
class RepairOutcome:
    attempt_dir: str
    reason: str | None = None
    start_notification: dict[str, Any] | None = None
    before_context: dict[str, Any] | None = None
    stages: list[StageResult] = field(default_factory=list)
    final_stage: StageResult | None = None
    final_notification: dict[str, Any] | None = None

    def add_stage(self, stage: StageResult) -> StageResult:
        self.stages.append(stage)
        return stage

    @property
    def used_ai(self) -> bool:
        return any(stage.used_ai for stage in self.stages)

    @property
    def fixed(self) -> bool:
        final = self.final_stage or self._last_stage_with_evaluation()
        return bool(final and final.evaluation and final.evaluation.effective_healthy)

    def _last_stage_with_evaluation(self) -> StageResult | None:
        for stage in reversed(self.stages):
            if stage.evaluation is not None:
                return stage
        return None

    def to_legacy_details(self) -> dict[str, Any]:
        out: dict[str, Any] = {"attempt_dir": self.attempt_dir}
        if self.reason:
            out["reason"] = self.reason
        if self.start_notification is not None:
            out["notify_start"] = self.start_notification
        if self.before_context is not None:
            out["context_before"] = self.before_context

        for stage in self.stages:
            if stage.name == "pause":
                payload = _require_stage_payload(stage, SessionStageData)
                out["pause_stage"] = _records_to_json(payload.commands)
            elif stage.name == "pause_check":
                payload = _require_stage_payload(stage, PauseCheckStageData)
                out["pause_wait_seconds"] = payload.waited_before_seconds
                if stage.context is not None:
                    out["context_after_pause"] = stage.context
                if stage.evaluation and stage.evaluation.anomaly_guard is not None:
                    out["anomaly_guard_after_pause"] = stage.evaluation.anomaly_guard
            elif stage.name == "terminate":
                payload = _require_stage_payload(stage, SessionStageData)
                out["terminate_stage"] = _records_to_json(payload.commands)
            elif stage.name == "terminate_check":
                if stage.context is not None:
                    out["context_after_terminate"] = stage.context
                if stage.evaluation and stage.evaluation.anomaly_guard is not None:
                    out["anomaly_guard_after_terminate"] = stage.evaluation.anomaly_guard
            elif stage.name == "new":
                payload = _require_stage_payload(stage, SessionStageData)
                out["new_stage"] = _records_to_json(payload.commands)
            elif stage.name == "official":
                payload = _require_stage_payload(stage, OfficialRepairStageData)
                out["official"] = _records_to_json(payload.steps)
                out["official_break_reason"] = payload.break_reason
                if stage.context is not None:
                    out["context_after_official"] = stage.context
                if stage.evaluation and stage.evaluation.anomaly_guard is not None:
                    out["anomaly_guard_after_official"] = stage.evaluation.anomaly_guard
            elif stage.name == "ai_decision":
                payload = _require_stage_payload(stage, AiDecision)
                out["ai_decision"] = payload.to_json()
            elif stage.name == "backup":
                payload = _require_stage_payload(stage, BackupArtifact)
                if payload.error is not None:
                    out["backup_before_ai_error"] = payload.error
                else:
                    out["backup_before_ai"] = payload.to_json()
                if stage.notification is not None:
                    out["notify_backup"] = stage.notification
            elif stage.name == "ai_config":
                payload = _require_stage_payload(stage, AiRepairStageData)
                out["ai_stage"] = "config"
                out["ai_result_config"] = _cmd_result_to_json(payload.result)
                if stage.context is not None:
                    out["context_after_ai_config"] = stage.context
                if stage.evaluation and stage.evaluation.anomaly_guard is not None:
                    out["anomaly_guard_after_ai_config"] = stage.evaluation.anomaly_guard
            elif stage.name == "ai_code":
                payload = _require_stage_payload(stage, AiRepairStageData)
                out["ai_stage"] = "code"
                out["ai_result_code"] = _cmd_result_to_json(payload.result)
                if stage.context is not None:
                    out["context_after_ai_code"] = stage.context
                if stage.evaluation and stage.evaluation.anomaly_guard is not None:
                    out["anomaly_guard_after_ai_code"] = stage.evaluation.anomaly_guard
            elif stage.name == "final":
                if stage.context is not None:
                    out["context_final"] = stage.context
                if stage.evaluation and stage.evaluation.anomaly_guard is not None:
                    out["anomaly_guard_final"] = stage.evaluation.anomaly_guard

        if self.final_notification is not None:
            out["notify_final"] = self.final_notification
        return out


@dataclass(frozen=True)
class RepairResult:
    attempted: bool
    fixed: bool
    used_ai: bool
    outcome: RepairOutcome | None = None
    details_data: dict[str, Any] = field(default_factory=dict)

    @property
    def details(self) -> dict[str, Any]:
        if self.outcome is not None:
            return self.outcome.to_legacy_details()
        return self.details_data

    def to_json(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "fixed": self.fixed,
            "used_ai": self.used_ai,
            "details": self.details,
        }


# Legacy details conversion helpers

def _records_to_json(records: tuple[CommandExecutionRecord, ...]) -> list[dict[str, Any]]:
    return [record.to_json() for record in records]


def _coerce_execution_records(items: list[dict[str, Any]]) -> tuple[CommandExecutionRecord, ...]:
    return tuple(CommandExecutionRecord.from_mapping(item) for item in items)


def _cmd_result_to_json(result: CmdResult) -> dict[str, Any]:
    return {
        "argv": result.argv,
        "cwd": str(result.cwd) if result.cwd is not None else None,
        "exit_code": result.exit_code,
        "duration_ms": result.duration_ms,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _require_stage_payload(stage: StageResult, expected_type: type[Any]) -> Any:
    if stage.payload is None or not isinstance(stage.payload, expected_type):
        raise TypeError(f"stage {stage.name} expected payload {expected_type.__name__}")
    return stage.payload
