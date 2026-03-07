from __future__ import annotations

import json
import logging
import re
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from string import Template
from typing import Any

from .anomaly_guard import _analyze_anomaly_guard
from .config import AppConfig
from .health import HealthEvaluation, probe_health, probe_logs, probe_status
from .notify import _ask_user_enable_ai, _notify_send
from .runtime import CmdResult, run_cmd
from .shared import _parse_json_maybe, _write_attempt_file, ensure_dir, redact_text, truncate_for_log
from .state import StateStore, _now_ts


def _parse_agent_id_from_session_key(key: str) -> str | None:
    match = re.match(r"^agent:([^:]+):", key or "")
    if not match:
        return None
    return match.group(1)


def _list_active_sessions(cfg: AppConfig, *, active_minutes: int) -> list[dict[str, Any]]:
    argv = [
        cfg.openclaw.command,
        "sessions",
        "--all-agents",
        "--active",
        str(active_minutes),
        "--json",
    ]
    cwd = cfg.openclaw.workspace_dir if cfg.openclaw.workspace_dir.exists() else None
    res = run_cmd(argv, timeout_seconds=max(15, cfg.monitor.probe_timeout_seconds), cwd=cwd)
    data = _parse_json_maybe(res.stdout)
    if not res.ok or not isinstance(data, dict):
        return []
    sessions = data.get("sessions", [])
    if not isinstance(sessions, list):
        return []
    out: list[dict[str, Any]] = []
    for item in sessions:
        if isinstance(item, dict):
            out.append(item)
    return out


def _backup_openclaw_state(cfg: AppConfig, attempt_dir: Path) -> dict[str, Any]:
    src = cfg.openclaw.state_dir
    if not src.exists():
        raise FileNotFoundError(f"openclaw state dir not found: {src}")
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    parent = src.parent
    archive_base = parent / f"{src.name}.backup-{stamp}"
    archive_path = shutil.make_archive(
        base_name=str(archive_base),
        format="gztar",
        root_dir=str(parent),
        base_dir=src.name,
    )
    out = {"source": str(src), "archive": archive_path}
    _write_attempt_file(attempt_dir, "backup.json", json.dumps(out, ensure_ascii=False, indent=2))
    return out


def _run_session_command_stage(
    cfg: AppConfig,
    attempt_dir: Path,
    *,
    stage_name: str,
    message_text: str,
) -> list[dict[str, Any]]:
    repair_log = logging.getLogger("fix_my_claw.repair")
    results: list[dict[str, Any]] = []
    if not cfg.repair.session_control_enabled or not message_text.strip():
        return results
    sessions = _list_active_sessions(cfg, active_minutes=cfg.repair.session_active_minutes)
    allow_agents = set(cfg.repair.session_agents)
    for session in sessions:
        key = str(session.get("key", ""))
        agent_id = _parse_agent_id_from_session_key(key) or str(session.get("agentId", ""))
        if not agent_id or agent_id not in allow_agents:
            continue
        session_id = str(session.get("sessionId", "")).strip()
        if not session_id:
            continue
        argv = [
            cfg.openclaw.command,
            "agent",
            "--agent",
            agent_id,
            "--session-id",
            session_id,
            "--message",
            message_text,
        ]
        cwd = cfg.openclaw.workspace_dir if cfg.openclaw.workspace_dir.exists() else None
        res = run_cmd(argv, timeout_seconds=cfg.repair.session_command_timeout_seconds, cwd=cwd)
        repair_log.warning(
            "%s stage: agent=%s session=%s exit=%s", stage_name, agent_id, session_id, res.exit_code
        )
        idx = len(results) + 1
        stdout_name = f"{stage_name}.{idx}.stdout.txt"
        stderr_name = f"{stage_name}.{idx}.stderr.txt"
        _write_attempt_file(attempt_dir, stdout_name, redact_text(res.stdout))
        _write_attempt_file(attempt_dir, stderr_name, redact_text(res.stderr))
        results.append(
            {
                "agent": agent_id,
                "session_id": session_id,
                "argv": res.argv,
                "exit_code": res.exit_code,
                "duration_ms": res.duration_ms,
                "stdout_path": str((attempt_dir / stdout_name).resolve()),
                "stderr_path": str((attempt_dir / stderr_name).resolve()),
            }
        )
    return results


def _attempt_dir(cfg: AppConfig) -> Path:
    base = cfg.monitor.state_dir / "attempts"
    ensure_dir(base)
    ts = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    return Path(tempfile.mkdtemp(prefix=f"{ts}-", dir=str(base)))


def _context_logs_timeout_seconds(cfg: AppConfig) -> int:
    return max(cfg.monitor.probe_timeout_seconds, cfg.anomaly_guard.probe_timeout_seconds)


def _evaluate_with_context(
    cfg: AppConfig,
    attempt_dir: Path,
    *,
    stage_name: str,
    log_probe_failures: bool = False,
) -> tuple[HealthEvaluation, dict]:
    evaluation = _evaluate_health(
        cfg,
        log_probe_failures=log_probe_failures,
        capture_logs=True,
        logs_timeout_seconds=_context_logs_timeout_seconds(cfg),
    )
    context = _collect_context(evaluation, attempt_dir, stage_name=stage_name)
    return evaluation, context


def _collect_context(evaluation: HealthEvaluation, attempt_dir: Path, *, stage_name: str) -> dict:
    logs = evaluation.logs_probe
    prefix = f"context.{stage_name}"
    health_stdout = f"{prefix}.health.stdout.txt"
    health_stderr = f"{prefix}.health.stderr.txt"
    status_stdout = f"{prefix}.status.stdout.txt"
    status_stderr = f"{prefix}.status.stderr.txt"
    logs_file = f"{prefix}.openclaw.logs.txt" if logs is not None else None

    _write_attempt_file(attempt_dir, health_stdout, redact_text(evaluation.health_probe.cmd.stdout))
    _write_attempt_file(attempt_dir, health_stderr, redact_text(evaluation.health_probe.cmd.stderr))
    _write_attempt_file(attempt_dir, status_stdout, redact_text(evaluation.status_probe.cmd.stdout))
    _write_attempt_file(attempt_dir, status_stderr, redact_text(evaluation.status_probe.cmd.stderr))
    if logs is not None and logs_file is not None:
        logs_text = logs.stdout + ("\n" + logs.stderr if logs.stderr else "")
        _write_attempt_file(attempt_dir, logs_file, redact_text(logs_text))

    return {
        "healthy": evaluation.effective_healthy,
        "probe_healthy": evaluation.probe_healthy,
        "reason": evaluation.reason,
        "health": evaluation.health,
        "status": evaluation.status,
        "logs": (
            {
                "ok": logs.ok,
                "exit_code": logs.exit_code,
                "duration_ms": logs.duration_ms,
                "argv": logs.argv,
                "stdout_path": str((attempt_dir / logs_file).resolve()),
            }
            if logs is not None and logs_file is not None
            else None
        ),
        "attempt_dir": str(attempt_dir.resolve()),
    }


def _evaluate_health(
    cfg: AppConfig,
    *,
    log_probe_failures: bool = False,
    capture_logs: bool = False,
    logs_timeout_seconds: int | None = None,
) -> HealthEvaluation:
    health = probe_health(cfg, log_on_fail=log_probe_failures)
    status = probe_status(cfg, log_on_fail=log_probe_failures)
    probe_healthy = health.ok and status.ok
    effective_healthy = probe_healthy
    reason: str | None = None
    logs_probe: CmdResult | None = None
    anomaly_guard: dict | None = None
    should_collect_logs = capture_logs or (probe_healthy and cfg.anomaly_guard.enabled)
    if should_collect_logs:
        logs_probe = probe_logs(
            cfg,
            timeout_seconds=logs_timeout_seconds or cfg.anomaly_guard.probe_timeout_seconds,
        )
    if not probe_healthy:
        reason = "probe_failed"
    elif cfg.anomaly_guard.enabled:
        if logs_probe is None:
            raise RuntimeError("anomaly guard requires a logs probe")
        anomaly_guard = _analyze_anomaly_guard(cfg, logs=logs_probe)
        if anomaly_guard.get("triggered"):
            effective_healthy = False
            reason = "anomaly_guard"
    return HealthEvaluation(
        health_probe=health,
        status_probe=status,
        logs_probe=logs_probe,
        anomaly_guard=anomaly_guard,
        probe_healthy=probe_healthy,
        effective_healthy=effective_healthy,
        reason=reason,
    )


def _run_official_steps(
    cfg: AppConfig,
    attempt_dir: Path,
    *,
    break_on_healthy: bool = True,
) -> tuple[list[dict], HealthEvaluation, str]:
    repair_log = logging.getLogger("fix_my_claw.repair")
    results: list[dict] = []
    last_evaluation: HealthEvaluation | None = None
    break_reason = "no_steps"
    total = len(cfg.repair.official_steps)
    for idx, step in enumerate(cfg.repair.official_steps, start=1):
        if not step:
            continue
        argv = [cfg.openclaw.command if step[0] == "openclaw" else step[0], *step[1:]]
        repair_log.warning("official step %d/%d: %s", idx, total, " ".join(argv))
        cwd = cfg.openclaw.workspace_dir if cfg.openclaw.workspace_dir.exists() else None
        res = run_cmd(argv, timeout_seconds=cfg.repair.step_timeout_seconds, cwd=cwd)
        repair_log.warning(
            "official step %d/%d done: exit=%s duration_ms=%s",
            idx,
            total,
            res.exit_code,
            res.duration_ms,
        )
        if res.stderr:
            repair_log.info("official step %d/%d stderr: %s", idx, total, truncate_for_log(res.stderr))
        stdout_name = f"official.{idx}.stdout.txt"
        stderr_name = f"official.{idx}.stderr.txt"
        _write_attempt_file(attempt_dir, stdout_name, redact_text(res.stdout))
        _write_attempt_file(attempt_dir, stderr_name, redact_text(res.stderr))
        results.append(
            {
                "argv": res.argv,
                "exit_code": res.exit_code,
                "duration_ms": res.duration_ms,
                "stdout_path": str((attempt_dir / stdout_name).resolve()),
                "stderr_path": str((attempt_dir / stderr_name).resolve()),
            }
        )
        time.sleep(cfg.repair.post_step_wait_seconds)
        last_evaluation = _evaluate_health(
            cfg,
            log_probe_failures=False,
            capture_logs=True,
            logs_timeout_seconds=_context_logs_timeout_seconds(cfg),
        )
        break_reason = "steps_exhausted"
        if break_on_healthy and last_evaluation.effective_healthy:
            break_reason = "healthy"
            repair_log.warning("OpenClaw is healthy after official step %d/%d", idx, total)
            break
    if last_evaluation is None:
        last_evaluation = _evaluate_health(
            cfg,
            log_probe_failures=False,
            capture_logs=True,
            logs_timeout_seconds=_context_logs_timeout_seconds(cfg),
        )
    return results, last_evaluation, break_reason


def _load_prompt_text(name: str) -> str:
    from importlib.resources import files

    return (files("fix_my_claw.prompts") / name).read_text(encoding="utf-8")


def _build_ai_cmd(cfg: AppConfig, *, code_stage: bool) -> list[str]:
    variables = {
        "workspace_dir": str(cfg.openclaw.workspace_dir),
        "openclaw_state_dir": str(cfg.openclaw.state_dir),
        "monitor_state_dir": str(cfg.monitor.state_dir),
    }
    args = cfg.ai.args_code if code_stage else cfg.ai.args
    rendered = [Template(arg).safe_substitute(variables) for arg in args]
    argv = [cfg.ai.command]
    if cfg.ai.model:
        argv += ["-m", cfg.ai.model]
    argv += rendered
    return argv


def _run_ai_repair(cfg: AppConfig, attempt_dir: Path, *, code_stage: bool) -> CmdResult:
    prompt_name = "repair_code.md" if code_stage else "repair.md"
    prompt = Template(_load_prompt_text(prompt_name)).safe_substitute(
        {
            "attempt_dir": str(attempt_dir.resolve()),
            "workspace_dir": str(cfg.openclaw.workspace_dir),
            "openclaw_state_dir": str(cfg.openclaw.state_dir),
            "monitor_state_dir": str(cfg.monitor.state_dir),
            "health_cmd": " ".join([cfg.openclaw.command, *cfg.openclaw.health_args]),
            "status_cmd": " ".join([cfg.openclaw.command, *cfg.openclaw.status_args]),
            "logs_cmd": " ".join([cfg.openclaw.command, *cfg.openclaw.logs_args]),
        }
    )

    argv = _build_ai_cmd(cfg, code_stage=code_stage)
    logging.getLogger("fix_my_claw.repair").warning(
        "AI repair (%s) starting: %s", "code" if code_stage else "config", argv
    )
    res = run_cmd(
        argv,
        timeout_seconds=cfg.ai.timeout_seconds,
        cwd=cfg.openclaw.workspace_dir if cfg.openclaw.workspace_dir.exists() else None,
        stdin_text=prompt,
    )
    stage_name = "code" if code_stage else "config"
    _write_attempt_file(attempt_dir, f"ai.{stage_name}.argv.txt", " ".join(argv))
    _write_attempt_file(attempt_dir, f"ai.{stage_name}.stdout.txt", redact_text(res.stdout))
    _write_attempt_file(attempt_dir, f"ai.{stage_name}.stderr.txt", redact_text(res.stderr))
    logging.getLogger("fix_my_claw.repair").warning("AI repair done: exit=%s", res.exit_code)
    if res.stderr:
        logging.getLogger("fix_my_claw.repair").warning("AI stderr: %s", truncate_for_log(res.stderr))
    return res


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
    stage_name: str
    commands: tuple[CommandExecutionRecord, ...]
    waited_before_seconds: int = 0


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
    stage_name: str
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


def _session_stage_has_successful_commands(stage: StageResult) -> bool:
    if not isinstance(stage.payload, SessionStageData):
        return False
    return any(record.exit_code == 0 for record in stage.payload.commands)


def _should_try_soft_pause(cfg: AppConfig, evaluation: HealthEvaluation) -> bool:
    return (
        cfg.repair.soft_pause_enabled
        and cfg.repair.session_control_enabled
        and bool(cfg.repair.pause_message.strip())
        and evaluation.status_probe.ok
    )


@dataclass(frozen=True)
class RepairPipelineContext:
    cfg: AppConfig
    store: StateStore
    attempt_dir: Path


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


@dataclass(frozen=True)
class SessionPauseStage:
    def run(self, ctx: RepairPipelineContext) -> StageResult:
        commands = _coerce_execution_records(
            _run_session_command_stage(
                ctx.cfg,
                ctx.attempt_dir,
                stage_name="pause",
                message_text=ctx.cfg.repair.pause_message,
            )
        )
        return StageResult(
            name="pause",
            status="completed",
            payload=SessionStageData(stage_name="pause", commands=commands),
        )


@dataclass(frozen=True)
class PauseAssessmentStage:
    def run(self, ctx: RepairPipelineContext, *, previous_stage: StageResult) -> StageResult:
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


@dataclass(frozen=True)
class SessionTerminateStage:
    def run(self, ctx: RepairPipelineContext) -> StageResult:
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
    def run(self, ctx: RepairPipelineContext, *, previous_stage: StageResult | None) -> StageResult:
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


@dataclass(frozen=True)
class OfficialRepairStage:
    def run(self, ctx: RepairPipelineContext) -> StageResult:
        steps, evaluation, break_reason = _run_official_steps(
            ctx.cfg,
            ctx.attempt_dir,
            break_on_healthy=True,
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


@dataclass(frozen=True)
class AiDecisionStage:
    preset: dict[str, Any] | None = None

    def run(self, ctx: RepairPipelineContext) -> StageResult:
        # 检查是否有全局 GUI 标志文件（GUI 优先）
        # 标志文件位置：state 目录下（与 attempt_dir 同级）
        gui_flag_file = ctx.attempt_dir.parent.parent / "gui.ask.flag"
        
        if gui_flag_file.exists():
            # GUI 标志存在，读取用户决定
            try:
                with open(gui_flag_file, 'r') as f:
                    flag_data = json.load(f)
                    decision = flag_data.get("decision", "no")
                    # 读取成功后删除标志文件（避免影响后续修复）
                    gui_flag_file.unlink()
                return StageResult(
                    name="ai_decision",
                    status="completed",
                    payload=AiDecision(asked=True, decision=decision),
                )
            except Exception as exc:
                # 读取失败，记录错误后回退到 Discord 询问
                logging.getLogger("fix_my_claw.repair").error(
                    "Failed to read GUI flag: %s", exc
                )
        
        # GUI 标志不存在，使用 Discord 询问（保持现有逻辑）
        decision = _ask_user_enable_ai(ctx.cfg, ctx.attempt_dir)
        return StageResult(
            name="ai_decision",
            status="completed",
            payload=AiDecision.from_mapping(decision),
        )


@dataclass(frozen=True)
class BackupStage:
    def run(self, ctx: RepairPipelineContext) -> StageResult:
        try:
            artifact = BackupArtifact.from_mapping(_backup_openclaw_state(ctx.cfg, ctx.attempt_dir))
        except Exception as exc:
            return StageResult(
                name="backup",
                status="failed",
                payload=BackupArtifact(error=str(exc)),
                stop_reason="backup_error",
            )
        return StageResult(
            name="backup",
            status="completed",
            payload=artifact,
            notification=_notify_send(
                ctx.cfg,
                f"fix-my-claw: 已完成备份，开始 Codex 修复。备份文件：{artifact.archive}",
                silent=False,
            ),
        )


@dataclass(frozen=True)
class AiRepairStage:
    code_stage: bool

    def run(self, ctx: RepairPipelineContext) -> StageResult:
        result = _run_ai_repair(ctx.cfg, ctx.attempt_dir, code_stage=self.code_stage)
        stage_suffix = "code" if self.code_stage else "config"
        evaluation, context = _evaluate_with_context(
            ctx.cfg,
            ctx.attempt_dir,
            stage_name=f"after_ai_{stage_suffix}",
        )
        return StageResult(
            name=f"ai_{stage_suffix}",
            status="completed",
            payload=AiRepairStageData(stage_name=stage_suffix, result=result),
            evaluation=evaluation,
            context=context,
            used_ai=True,
        )


@dataclass(frozen=True)
class FinalAssessmentStage:
    stage_name: str

    def run(self, ctx: RepairPipelineContext) -> StageResult:
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


def _result_from_outcome(*, attempted: bool, outcome: RepairOutcome) -> RepairResult:
    return RepairResult(
        attempted=attempted,
        fixed=outcome.fixed,
        used_ai=outcome.used_ai,
        outcome=outcome,
    )


def attempt_repair(
    cfg: AppConfig,
    store: StateStore,
    *,
    force: bool,
    reason: str | None = None,
) -> RepairResult:
    repair_log = logging.getLogger("fix_my_claw.repair")
    initial_evaluation = _evaluate_health(
        cfg,
        log_probe_failures=False,
        capture_logs=True,
        logs_timeout_seconds=_context_logs_timeout_seconds(cfg),
    )
    if initial_evaluation.effective_healthy:
        repair_log.info("repair skipped: already healthy")
        return RepairResult(attempted=False, fixed=True, used_ai=False, details_data={"already_healthy": True})

    if not cfg.repair.enabled:
        repair_log.warning("repair skipped: disabled by config")
        return RepairResult(attempted=False, fixed=False, used_ai=False, details_data={"repair_disabled": True})

    if not store.can_attempt_repair(cfg.monitor.repair_cooldown_seconds, force=force):
        details: dict[str, object] = {"cooldown": True}
        state = store.load()
        if state.last_repair_ts is not None:
            elapsed = _now_ts() - state.last_repair_ts
            remaining = max(0, cfg.monitor.repair_cooldown_seconds - elapsed)
            details["cooldown_remaining_seconds"] = remaining
            repair_log.info("repair skipped: cooldown (%ss remaining)", remaining)
        else:
            repair_log.info("repair skipped: cooldown")
        return RepairResult(attempted=False, fixed=False, used_ai=False, details_data=details)

    attempt_dir = _attempt_dir(cfg)
    store.mark_repair_attempt()
    ctx = RepairPipelineContext(cfg=cfg, store=store, attempt_dir=attempt_dir)
    outcome = RepairOutcome(attempt_dir=str(attempt_dir.resolve()), reason=reason)
    repair_log.warning("starting repair attempt: dir=%s", attempt_dir.resolve())
    outcome.start_notification = _notify_send(
        cfg,
        "fix-my-claw: 检测到异常，开始分层修复（会话可达时先发送 PAUSE 保留现场；若仍异常，再升级到 /stop -> /new -> 官方结构修复）。",
        silent=False,
    )

    outcome.before_context = _collect_context(initial_evaluation, attempt_dir, stage_name="before")
    if _should_try_soft_pause(cfg, initial_evaluation):
        pause_candidate = SessionPauseStage().run(ctx)
        pause_payload = _require_stage_payload(pause_candidate, SessionStageData)
        if pause_payload.commands:
            pause_stage = outcome.add_stage(pause_candidate)
            if _session_stage_has_successful_commands(pause_stage):
                pause_check_stage = outcome.add_stage(PauseAssessmentStage().run(ctx, previous_stage=pause_stage))
                if pause_check_stage.fixed:
                    outcome.final_stage = pause_check_stage
                    outcome.final_notification = _notify_send(
                        cfg,
                        "fix-my-claw: 已发送 PAUSE 并完成复检，系统恢复健康，跳过 /stop、/new 与结构修复。",
                    )
                    repair_log.warning("recovered after soft pause: dir=%s", attempt_dir.resolve())
                    return _result_from_outcome(attempted=True, outcome=outcome)
    terminate_stage = outcome.add_stage(SessionTerminateStage().run(ctx))
    outcome.add_stage(SessionResetStage().run(ctx, previous_stage=terminate_stage))
    official_stage = outcome.add_stage(OfficialRepairStage().run(ctx))

    if official_stage.fixed:
        outcome.final_stage = official_stage
        outcome.final_notification = _notify_send(
            cfg,
            "fix-my-claw: 分层修复已完成，系统恢复健康，无需启用 Codex 修复。",
        )
        repair_log.warning("recovered by official steps: dir=%s", attempt_dir.resolve())
        return _result_from_outcome(attempted=True, outcome=outcome)

    if not cfg.ai.enabled:
        repair_log.info("Codex-assisted remediation disabled; leaving OpenClaw unhealthy")
        final_stage = outcome.add_stage(FinalAssessmentStage(stage_name="final_no_ai").run(ctx))
        outcome.final_stage = final_stage
        outcome.final_notification = _notify_send(
            cfg,
            "fix-my-claw: 官方修复后仍异常，且 ai.enabled=false，本轮不会发起 yes/no 与 Codex 修复，请人工介入。",
            silent=False,
        )
        return _result_from_outcome(attempted=True, outcome=outcome)

    if not store.can_attempt_ai(
        max_attempts_per_day=cfg.ai.max_attempts_per_day,
        cooldown_seconds=cfg.ai.cooldown_seconds,
    ):
        # 直接创建限流决策，不运行 stage（避免触发 GUI 标志检查）
        outcome.add_stage(StageResult(
            name="ai_decision",
            status="completed",
            payload=AiDecision.from_mapping({"asked": False, "decision": "rate_limited"}),
        ))
        final_stage = outcome.add_stage(FinalAssessmentStage(stage_name="final_rate_limited").run(ctx))
        outcome.final_stage = final_stage
        outcome.final_notification = _notify_send(
            cfg,
            "fix-my-claw: Codex 修复被限流（每日次数或冷却期），本轮跳过。",
            silent=False,
        )
        return _result_from_outcome(attempted=True, outcome=outcome)

    ai_decision_stage = outcome.add_stage(AiDecisionStage().run(ctx))
    ai_decision = _require_stage_payload(ai_decision_stage, AiDecision)
    if ai_decision.decision != "yes":
        final_stage = outcome.add_stage(FinalAssessmentStage(stage_name="final_no_approval").run(ctx))
        outcome.final_stage = final_stage
        outcome.final_notification = _notify_send(
            cfg,
            "fix-my-claw: 未收到 yes（含 no/timeout/发送失败/多次无效回复），本轮不会启用 Codex 修复。",
            silent=False,
        )
        return _result_from_outcome(attempted=True, outcome=outcome)

    backup_stage = outcome.add_stage(BackupStage().run(ctx))
    backup_artifact = _require_stage_payload(backup_stage, BackupArtifact)
    if backup_stage.status != "completed":
        outcome.final_stage = outcome.add_stage(FinalAssessmentStage(stage_name="final_backup_error").run(ctx))
        outcome.final_notification = _notify_send(
            cfg,
            f"fix-my-claw: 收到 yes，但备份失败，已停止 Codex 修复。错误：{backup_artifact.error}",
            silent=False,
        )
        return _result_from_outcome(attempted=True, outcome=outcome)

    store.mark_ai_attempt()
    ai_config_stage = outcome.add_stage(AiRepairStage(code_stage=False).run(ctx))
    if ai_config_stage.fixed:
        outcome.final_stage = ai_config_stage
        outcome.final_notification = _notify_send(
            cfg,
            "fix-my-claw: Codex 配置阶段修复成功，系统恢复健康。",
            silent=False,
        )
        repair_log.warning("recovered by Codex-assisted remediation: dir=%s", attempt_dir.resolve())
        return _result_from_outcome(attempted=True, outcome=outcome)

    if cfg.ai.allow_code_changes:
        ai_code_stage = outcome.add_stage(AiRepairStage(code_stage=True).run(ctx))
        if ai_code_stage.fixed:
            outcome.final_stage = ai_code_stage
            outcome.final_notification = _notify_send(
                cfg,
                "fix-my-claw: Codex 代码阶段修复成功，系统恢复健康。",
                silent=False,
            )
            repair_log.warning("recovered by code-stage remediation: dir=%s", attempt_dir.resolve())
            return _result_from_outcome(attempted=True, outcome=outcome)

    final_stage = outcome.add_stage(FinalAssessmentStage(stage_name="final").run(ctx))
    outcome.final_stage = final_stage
    outcome.final_notification = _notify_send(
        cfg,
        "fix-my-claw: 本轮修复结束，但系统仍异常，请人工介入排查。",
        silent=False,
    )
    repair_log.warning(
        "repair attempt finished: fixed=%s used_codex=%s dir=%s",
        outcome.fixed,
        outcome.used_ai,
        attempt_dir.resolve(),
    )
    return _result_from_outcome(attempted=True, outcome=outcome)
