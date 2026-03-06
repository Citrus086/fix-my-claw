from __future__ import annotations

import argparse
import difflib
import errno
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from pathlib import Path
from string import Template
from typing import Any

try:
    import tomllib  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

DEFAULT_CONFIG_PATH = "~/.fix-my-claw/config.toml"

DEFAULT_CONFIG_TOML = """\
[monitor]
interval_seconds = 60
probe_timeout_seconds = 15
repair_cooldown_seconds = 300
state_dir = "~/.fix-my-claw"
log_file = "~/.fix-my-claw/fix-my-claw.log"
log_level = "INFO"

[openclaw]
command = "openclaw"
state_dir = "~/.openclaw"
workspace_dir = "~/.openclaw/workspace"
health_args = ["gateway", "health", "--json"]
status_args = ["gateway", "status", "--json"]
logs_args = ["logs", "--tail", "200"]

[repair]
enabled = true
session_control_enabled = true
session_active_minutes = 30
session_agents = ["macs-orchestrator", "macs-builder", "macs-architect", "macs-research"]
terminate_message = "/stop"
new_message = "/new"
session_command_timeout_seconds = 120
session_stage_wait_seconds = 1
official_steps = [
  ["openclaw", "doctor", "--repair"],
  ["openclaw", "gateway", "restart"],
]
step_timeout_seconds = 600
post_step_wait_seconds = 2

[notify]
channel = "discord"
account = "orchestrator"
target = "channel:1479011917367476347"
silent = true
send_timeout_seconds = 20
read_timeout_seconds = 20
ask_enable_ai = true
ask_timeout_seconds = 300
poll_interval_seconds = 5
read_limit = 20
# If target is channel:..., reply should mention notify account (e.g. "@fix-my-claw yes").
# Only strict replies are accepted: 是/否/yes/no. Invalid replies are re-asked and capped at 3 attempts.
operator_user_ids = []

[anomaly_guard]
enabled = true
window_lines = 200
probe_timeout_seconds = 15
keywords_stop = ["stop", "halt", "abort", "cancel", "terminate", "停止", "立刻停止", "强制停止", "终止", "停止指令"]
keywords_repeat = ["repeat", "repeating", "loop", "ping-pong", "重复", "死循环", "不断", "一直在重复", "重复汇报"]
max_repeat_same_signature = 3
min_ping_pong_turns = 4
min_signature_chars = 16
auto_dispatch_check = true
dispatch_window_lines = 20
keywords_dispatch = ["dispatch", "handoff", "delegate", "assign", "开始实施", "开始执行", "派给", "转交"]
min_post_dispatch_unexpected_turns = 2
similarity_enabled = true
similarity_threshold = 0.82
similarity_min_chars = 12
max_similar_repeat = 4

[ai]
enabled = false
provider = "codex"
command = "codex"
args = [
  "exec",
  "-s", "workspace-write",
  "-c", "approval_policy=\\"never\\"",
  "--skip-git-repo-check",
  "-C", "$workspace_dir",
  "--add-dir", "$openclaw_state_dir",
  "--add-dir", "$monitor_state_dir",
]
model = "gpt-5.2"
timeout_seconds = 1800
max_attempts_per_day = 2
cooldown_seconds = 3600
allow_code_changes = false
args_code = [
  "exec",
  "-s", "danger-full-access",
  "-c", "approval_policy=\\"never\\"",
  "--skip-git-repo-check",
  "-C", "$workspace_dir",
]
"""

ROLE_ALIASES: dict[str, tuple[str, ...]] = {
    "user": ("user", "用户", "human"),
    "orchestrator": ("orchestrator", "调度", "协调"),
    "builder": ("builder", "实施", "执行器", "构建"),
    "architect": ("architect", "架构"),
    "research": ("research", "researcher", "研究", "调研"),
}

AGENT_ROLES = frozenset({"orchestrator", "builder", "architect", "research"})


def _expand_path(value: str) -> str:
    return os.path.expanduser(os.path.expandvars(value))


def _as_path(value: str) -> Path:
    return Path(_expand_path(value)).resolve()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def truncate_for_log(s: str, limit: int = 8000) -> str:
    if len(s) <= limit:
        return s
    return s[: limit - 20] + f"\n...[truncated {len(s) - limit} chars]"


_SECRET_PATTERNS = [
    r"\bsk-[A-Za-z0-9]{16,}\b",
]

LOCK_INITIALIZING_GRACE_SECONDS = 2.0


def redact_text(text: str) -> str:
    out = text
    out = re.sub(
        r'(?i)\b(api[_-]?key|token|secret|password)\b(\s*[:=]\s*)([^\s"\'`]+)',
        r"\1\2***",
        out,
    )
    out = re.sub(r"(?i)\b(Bearer)\s+([A-Za-z0-9._\\-]+)", r"\1 ***", out)
    for pat in _SECRET_PATTERNS:
        out = re.sub(pat, "sk-***", out)
    return out


class SecureRotatingFileHandler(RotatingFileHandler):
    def _open(self):  # pragma: no cover - exercised indirectly via setup_logging
        def _opener(path: str, flags: int) -> int:
            return os.open(path, flags, 0o600)

        return open(  # noqa: PTH123
            self.baseFilename,
            self.mode,
            encoding=self.encoding,
            errors=self.errors,
            opener=_opener,
        )


def setup_logging(cfg: "AppConfig") -> None:
    ensure_dir(cfg.monitor.state_dir)
    ensure_dir(cfg.monitor.log_file.parent)

    level = getattr(logging, cfg.monitor.log_level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    fmt = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = SecureRotatingFileHandler(
        cfg.monitor.log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    try:
        os.chmod(cfg.monitor.log_file, 0o600)
    except OSError:
        pass
    file_handler.setLevel(level)
    file_handler.setFormatter(fmt)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(level)
    stream_handler.setFormatter(fmt)

    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(stream_handler)


@dataclass(frozen=True)
class MonitorConfig:
    interval_seconds: int = 60
    probe_timeout_seconds: int = 15
    repair_cooldown_seconds: int = 300
    state_dir: Path = field(default_factory=lambda: _as_path("~/.fix-my-claw"))
    log_file: Path = field(default_factory=lambda: _as_path("~/.fix-my-claw/fix-my-claw.log"))
    log_level: str = "INFO"


@dataclass(frozen=True)
class OpenClawConfig:
    command: str = "openclaw"
    state_dir: Path = field(default_factory=lambda: _as_path("~/.openclaw"))
    workspace_dir: Path = field(default_factory=lambda: _as_path("~/.openclaw/workspace"))
    health_args: list[str] = field(default_factory=lambda: ["gateway", "health", "--json"])
    status_args: list[str] = field(default_factory=lambda: ["gateway", "status", "--json"])
    logs_args: list[str] = field(default_factory=lambda: ["logs", "--tail", "200"])


@dataclass(frozen=True)
class RepairConfig:
    enabled: bool = True
    session_control_enabled: bool = True
    session_active_minutes: int = 30
    session_agents: list[str] = field(
        default_factory=lambda: [
            "macs-orchestrator",
            "macs-builder",
            "macs-architect",
            "macs-research",
        ]
    )
    terminate_message: str = "/stop"
    new_message: str = "/new"
    session_command_timeout_seconds: int = 120
    session_stage_wait_seconds: int = 1
    official_steps: list[list[str]] = field(
        default_factory=lambda: [
            ["openclaw", "doctor", "--repair"],
            ["openclaw", "gateway", "restart"],
        ]
    )
    step_timeout_seconds: int = 600
    post_step_wait_seconds: int = 2


@dataclass(frozen=True)
class AnomalyGuardConfig:
    enabled: bool = True
    window_lines: int = 200
    probe_timeout_seconds: int = 15
    keywords_stop: list[str] = field(
        default_factory=lambda: [
            "stop",
            "halt",
            "abort",
            "cancel",
            "terminate",
            "停止",
            "立刻停止",
            "强制停止",
            "终止",
            "停止指令",
        ]
    )
    keywords_repeat: list[str] = field(
        default_factory=lambda: [
            "repeat",
            "repeating",
            "loop",
            "ping-pong",
            "重复",
            "死循环",
            "不断",
            "一直在重复",
            "重复汇报",
        ]
    )
    max_repeat_same_signature: int = 3
    min_ping_pong_turns: int = 4
    min_signature_chars: int = 16
    auto_dispatch_check: bool = True
    dispatch_window_lines: int = 20
    keywords_dispatch: list[str] = field(
        default_factory=lambda: [
            "dispatch",
            "handoff",
            "delegate",
            "assign",
            "开始实施",
            "开始执行",
            "派给",
            "转交",
        ]
    )
    min_post_dispatch_unexpected_turns: int = 2
    # Legacy compatibility key; no longer used for new dispatch analysis.
    keywords_architect_active: list[str] = field(
        default_factory=lambda: [
            "architect",
            "still output",
            "continue output",
            "还在输出",
            "继续发内容",
            "连续输出",
        ]
    )
    # Similarity detection for single-agent loops
    similarity_enabled: bool = True
    similarity_threshold: float = 0.82
    similarity_min_chars: int = 12
    max_similar_repeat: int = 4


@dataclass(frozen=True)
class NotifyConfig:
    channel: str = "discord"
    account: str = "orchestrator"
    target: str = "channel:1479011917367476347"
    silent: bool = True
    send_timeout_seconds: int = 20
    read_timeout_seconds: int = 20
    ask_enable_ai: bool = True
    ask_timeout_seconds: int = 300
    poll_interval_seconds: int = 5
    read_limit: int = 20
    operator_user_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AiConfig:
    enabled: bool = False
    provider: str = "codex"  # optional/for humans; command+args are what we actually execute
    command: str = "codex"
    # args supports placeholders: $workspace_dir, $openclaw_state_dir, $monitor_state_dir
    args: list[str] = field(
        default_factory=lambda: [
            "exec",
            "-s",
            "workspace-write",
            "-c",
            'approval_policy="never"',
            "--skip-git-repo-check",
            "-C",
            "$workspace_dir",
            "--add-dir",
            "$openclaw_state_dir",
            "--add-dir",
            "$monitor_state_dir",
        ]
    )
    model: str | None = None
    timeout_seconds: int = 1800
    max_attempts_per_day: int = 2
    cooldown_seconds: int = 3600
    allow_code_changes: bool = False
    args_code: list[str] = field(
        default_factory=lambda: [
            "exec",
            "-s",
            "danger-full-access",
            "-c",
            'approval_policy="never"',
            "--skip-git-repo-check",
            "-C",
            "$workspace_dir",
        ]
    )


@dataclass(frozen=True)
class AppConfig:
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    openclaw: OpenClawConfig = field(default_factory=OpenClawConfig)
    repair: RepairConfig = field(default_factory=RepairConfig)
    anomaly_guard: AnomalyGuardConfig = field(default_factory=AnomalyGuardConfig)
    notify: NotifyConfig = field(default_factory=NotifyConfig)
    ai: AiConfig = field(default_factory=AiConfig)


def _get(d: dict[str, Any], key: str, default: Any) -> Any:
    v = d.get(key, default)
    return default if v is None else v


def _parse_monitor(raw: dict[str, Any]) -> MonitorConfig:
    return MonitorConfig(
        interval_seconds=max(1, int(_get(raw, "interval_seconds", 60))),
        probe_timeout_seconds=max(1, int(_get(raw, "probe_timeout_seconds", 15))),
        repair_cooldown_seconds=max(0, int(_get(raw, "repair_cooldown_seconds", 300))),
        state_dir=_as_path(str(_get(raw, "state_dir", "~/.fix-my-claw"))),
        log_file=_as_path(str(_get(raw, "log_file", "~/.fix-my-claw/fix-my-claw.log"))),
        log_level=str(_get(raw, "log_level", "INFO")),
    )


def _parse_openclaw(raw: dict[str, Any]) -> OpenClawConfig:
    return OpenClawConfig(
        command=str(_get(raw, "command", "openclaw")),
        state_dir=_as_path(str(_get(raw, "state_dir", "~/.openclaw"))),
        workspace_dir=_as_path(str(_get(raw, "workspace_dir", "~/.openclaw/workspace"))),
        health_args=list(_get(raw, "health_args", ["gateway", "health", "--json"])),
        status_args=list(_get(raw, "status_args", ["gateway", "status", "--json"])),
        logs_args=list(_get(raw, "logs_args", ["logs", "--tail", "200"])),
    )


def _parse_repair(raw: dict[str, Any]) -> RepairConfig:
    raw_official_steps = _get(raw, "official_steps", RepairConfig().official_steps)
    official_steps = [list(x) for x in raw_official_steps if x]
    return RepairConfig(
        enabled=bool(_get(raw, "enabled", True)),
        session_control_enabled=bool(_get(raw, "session_control_enabled", True)),
        session_active_minutes=max(1, int(_get(raw, "session_active_minutes", 30))),
        session_agents=[str(x).strip() for x in _get(raw, "session_agents", RepairConfig().session_agents)],
        terminate_message=str(_get(raw, "terminate_message", "/stop")),
        new_message=str(_get(raw, "new_message", "/new")),
        session_command_timeout_seconds=max(10, int(_get(raw, "session_command_timeout_seconds", 120))),
        session_stage_wait_seconds=max(0, int(_get(raw, "session_stage_wait_seconds", 1))),
        official_steps=official_steps,
        step_timeout_seconds=max(1, int(_get(raw, "step_timeout_seconds", 600))),
        post_step_wait_seconds=max(0, int(_get(raw, "post_step_wait_seconds", 2))),
    )


def _parse_anomaly_guard(raw: dict[str, Any]) -> AnomalyGuardConfig:
    cfg = AnomalyGuardConfig()
    return AnomalyGuardConfig(
        enabled=bool(_get(raw, "enabled", cfg.enabled)),
        window_lines=max(20, int(_get(raw, "window_lines", cfg.window_lines))),
        probe_timeout_seconds=max(3, int(_get(raw, "probe_timeout_seconds", cfg.probe_timeout_seconds))),
        keywords_stop=[str(x).strip() for x in _get(raw, "keywords_stop", cfg.keywords_stop)],
        keywords_repeat=[str(x).strip() for x in _get(raw, "keywords_repeat", cfg.keywords_repeat)],
        max_repeat_same_signature=max(
            2, int(_get(raw, "max_repeat_same_signature", cfg.max_repeat_same_signature))
        ),
        min_ping_pong_turns=max(2, int(_get(raw, "min_ping_pong_turns", cfg.min_ping_pong_turns))),
        min_signature_chars=max(8, int(_get(raw, "min_signature_chars", cfg.min_signature_chars))),
        auto_dispatch_check=bool(_get(raw, "auto_dispatch_check", cfg.auto_dispatch_check)),
        dispatch_window_lines=max(1, int(_get(raw, "dispatch_window_lines", cfg.dispatch_window_lines))),
        keywords_dispatch=[str(x).strip() for x in _get(raw, "keywords_dispatch", cfg.keywords_dispatch)],
        min_post_dispatch_unexpected_turns=max(
            2,
            int(
                _get(
                    raw,
                    "min_post_dispatch_unexpected_turns",
                    cfg.min_post_dispatch_unexpected_turns,
                )
            ),
        ),
        keywords_architect_active=[
            str(x).strip() for x in _get(raw, "keywords_architect_active", cfg.keywords_architect_active)
        ],
        similarity_enabled=bool(_get(raw, "similarity_enabled", cfg.similarity_enabled)),
        similarity_threshold=max(
            0.5, min(1.0, float(_get(raw, "similarity_threshold", cfg.similarity_threshold)))
        ),
        similarity_min_chars=max(6, int(_get(raw, "similarity_min_chars", cfg.similarity_min_chars))),
        max_similar_repeat=max(2, int(_get(raw, "max_similar_repeat", cfg.max_similar_repeat))),
    )


def _parse_notify(raw: dict[str, Any]) -> NotifyConfig:
    cfg = NotifyConfig()
    send_timeout_seconds = max(5, int(_get(raw, "send_timeout_seconds", cfg.send_timeout_seconds)))
    read_timeout_seconds = max(
        5,
        int(_get(raw, "read_timeout_seconds", send_timeout_seconds)),
    )
    return NotifyConfig(
        channel=str(_get(raw, "channel", cfg.channel)),
        account=str(_get(raw, "account", cfg.account)),
        target=str(_get(raw, "target", cfg.target)),
        silent=bool(_get(raw, "silent", cfg.silent)),
        send_timeout_seconds=send_timeout_seconds,
        read_timeout_seconds=read_timeout_seconds,
        ask_enable_ai=bool(_get(raw, "ask_enable_ai", cfg.ask_enable_ai)),
        ask_timeout_seconds=max(15, int(_get(raw, "ask_timeout_seconds", cfg.ask_timeout_seconds))),
        poll_interval_seconds=max(1, int(_get(raw, "poll_interval_seconds", cfg.poll_interval_seconds))),
        read_limit=max(1, int(_get(raw, "read_limit", cfg.read_limit))),
        operator_user_ids=[str(x).strip() for x in _get(raw, "operator_user_ids", cfg.operator_user_ids)],
    )


def _parse_ai(raw: dict[str, Any]) -> AiConfig:
    cfg = AiConfig()
    return AiConfig(
        enabled=bool(_get(raw, "enabled", cfg.enabled)),
        provider=str(_get(raw, "provider", cfg.provider)),
        command=str(_get(raw, "command", cfg.command)),
        args=list(_get(raw, "args", cfg.args)),
        model=_get(raw, "model", cfg.model),
        timeout_seconds=max(1, int(_get(raw, "timeout_seconds", cfg.timeout_seconds))),
        max_attempts_per_day=max(0, int(_get(raw, "max_attempts_per_day", cfg.max_attempts_per_day))),
        cooldown_seconds=max(0, int(_get(raw, "cooldown_seconds", cfg.cooldown_seconds))),
        allow_code_changes=bool(_get(raw, "allow_code_changes", cfg.allow_code_changes)),
        args_code=list(_get(raw, "args_code", cfg.args_code)),
    )


def load_config(path: str) -> AppConfig:
    p = _as_path(path)
    if not p.exists():
        raise FileNotFoundError(f"config not found: {p}")
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    monitor = _parse_monitor(dict(data.get("monitor", {})))
    openclaw = _parse_openclaw(dict(data.get("openclaw", {})))
    repair = _parse_repair(dict(data.get("repair", {})))
    anomaly_raw = data.get("anomaly_guard", data.get("loop_guard", {}))
    anomaly_guard = _parse_anomaly_guard(dict(anomaly_raw))
    notify = _parse_notify(dict(data.get("notify", {})))
    ai = _parse_ai(dict(data.get("ai", {})))
    return AppConfig(
        monitor=monitor,
        openclaw=openclaw,
        repair=repair,
        anomaly_guard=anomaly_guard,
        notify=notify,
        ai=ai,
    )


def write_default_config(path: str, *, overwrite: bool = False) -> Path:
    p = _as_path(path)
    if p.exists() and not overwrite:
        return p
    ensure_dir(p.parent)
    p.write_text(DEFAULT_CONFIG_TOML, encoding="utf-8")
    return p


@dataclass(frozen=True)
class CmdResult:
    argv: list[str]
    cwd: Path | None
    exit_code: int
    duration_ms: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


def run_cmd(
    argv: list[str],
    *,
    timeout_seconds: int,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    stdin_text: str | None = None,
) -> CmdResult:
    started = time.monotonic()
    try:
        cp = subprocess.run(
            argv,
            input=stdin_text,
            text=True,
            capture_output=True,
            cwd=str(cwd) if cwd is not None else None,
            env=env,
            timeout=timeout_seconds,
        )
        code = cp.returncode
        out = cp.stdout or ""
        err = cp.stderr or ""
    except FileNotFoundError as e:
        code = 127
        out = ""
        err = f"[fix-my-claw] command not found: {argv[0]} ({e})"
    except subprocess.TimeoutExpired as e:
        code = 124
        out = (e.stdout or "") if isinstance(e.stdout, str) else ""
        err = (e.stderr or "") if isinstance(e.stderr, str) else ""
        err = (err + "\n" if err else "") + f"[fix-my-claw] timeout after {timeout_seconds}s"
    except OSError as e:
        code = 1
        out = ""
        err = f"[fix-my-claw] os error running {argv!r}: {e}"
    duration_ms = int((time.monotonic() - started) * 1000)
    return CmdResult(
        argv=list(argv),
        cwd=cwd,
        exit_code=code,
        duration_ms=duration_ms,
        stdout=out,
        stderr=err,
    )


@dataclass
class FileLock:
    path: Path
    _fd: int | None = None

    def acquire(self, *, timeout_seconds: int = 0) -> bool:
        start = time.monotonic()
        while True:
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.write(fd, str(os.getpid()).encode("utf-8"))
                self._fd = fd
                return True
            except FileExistsError:
                if self._try_break_stale_lock():
                    continue
                if timeout_seconds <= 0:
                    return False
                if (time.monotonic() - start) >= timeout_seconds:
                    return False
                time.sleep(0.2)

    def _try_break_stale_lock(self) -> bool:
        try:
            pid_text = self.path.read_text(encoding="utf-8").strip()
            pid = int(pid_text) if pid_text else None
        except Exception:
            pid = None

        if pid is None:
            try:
                age_seconds = max(0.0, time.time() - self.path.stat().st_mtime)
            except FileNotFoundError:
                return True
            except Exception:
                return False
            if age_seconds < LOCK_INITIALIZING_GRACE_SECONDS:
                return False
            try:
                self.path.unlink(missing_ok=True)
                return True
            except Exception:
                return False

        try:
            os.kill(pid, 0)
            return False
        except ProcessLookupError:
            try:
                self.path.unlink(missing_ok=True)
                return True
            except Exception:
                return False
        except PermissionError:
            return False
        except OSError as e:
            if e.errno == errno.EPERM:
                return False
            if e.errno != errno.ESRCH:
                return False
            try:
                self.path.unlink(missing_ok=True)
                return True
            except Exception:
                return False

    def release(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            finally:
                self._fd = None
        try:
            self.path.unlink(missing_ok=True)
        except Exception:
            pass


def _now_ts() -> int:
    return int(time.time())


def _today_ymd() -> str:
    return time.strftime("%Y-%m-%d", time.localtime())


@dataclass
class State:
    last_ok_ts: int | None = None
    last_repair_ts: int | None = None
    last_ai_ts: int | None = None
    ai_attempts_day: str | None = None
    ai_attempts_count: int = 0

    def to_json(self) -> dict:
        return {
            "last_ok_ts": self.last_ok_ts,
            "last_repair_ts": self.last_repair_ts,
            "last_ai_ts": self.last_ai_ts,
            "ai_attempts_day": self.ai_attempts_day,
            "ai_attempts_count": self.ai_attempts_count,
        }

    @staticmethod
    def from_json(d: dict) -> "State":
        s = State()
        s.last_ok_ts = d.get("last_ok_ts")
        s.last_repair_ts = d.get("last_repair_ts")
        s.last_ai_ts = d.get("last_ai_ts")
        s.ai_attempts_day = d.get("ai_attempts_day")
        s.ai_attempts_count = int(d.get("ai_attempts_count", 0))
        return s


class StateStore:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.path = base_dir / "state.json"
        self.lock_path = base_dir / "state.lock"
        ensure_dir(base_dir)

    def _load_unlocked(self) -> State:
        if not self.path.exists():
            return State()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return State.from_json(data if isinstance(data, dict) else {})
        except Exception:
            return State()

    def load(self) -> State:
        return self._load_unlocked()

    def _save_unlocked(self, state: State) -> None:
        ensure_dir(self.path.parent)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def _with_lock(self, fn: Any, *, timeout_seconds: int = 5) -> Any:
        lock = FileLock(self.lock_path)
        if not lock.acquire(timeout_seconds=timeout_seconds):
            raise TimeoutError(f"timed out waiting for state lock: {self.lock_path}")
        try:
            return fn()
        finally:
            lock.release()

    def save(self, state: State) -> None:
        self._with_lock(lambda: self._save_unlocked(state))

    def mark_ok(self) -> None:
        def _update() -> None:
            s = self._load_unlocked()
            s.last_ok_ts = _now_ts()
            self._save_unlocked(s)

        self._with_lock(_update)

    def can_attempt_repair(self, cooldown_seconds: int, *, force: bool) -> bool:
        if force:
            return True
        s = self.load()
        if s.last_repair_ts is None:
            return True
        return (_now_ts() - s.last_repair_ts) >= cooldown_seconds

    def mark_repair_attempt(self) -> None:
        def _update() -> None:
            s = self._load_unlocked()
            s.last_repair_ts = _now_ts()
            self._save_unlocked(s)

        self._with_lock(_update)

    def can_attempt_ai(self, *, max_attempts_per_day: int, cooldown_seconds: int) -> bool:
        def _check() -> bool:
            s = self._load_unlocked()
            today = _today_ymd()
            if s.ai_attempts_day != today:
                s.ai_attempts_day = today
                s.ai_attempts_count = 0
                s.last_ai_ts = None
                self._save_unlocked(s)

            if s.ai_attempts_count >= max_attempts_per_day:
                return False
            if s.last_ai_ts is not None and (_now_ts() - s.last_ai_ts) < cooldown_seconds:
                return False
            return True

        return bool(self._with_lock(_check))

    def mark_ai_attempt(self) -> None:
        def _update() -> None:
            s = self._load_unlocked()
            today = _today_ymd()
            if s.ai_attempts_day != today:
                s.ai_attempts_day = today
                s.ai_attempts_count = 0
            s.ai_attempts_count += 1
            s.last_ai_ts = _now_ts()
            self._save_unlocked(s)

        self._with_lock(_update)


@dataclass(frozen=True)
class Probe:
    name: str
    cmd: CmdResult
    json_data: dict | list | None

    @property
    def ok(self) -> bool:
        return self.cmd.ok

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "ok": self.ok,
            "exit_code": self.cmd.exit_code,
            "duration_ms": self.cmd.duration_ms,
            "argv": self.cmd.argv,
            "stdout": self.cmd.stdout,
            "stderr": self.cmd.stderr,
            "json": self.json_data,
        }


def _parse_json_maybe(stdout: str) -> dict | list | None:
    s = stdout.strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None


def probe_health(cfg: AppConfig, *, log_on_fail: bool = True) -> Probe:
    argv = [cfg.openclaw.command, *cfg.openclaw.health_args]
    cwd = cfg.openclaw.workspace_dir if cfg.openclaw.workspace_dir.exists() else None
    cmd = run_cmd(argv, timeout_seconds=cfg.monitor.probe_timeout_seconds, cwd=cwd)
    data = _parse_json_maybe(cmd.stdout)
    if log_on_fail and not cmd.ok:
        logging.getLogger("fix_my_claw.openclaw").warning(
            "health probe failed: %s", truncate_for_log(cmd.stderr or cmd.stdout)
        )
    return Probe(name="health", cmd=cmd, json_data=data)


def probe_status(cfg: AppConfig, *, log_on_fail: bool = True) -> Probe:
    argv = [cfg.openclaw.command, *cfg.openclaw.status_args]
    cwd = cfg.openclaw.workspace_dir if cfg.openclaw.workspace_dir.exists() else None
    cmd = run_cmd(argv, timeout_seconds=cfg.monitor.probe_timeout_seconds, cwd=cwd)
    data = _parse_json_maybe(cmd.stdout)
    if log_on_fail and not cmd.ok:
        logging.getLogger("fix_my_claw.openclaw").warning(
            "status probe failed: %s", truncate_for_log(cmd.stderr or cmd.stdout)
        )
    return Probe(name="status", cmd=cmd, json_data=data)


def probe_logs(cfg: AppConfig, *, timeout_seconds: int = 15) -> CmdResult:
    argv = [cfg.openclaw.command, *cfg.openclaw.logs_args]
    cwd = cfg.openclaw.workspace_dir if cfg.openclaw.workspace_dir.exists() else None
    return run_cmd(argv, timeout_seconds=timeout_seconds, cwd=cwd)


def _normalize_loop_line(line: str) -> str:
    s = line.strip().lower()
    s = re.sub(r"\b[0-9a-f]{6,}\b", "<id>", s)
    s = re.sub(r"\b\d+\b", "<n>", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _find_token_index(text: str, token: str) -> int:
    if not token:
        return -1
    if re.search(r"[a-z0-9_]", token):
        match = re.search(rf"(?<![a-z0-9_]){re.escape(token)}(?![a-z0-9_])", text)
        return match.start() if match else -1
    return text.find(token)


def _extract_speaker_role(line: str) -> str | None:
    s = line.strip().lower()
    s = re.sub(r"^\[[^\]]+\]\s*", "", s)
    s = re.sub(r"^\d{4}-\d{2}-\d{2}[ t]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?\s+", "", s)
    for role, aliases in ROLE_ALIASES.items():
        for alias in aliases:
            prefixes = (
                f"{alias}:",
                f"{alias}：",
                f"{alias} ",
                f"{alias}>",
                f"{alias}-",
                f"[{alias}]",
                f"[{alias}] ",
            )
            if s == alias or any(s.startswith(prefix) for prefix in prefixes):
                return role
    return None


def _extract_role(line: str) -> str | None:
    speaker = _extract_speaker_role(line)
    if speaker:
        return speaker
    for role, aliases in ROLE_ALIASES.items():
        if any(_find_token_index(line, alias) >= 0 for alias in aliases):
            return role
    return None


def _contains_any(text: str, tokens: list[str]) -> bool:
    return any(_find_token_index(text, t) >= 0 for t in tokens if t)


def _extract_handoff_target_role(
    line: str,
    *,
    dispatch_tokens: list[str],
    speaker_role: str,
) -> str | None:
    dispatch_hit: tuple[int, str] | None = None
    for token in dispatch_tokens:
        idx = _find_token_index(line, token)
        if idx >= 0 and (dispatch_hit is None or idx < dispatch_hit[0]):
            dispatch_hit = (idx, token)
    if dispatch_hit is None:
        return None

    tail = line[dispatch_hit[0] + len(dispatch_hit[1]) :]
    target_hit: tuple[int, str] | None = None
    for role in AGENT_ROLES:
        if role == speaker_role:
            continue
        for alias in ROLE_ALIASES.get(role, ()):
            idx = _find_token_index(tail, alias)
            if idx >= 0 and (target_hit is None or idx < target_hit[0]):
                target_hit = (idx, role)
    return target_hit[1] if target_hit else None


def _find_unexpected_post_dispatch_streak(
    lines: list[str],
    *,
    start_idx: int,
    expected_role: str,
    max_lines: int,
    min_turns: int,
) -> dict[str, Any] | None:
    streak_role: str | None = None
    streak_count = 0
    for rel_idx, raw in enumerate(lines[start_idx + 1 : start_idx + 1 + max_lines], start=1):
        speaker_role = _extract_speaker_role(raw)
        if speaker_role not in AGENT_ROLES:
            continue
        if speaker_role == expected_role:
            streak_role = None
            streak_count = 0
            continue
        if speaker_role == streak_role:
            streak_count += 1
        else:
            streak_role = speaker_role
            streak_count = 1
        if streak_count >= min_turns:
            return {
                "unexpected_role": speaker_role,
                "turns": streak_count,
                "unexpected_line_index": start_idx + rel_idx,
                "unexpected_line": raw,
            }
    return None


def _calc_similarity(a: str, b: str) -> float:
    """Calculate similarity ratio between two strings using SequenceMatcher.
    
    Returns a float between 0.0 and 1.0, where 1.0 means identical.
    """
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _find_similar_group(
    signature: str,
    groups: list[tuple[str, list[str]]],
    threshold: float,
) -> tuple[int, list[str]] | None:
    """Find an existing similar group for the given signature.
    
    Args:
        signature: The normalized signature to classify
        groups: List of (representative, signatures) tuples
        threshold: Minimum similarity to consider as match
    
    Returns:
        Tuple of (group_index, signatures_list) if found, None otherwise
    """
    for idx, (rep, sigs) in enumerate(groups):
        if _calc_similarity(signature, rep) >= threshold:
            return (idx, sigs)
    return None


def _analyze_anomaly_guard(cfg: AppConfig) -> dict:
    logs = probe_logs(cfg, timeout_seconds=cfg.anomaly_guard.probe_timeout_seconds)
    merged = logs.stdout + (("\n" + logs.stderr) if logs.stderr else "")
    lines_all = [ln for ln in merged.splitlines() if ln.strip()]
    lines = lines_all[-cfg.anomaly_guard.window_lines :]

    stop_tokens = [x.lower() for x in cfg.anomaly_guard.keywords_stop if x]
    repeat_tokens = [x.lower() for x in cfg.anomaly_guard.keywords_repeat if x]
    dispatch_tokens = [x.lower() for x in cfg.anomaly_guard.keywords_dispatch if x]

    if not logs.ok:
        return {
            "enabled": True,
            "triggered": False,
            "probe_ok": False,
            "probe_exit_code": logs.exit_code,
            "probe_error": redact_text(logs.stderr or logs.stdout),
        }

    stop_signals = 0
    stop_roles: set[str] = set()
    signatures: Counter[str] = Counter()
    ping_roles: list[str] = []
    dispatch_events: list[dict[str, Any]] = []

    # Similarity-based grouping for single-agent loop detection.
    # Keep groups per role to avoid mixing orchestrator and builder messages.
    similar_groups_by_role: dict[str, list[tuple[str, list[str]]]] = {}

    for idx, raw in enumerate(lines):
        normalized = _normalize_loop_line(raw)
        speaker_role = _extract_speaker_role(raw)
        role = speaker_role or _extract_role(normalized)
        is_stop = _contains_any(normalized, stop_tokens)
        is_repeat = _contains_any(normalized, repeat_tokens)

        if is_stop:
            stop_signals += 1
            stop_roles.add(role or "unknown")

        if len(normalized) >= cfg.anomaly_guard.min_signature_chars and role in {"orchestrator", "builder"}:
            sig_key = f"{role}|{normalized}"
            signatures[sig_key] += 1

            # Similarity grouping: group signatures that are similar but not identical
            if cfg.anomaly_guard.similarity_enabled and len(normalized) >= cfg.anomaly_guard.similarity_min_chars:
                groups = similar_groups_by_role.setdefault(role, [])
                found = _find_similar_group(
                    normalized,
                    groups,
                    cfg.anomaly_guard.similarity_threshold
                )
                if found:
                    _, sigs = found
                    sigs.append(sig_key)
                else:
                    groups.append((normalized, [sig_key]))

        if role in {"orchestrator", "builder"} and (is_stop or is_repeat):
            ping_roles.append(role)

        if (
            cfg.anomaly_guard.auto_dispatch_check
            and speaker_role in AGENT_ROLES
            and _contains_any(normalized, dispatch_tokens)
        ):
            target_role = _extract_handoff_target_role(
                normalized,
                dispatch_tokens=dispatch_tokens,
                speaker_role=speaker_role,
            )
            if target_role:
                dispatch_events.append(
                    {
                        "dispatch_line_index": idx,
                        "initiator_role": speaker_role,
                        "target_role": target_role,
                        "dispatch_line": raw,
                    }
                )

    ping_pong_turns = 0
    for i in range(1, len(ping_roles)):
        if ping_roles[i] != ping_roles[i - 1]:
            ping_pong_turns += 1

    max_repeat_same_signature = max(signatures.values(), default=0)
    top_signature = signatures.most_common(1)[0][0] if signatures else None
    
    # Calculate max similar repeats across all role-scoped groups.
    max_similar_repeats = 0
    top_similar_group: dict[str, Any] | None = None
    for role, groups in similar_groups_by_role.items():
        for rep, sigs in groups:
            if len(sigs) > max_similar_repeats:
                max_similar_repeats = len(sigs)
                top_similar_group = {
                    "role": role,
                    "representative": rep,
                    "count": len(sigs),
                }

    repeat_trigger = max_repeat_same_signature >= cfg.anomaly_guard.max_repeat_same_signature
    similar_repeat_trigger = (
        cfg.anomaly_guard.similarity_enabled
        and max_similar_repeats >= cfg.anomaly_guard.max_similar_repeat
    )
    ping_pong_trigger = ping_pong_turns >= cfg.anomaly_guard.min_ping_pong_turns

    auto_dispatch_trigger = False
    auto_dispatch_event: dict[str, Any] | None = None
    if cfg.anomaly_guard.auto_dispatch_check:
        for event in dispatch_events:
            unexpected = _find_unexpected_post_dispatch_streak(
                lines,
                start_idx=int(event["dispatch_line_index"]),
                expected_role=str(event["target_role"]),
                max_lines=cfg.anomaly_guard.dispatch_window_lines,
                min_turns=cfg.anomaly_guard.min_post_dispatch_unexpected_turns,
            )
            if unexpected is not None:
                auto_dispatch_trigger = True
                auto_dispatch_event = {**event, **unexpected}
                break

    # Allow semantic repetition to trigger on its own; requiring stop signals misses
    # practical loop cases where agents keep repeating without explicit "stop" text.
    triggered = ping_pong_trigger or auto_dispatch_trigger or repeat_trigger or similar_repeat_trigger

    return {
        "enabled": True,
        "triggered": triggered,
        "probe_ok": True,
        "metrics": {
            "lines_analyzed": len(lines),
            "stop_signals": stop_signals,
            "distinct_stop_roles": sorted(stop_roles),
            "max_repeat_same_signature": max_repeat_same_signature,
            "ping_pong_turns": ping_pong_turns,
            "top_signature": top_signature,
            "max_similar_repeats": max_similar_repeats,
            "top_similar_group": top_similar_group,
            "auto_dispatch_event": auto_dispatch_event,
        },
        "signals": {
            "repeat_trigger": repeat_trigger,
            "similar_repeat_trigger": similar_repeat_trigger,
            "ping_pong_trigger": ping_pong_trigger,
            "auto_dispatch_trigger": auto_dispatch_trigger,
        },
    }


@dataclass(frozen=True)
class CheckResult:
    healthy: bool
    health: dict
    status: dict
    anomaly_guard: dict | None = None

    def to_json(self) -> dict:
        out = {"healthy": self.healthy, "health": self.health, "status": self.status}
        if self.anomaly_guard is not None:
            out["anomaly_guard"] = self.anomaly_guard
            # Backward compatible key for older parsers.
            out["loop_guard"] = self.anomaly_guard
        return out


def run_check(cfg: AppConfig, store: StateStore) -> CheckResult:
    healthy, h, s, anomaly_guard = _evaluate_health(cfg)
    if healthy:
        store.mark_ok()
    return CheckResult(
        healthy=healthy,
        health=h.to_json(),
        status=s.to_json(),
        anomaly_guard=anomaly_guard,
    )


def _parse_agent_id_from_session_key(key: str) -> str | None:
    m = re.match(r"^agent:([^:]+):", key or "")
    if not m:
        return None
    return m.group(1)


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


def _notify_send(cfg: AppConfig, text: str, *, silent: bool | None = None) -> dict[str, Any]:
    argv = [
        cfg.openclaw.command,
        "message",
        "send",
        "--channel",
        cfg.notify.channel,
        "--account",
        cfg.notify.account,
        "--target",
        cfg.notify.target,
        "--message",
        text,
        "--json",
    ]
    use_silent = cfg.notify.silent if silent is None else silent
    if use_silent:
        argv.append("--silent")
    cwd = cfg.openclaw.workspace_dir if cfg.openclaw.workspace_dir.exists() else None
    res = run_cmd(argv, timeout_seconds=cfg.notify.send_timeout_seconds, cwd=cwd)
    parsed = _parse_json_maybe(res.stdout)
    message_id = None
    if isinstance(parsed, dict):
        payload = parsed.get("payload")
        if isinstance(payload, dict):
            result = payload.get("result")
            if isinstance(result, dict):
                message_id = result.get("messageId")
    return {
        "sent": res.ok,
        "message_id": str(message_id) if message_id else None,
        "exit_code": res.exit_code,
        "argv": res.argv,
        "stderr": redact_text(res.stderr),
        "stdout": redact_text(res.stdout),
    }


def _notify_read_messages(cfg: AppConfig, *, after_id: str | None = None) -> list[dict[str, Any]]:
    argv = [
        cfg.openclaw.command,
        "message",
        "read",
        "--channel",
        cfg.notify.channel,
        "--account",
        cfg.notify.account,
        "--target",
        cfg.notify.target,
        "--limit",
        str(cfg.notify.read_limit),
        "--json",
    ]
    if after_id:
        argv += ["--after", after_id]
    cwd = cfg.openclaw.workspace_dir if cfg.openclaw.workspace_dir.exists() else None
    res = run_cmd(argv, timeout_seconds=cfg.notify.read_timeout_seconds, cwd=cwd)
    if not res.ok:
        return []
    parsed = _parse_json_maybe(res.stdout)
    if not isinstance(parsed, dict):
        return []
    payload = parsed.get("payload")
    if not isinstance(payload, dict):
        return []
    messages = payload.get("messages", [])
    if not isinstance(messages, list):
        return []
    out: list[dict[str, Any]] = []
    for item in messages:
        if isinstance(item, dict):
            out.append(item)
    return out


def _normalize_name_key(value: str) -> str:
    return re.sub(r"[\s_\-]+", "", value.strip().lower())


def _max_message_id(current: str | None, candidate: str | None) -> str | None:
    ids = [x for x in (current, candidate) if x]
    if not ids:
        return None
    return max(ids, key=lambda x: (1, int(x)) if x.isdigit() else (0, x))


def _normalize_ai_reply_token(text: str) -> str:
    # Remove leading Discord mentions and trailing punctuation, then strict-match.
    t = re.sub(r"<@!?\d+>", " ", text.strip().lower())
    t = re.sub(r"[ \t\r\n]+", " ", t).strip()
    t = re.sub(r"[。！？!?.,，]+$", "", t).strip()
    return t


def _message_mentions_notify_account(
    cfg: AppConfig, message: dict[str, Any], *, required_mention_id: str | None
) -> bool:
    mentions = message.get("mentions")
    mention_list = mentions if isinstance(mentions, list) else []

    account_key = _normalize_name_key(cfg.notify.account)
    for mention in mention_list:
        if not isinstance(mention, dict):
            continue
        mention_id = str(mention.get("id", "")).strip()
        if required_mention_id and mention_id and mention_id == required_mention_id:
            return True
        for key in ("username", "global_name", "name", "display_name", "nick"):
            raw = mention.get(key)
            if isinstance(raw, str) and raw.strip() and _normalize_name_key(raw) == account_key:
                return True

    if required_mention_id:
        content = str(message.get("content", ""))
        if re.search(rf"<@!?{re.escape(required_mention_id)}>", content):
            return True
    return False


def _resolve_sent_message_author_id(cfg: AppConfig, message_id: str | None) -> str | None:
    if not message_id:
        return None
    target = str(message_id).strip()
    if not target:
        return None
    for _ in range(3):
        for msg in _notify_read_messages(cfg):
            if str(msg.get("id", "")).strip() != target:
                continue
            author = msg.get("author")
            if isinstance(author, dict):
                author_id = str(author.get("id", "")).strip()
                if author_id:
                    return author_id
        time.sleep(0.5)
    return None


def _is_ai_reply_candidate(
    cfg: AppConfig, message: dict[str, Any], *, required_mention_id: str | None = None
) -> bool:
    content = str(message.get("content", "")).strip()
    if not content:
        return False
    author = message.get("author", {})
    author_id = str(author.get("id", "")) if isinstance(author, dict) else ""
    is_bot = bool(author.get("bot")) if isinstance(author, dict) else False
    if is_bot:
        return False
    if cfg.notify.operator_user_ids and author_id not in set(cfg.notify.operator_user_ids):
        return False
    if cfg.notify.target.strip().lower().startswith("channel:"):
        if not _message_mentions_notify_account(cfg, message, required_mention_id=required_mention_id):
            return False
    return True


def _extract_ai_decision(
    cfg: AppConfig, message: dict[str, Any], *, required_mention_id: str | None = None
) -> str | None:
    if not _is_ai_reply_candidate(cfg, message, required_mention_id=required_mention_id):
        return None
    content = _normalize_ai_reply_token(str(message.get("content", "")))
    if content in {"yes", "是"}:
        return "yes"
    if content in {"no", "否"}:
        return "no"
    return None


def _ask_user_enable_ai(cfg: AppConfig, attempt_dir: Path) -> dict[str, Any]:
    if not cfg.notify.ask_enable_ai:
        return {"asked": False, "decision": "skip"}
    max_invalid_replies = 3
    prompt = (
        "fix-my-claw: 已执行命令级终止 + /new + 官方结构修复，当前仍异常。"
        f"是否启用 Codex 修复？请 @{cfg.notify.account} 回复 是/否（Please answer with yes/no）。"
        "（回复 yes/是 将先备份整个 ~/.openclaw 到其上级目录）"
    )
    sent = _notify_send(cfg, prompt, silent=False)
    message_id = sent.get("message_id")
    required_mention_id = _resolve_sent_message_author_id(cfg, str(message_id) if message_id else None)
    _write_attempt_file(attempt_dir, "notify.ask.json", json.dumps(sent, ensure_ascii=False, indent=2))
    _write_attempt_file(
        attempt_dir,
        "notify.ask.mention.json",
        json.dumps(
            {
                "required_mention_id": required_mention_id,
                "notify_account": cfg.notify.account,
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    if not sent.get("sent"):
        return {"asked": True, "decision": "error", "send": sent}

    deadline = time.monotonic() + cfg.notify.ask_timeout_seconds
    last_seen = str(message_id) if message_id else None
    invalid_replies = 0
    while time.monotonic() < deadline:
        messages = _notify_read_messages(cfg, after_id=last_seen)
        next_last_seen = last_seen
        for msg in messages:
            msg_id = str(msg.get("id", "")).strip()
            if msg_id:
                next_last_seen = _max_message_id(next_last_seen, msg_id)
            decision = _extract_ai_decision(cfg, msg, required_mention_id=required_mention_id)
            if decision:
                out = {
                    "asked": True,
                    "decision": decision,
                    "reply_message_id": str(msg.get("id", "")),
                    "reply_author_id": str((msg.get("author") or {}).get("id", "")),
                }
                _write_attempt_file(
                    attempt_dir, "notify.ask.decision.json", json.dumps(out, ensure_ascii=False, indent=2)
                )
                return out
            if _is_ai_reply_candidate(cfg, msg, required_mention_id=required_mention_id):
                invalid_replies += 1
                if invalid_replies >= max_invalid_replies:
                    out = {
                        "asked": True,
                        "decision": "invalid_limit",
                        "invalid_replies": invalid_replies,
                        "reply_message_id": str(msg.get("id", "")),
                        "reply_author_id": str((msg.get("author") or {}).get("id", "")),
                    }
                    _write_attempt_file(
                        attempt_dir, "notify.ask.decision.json", json.dumps(out, ensure_ascii=False, indent=2)
                    )
                    return out
                remaining = max_invalid_replies - invalid_replies
                _notify_send(
                    cfg,
                    f"fix-my-claw: 未识别到有效回复。请仅回复 是/否（Please answer with yes/no）。剩余 {remaining} 次。",
                    silent=False,
                )
        last_seen = next_last_seen
        time.sleep(cfg.notify.poll_interval_seconds)

    out = {"asked": True, "decision": "timeout"}
    _write_attempt_file(attempt_dir, "notify.ask.decision.json", json.dumps(out, ensure_ascii=False, indent=2))
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
        _write_attempt_file(attempt_dir, f"{stage_name}.{idx}.stdout.txt", redact_text(res.stdout))
        _write_attempt_file(attempt_dir, f"{stage_name}.{idx}.stderr.txt", redact_text(res.stderr))
        results.append(
            {
                "agent": agent_id,
                "session_id": session_id,
                "argv": res.argv,
                "exit_code": res.exit_code,
                "duration_ms": res.duration_ms,
                "stdout_path": str((attempt_dir / f"{stage_name}.{idx}.stdout.txt").resolve()),
                "stderr_path": str((attempt_dir / f"{stage_name}.{idx}.stderr.txt").resolve()),
            }
        )
    return results


@dataclass(frozen=True)
class RepairResult:
    attempted: bool
    fixed: bool
    used_ai: bool
    details: dict

    def to_json(self) -> dict:
        return {
            "attempted": self.attempted,
            "fixed": self.fixed,
            "used_ai": self.used_ai,
            "details": self.details,
        }


def _attempt_dir(cfg: AppConfig) -> Path:
    base = cfg.monitor.state_dir / "attempts"
    ensure_dir(base)
    ts = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    return Path(tempfile.mkdtemp(prefix=f"{ts}-", dir=str(base)))


def _write_attempt_file(dir_: Path, name: str, content: str) -> Path:
    p = dir_ / name
    p.write_text(content, encoding="utf-8")
    return p


def _collect_context(cfg: AppConfig, attempt_dir: Path, *, stage_name: str) -> dict:
    health = probe_health(cfg, log_on_fail=False)
    status = probe_status(cfg, log_on_fail=False)
    logs = probe_logs(cfg, timeout_seconds=cfg.monitor.probe_timeout_seconds)

    prefix = f"context.{stage_name}"
    health_stdout = f"{prefix}.health.stdout.txt"
    health_stderr = f"{prefix}.health.stderr.txt"
    status_stdout = f"{prefix}.status.stdout.txt"
    status_stderr = f"{prefix}.status.stderr.txt"
    logs_file = f"{prefix}.openclaw.logs.txt"

    _write_attempt_file(attempt_dir, health_stdout, redact_text(health.cmd.stdout))
    _write_attempt_file(attempt_dir, health_stderr, redact_text(health.cmd.stderr))
    _write_attempt_file(attempt_dir, status_stdout, redact_text(status.cmd.stdout))
    _write_attempt_file(attempt_dir, status_stderr, redact_text(status.cmd.stderr))
    _write_attempt_file(attempt_dir, logs_file, redact_text(logs.stdout + ("\n" + logs.stderr if logs.stderr else "")))

    return {
        "health": health.to_json(),
        "status": status.to_json(),
        "logs": {
            "ok": logs.ok,
            "exit_code": logs.exit_code,
            "duration_ms": logs.duration_ms,
            "argv": logs.argv,
            "stdout_path": str((attempt_dir / logs_file).resolve()),
        },
        "attempt_dir": str(attempt_dir.resolve()),
    }

def _evaluate_health(
    cfg: AppConfig,
    *,
    log_probe_failures: bool = False,
) -> tuple[bool, Probe, Probe, dict | None]:
    health = probe_health(cfg, log_on_fail=log_probe_failures)
    status = probe_status(cfg, log_on_fail=log_probe_failures)
    healthy = health.ok and status.ok
    anomaly_guard: dict | None = None
    if healthy and cfg.anomaly_guard.enabled:
        anomaly_guard = _analyze_anomaly_guard(cfg)
        if anomaly_guard.get("triggered"):
            healthy = False
    return healthy, health, status, anomaly_guard


def _is_effectively_healthy(cfg: AppConfig) -> tuple[bool, dict | None]:
    healthy, health, status, anomaly_guard = _evaluate_health(cfg, log_probe_failures=False)
    if not (health.ok and status.ok):
        return (
            False,
            {
                "probe_ok": False,
                "health": health.to_json(),
                "status": status.to_json(),
            },
        )
    return healthy, anomaly_guard


def _run_official_steps(cfg: AppConfig, attempt_dir: Path, *, break_on_healthy: bool = True) -> list[dict]:
    repair_log = logging.getLogger("fix_my_claw.repair")
    results: list[dict] = []
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
        _write_attempt_file(attempt_dir, f"official.{idx}.stdout.txt", redact_text(res.stdout))
        _write_attempt_file(attempt_dir, f"official.{idx}.stderr.txt", redact_text(res.stderr))
        results.append(
            {
                "argv": res.argv,
                "exit_code": res.exit_code,
                "duration_ms": res.duration_ms,
                "stdout_path": str((attempt_dir / f"official.{idx}.stdout.txt").resolve()),
                "stderr_path": str((attempt_dir / f"official.{idx}.stderr.txt").resolve()),
            }
        )
        time.sleep(cfg.repair.post_step_wait_seconds)
        if break_on_healthy and _is_effectively_healthy(cfg)[0]:
            repair_log.warning("OpenClaw is healthy after official step %d/%d", idx, total)
            break
    return results


def _load_prompt_text(name: str) -> str:
    from importlib.resources import files

    return (files("fix_my_claw.prompts") / name).read_text(encoding="utf-8")


def _build_ai_cmd(cfg: AppConfig, *, code_stage: bool) -> list[str]:
    vars = {
        "workspace_dir": str(cfg.openclaw.workspace_dir),
        "openclaw_state_dir": str(cfg.openclaw.state_dir),
        "monitor_state_dir": str(cfg.monitor.state_dir),
    }
    args = cfg.ai.args_code if code_stage else cfg.ai.args
    rendered = [Template(x).safe_substitute(vars) for x in args]
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


def attempt_repair(
    cfg: AppConfig,
    store: StateStore,
    *,
    force: bool,
    reason: str | None = None,
) -> RepairResult:
    repair_log = logging.getLogger("fix_my_claw.repair")
    initially_healthy, initial_health_info = _is_effectively_healthy(cfg)
    if initially_healthy:
        repair_log.info("repair skipped: already healthy")
        details: dict[str, object] = {"already_healthy": True}
        if initial_health_info is not None:
            details["health_info"] = initial_health_info
        return RepairResult(attempted=False, fixed=True, used_ai=False, details=details)

    if not cfg.repair.enabled:
        repair_log.warning("repair skipped: disabled by config")
        return RepairResult(attempted=False, fixed=False, used_ai=False, details={"repair_disabled": True})

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
        return RepairResult(attempted=False, fixed=False, used_ai=False, details=details)

    attempt_dir = _attempt_dir(cfg)
    store.mark_repair_attempt()
    details: dict = {"attempt_dir": str(attempt_dir.resolve())}
    if reason:
        details["reason"] = reason
    repair_log.warning("starting repair attempt: dir=%s", attempt_dir.resolve())
    details["notify_start"] = _notify_send(
        cfg,
        "fix-my-claw: 检测到异常，开始执行分层修复（命令终止 -> /new -> 官方结构修复）。",
        silent=False,
    )

    details["context_before"] = _collect_context(cfg, attempt_dir, stage_name="before")
    details["terminate_stage"] = _run_session_command_stage(
        cfg,
        attempt_dir,
        stage_name="terminate",
        message_text=cfg.repair.terminate_message,
    )
    if details["terminate_stage"] and cfg.repair.session_stage_wait_seconds > 0:
        time.sleep(cfg.repair.session_stage_wait_seconds)
    details["new_stage"] = _run_session_command_stage(
        cfg,
        attempt_dir,
        stage_name="new",
        message_text=cfg.repair.new_message,
    )
    details["official"] = _run_official_steps(
        cfg,
        attempt_dir,
        break_on_healthy=True,
    )
    details["context_after_official"] = _collect_context(cfg, attempt_dir, stage_name="after_official")

    healthy_after_official, anomaly_guard_after_official = _is_effectively_healthy(cfg)
    if anomaly_guard_after_official is not None:
        details["anomaly_guard_after_official"] = anomaly_guard_after_official
    if healthy_after_official:
        details["notify_final"] = _notify_send(
            cfg,
            "fix-my-claw: 分层修复已完成，系统恢复健康，无需启用 Codex 修复。",
        )
        repair_log.warning("recovered by official steps: dir=%s", attempt_dir.resolve())
        return RepairResult(attempted=True, fixed=True, used_ai=False, details=details)

    if not cfg.ai.enabled:
        repair_log.info("Codex-assisted remediation disabled; leaving OpenClaw unhealthy")
        details["notify_final"] = _notify_send(
            cfg,
            "fix-my-claw: 官方修复后仍异常，且 ai.enabled=false，本轮不会发起 yes/no 与 Codex 修复，请人工介入。",
            silent=False,
        )
        fixed, anomaly_guard_final = _is_effectively_healthy(cfg)
        if anomaly_guard_final is not None:
            details["anomaly_guard_final"] = anomaly_guard_final
        return RepairResult(attempted=True, fixed=fixed, used_ai=False, details=details)

    if not store.can_attempt_ai(
        max_attempts_per_day=cfg.ai.max_attempts_per_day,
        cooldown_seconds=cfg.ai.cooldown_seconds,
    ):
        details["ai_decision"] = {"asked": False, "decision": "rate_limited"}
        details["notify_final"] = _notify_send(
            cfg,
            "fix-my-claw: Codex 修复被限流（每日次数或冷却期），本轮跳过。",
            silent=False,
        )
        fixed, anomaly_guard_final = _is_effectively_healthy(cfg)
        if anomaly_guard_final is not None:
            details["anomaly_guard_final"] = anomaly_guard_final
        return RepairResult(attempted=True, fixed=fixed, used_ai=False, details=details)

    ai_decision = _ask_user_enable_ai(cfg, attempt_dir)
    details["ai_decision"] = ai_decision
    if ai_decision.get("decision") != "yes":
        details["notify_final"] = _notify_send(
            cfg,
            "fix-my-claw: 未收到 yes（含 no/timeout/发送失败/多次无效回复），本轮不会启用 Codex 修复。",
            silent=False,
        )
        fixed, anomaly_guard_final = _is_effectively_healthy(cfg)
        if anomaly_guard_final is not None:
            details["anomaly_guard_final"] = anomaly_guard_final
        return RepairResult(attempted=True, fixed=fixed, used_ai=False, details=details)

    try:
        backup_info = _backup_openclaw_state(cfg, attempt_dir)
        details["backup_before_ai"] = backup_info
    except Exception as e:
        details["backup_before_ai_error"] = str(e)
        details["notify_final"] = _notify_send(
            cfg,
            f"fix-my-claw: 收到 yes，但备份失败，已停止 Codex 修复。错误：{e}",
            silent=False,
        )
        fixed, anomaly_guard_final = _is_effectively_healthy(cfg)
        if anomaly_guard_final is not None:
            details["anomaly_guard_final"] = anomaly_guard_final
        return RepairResult(attempted=True, fixed=fixed, used_ai=False, details=details)

    details["notify_backup"] = _notify_send(
        cfg,
        f"fix-my-claw: 已完成备份，开始 Codex 修复。备份文件：{backup_info.get('archive')}",
        silent=False,
    )

    store.mark_ai_attempt()
    used_ai = True
    details["ai_stage"] = "config"
    details["ai_result_config"] = _run_ai_repair(cfg, attempt_dir, code_stage=False).__dict__
    details["context_after_ai_config"] = _collect_context(cfg, attempt_dir, stage_name="after_ai_config")
    healthy_after_ai_config, anomaly_guard_after_ai_config = _is_effectively_healthy(cfg)
    if anomaly_guard_after_ai_config is not None:
        details["anomaly_guard_after_ai_config"] = anomaly_guard_after_ai_config
    if healthy_after_ai_config:
        details["notify_final"] = _notify_send(
            cfg,
            "fix-my-claw: Codex 配置阶段修复成功，系统恢复健康。",
            silent=False,
        )
        repair_log.warning("recovered by Codex-assisted remediation: dir=%s", attempt_dir.resolve())
        return RepairResult(attempted=True, fixed=True, used_ai=True, details=details)

    if cfg.ai.allow_code_changes:
        details["ai_stage"] = "code"
        details["ai_result_code"] = _run_ai_repair(cfg, attempt_dir, code_stage=True).__dict__
        details["context_after_ai_code"] = _collect_context(cfg, attempt_dir, stage_name="after_ai_code")
        healthy_after_ai_code, anomaly_guard_after_ai_code = _is_effectively_healthy(cfg)
        if anomaly_guard_after_ai_code is not None:
            details["anomaly_guard_after_ai_code"] = anomaly_guard_after_ai_code
        if healthy_after_ai_code:
            details["notify_final"] = _notify_send(
                cfg,
                "fix-my-claw: Codex 代码阶段修复成功，系统恢复健康。",
                silent=False,
            )
            repair_log.warning("recovered by code-stage remediation: dir=%s", attempt_dir.resolve())
            return RepairResult(attempted=True, fixed=True, used_ai=True, details=details)

    fixed, anomaly_guard_final = _is_effectively_healthy(cfg)
    if anomaly_guard_final is not None:
        details["anomaly_guard_final"] = anomaly_guard_final
    details["notify_final"] = _notify_send(
        cfg,
        "fix-my-claw: 本轮修复结束，但系统仍异常，请人工介入排查。",
        silent=False,
    )
    repair_log.warning(
        "repair attempt finished: fixed=%s used_codex=%s dir=%s",
        fixed,
        used_ai,
        attempt_dir.resolve(),
    )
    return RepairResult(attempted=True, fixed=fixed, used_ai=used_ai, details=details)


def monitor_loop(cfg: AppConfig, store: StateStore) -> None:
    wd_log = logging.getLogger("fix_my_claw.watchdog")
    wd_log.info("starting monitor loop: interval=%ss", cfg.monitor.interval_seconds)
    while True:
        try:
            result = run_check(cfg, store)
            if not result.healthy:
                wd_log.warning(
                    "unhealthy: health_exit=%s status_exit=%s; attempting repair",
                    result.health.get("exit_code"),
                    result.status.get("exit_code"),
                )
                anomaly_triggered = bool(result.anomaly_guard and result.anomaly_guard.get("triggered"))
                if anomaly_triggered:
                    wd_log.warning(
                        "anomaly guard triggered: signals=%s",
                        result.anomaly_guard.get("signals"),
                    )
                rr = attempt_repair(
                    cfg,
                    store,
                    force=False,
                    reason="anomaly_guard" if anomaly_triggered else None,
                )
                if rr.attempted:
                    wd_log.warning(
                        "repair finished: fixed=%s used_codex=%s dir=%s",
                        rr.fixed,
                        rr.used_ai,
                        rr.details.get("attempt_dir"),
                    )
                elif rr.details.get("cooldown"):
                    remaining = rr.details.get("cooldown_remaining_seconds")
                    wd_log.info("repair skipped: cooldown (%ss remaining)", remaining if remaining is not None else "?")
                else:
                    wd_log.info("repair skipped: %s", rr.details)
        except Exception as e:
            wd_log.exception("monitor loop error: %s", e)
        time.sleep(cfg.monitor.interval_seconds)


def _add_config_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to TOML config file (default: {DEFAULT_CONFIG_PATH}).",
    )


def _load_or_init_config(path: str, *, init_if_missing: bool) -> AppConfig:
    p = _as_path(path)
    if not p.exists():
        if init_if_missing:
            write_default_config(str(p), overwrite=False)
        else:
            raise FileNotFoundError(f"config not found: {p} (run `fix-my-claw init` or `fix-my-claw up`)")
    return load_config(str(p))


def cmd_init(args: argparse.Namespace) -> int:
    p = write_default_config(args.config, overwrite=args.force)
    print(str(p))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    cfg = _load_or_init_config(args.config, init_if_missing=False)
    setup_logging(cfg)
    store = StateStore(cfg.monitor.state_dir)
    result = run_check(cfg, store)
    if args.json:
        print(json.dumps(result.to_json(), ensure_ascii=False))
    return 0 if result.healthy else 1


def cmd_repair(args: argparse.Namespace) -> int:
    cfg = _load_or_init_config(args.config, init_if_missing=False)
    setup_logging(cfg)
    lock = FileLock(cfg.monitor.state_dir / "fix-my-claw.lock")
    if not lock.acquire(timeout_seconds=0):
        print("another fix-my-claw instance is running", file=sys.stderr)
        return 2
    store = StateStore(cfg.monitor.state_dir)
    try:
        result = attempt_repair(cfg, store, force=args.force, reason=None)
    finally:
        lock.release()
    if args.json:
        print(json.dumps(result.to_json(), ensure_ascii=False))
    return 0 if result.fixed else 1


def cmd_monitor(args: argparse.Namespace) -> int:
    cfg = _load_or_init_config(args.config, init_if_missing=False)
    setup_logging(cfg)
    lock = FileLock(cfg.monitor.state_dir / "fix-my-claw.lock")
    if not lock.acquire(timeout_seconds=0):
        print("another fix-my-claw instance is running", file=sys.stderr)
        return 2
    store = StateStore(cfg.monitor.state_dir)
    try:
        monitor_loop(cfg, store)
    finally:
        lock.release()
    return 0


def cmd_up(args: argparse.Namespace) -> int:
    cfg = _load_or_init_config(args.config, init_if_missing=True)
    setup_logging(cfg)
    lock = FileLock(cfg.monitor.state_dir / "fix-my-claw.lock")
    if not lock.acquire(timeout_seconds=0):
        print("another fix-my-claw instance is running", file=sys.stderr)
        return 2
    store = StateStore(cfg.monitor.state_dir)
    try:
        monitor_loop(cfg, store)
    finally:
        lock.release()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fix-my-claw")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_up = sub.add_parser("up", help="One-command start: init default config (if missing) then monitor.")
    _add_config_arg(p_up)
    p_up.set_defaults(func=cmd_up)

    p_init = sub.add_parser("init", help="Write default config (prints config path).")
    _add_config_arg(p_init)
    p_init.add_argument("--force", action="store_true", help="Overwrite config if it already exists.")
    p_init.set_defaults(func=cmd_init)

    p_check = sub.add_parser("check", help="Probe OpenClaw health/status once.")
    _add_config_arg(p_check)
    p_check.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    p_check.set_defaults(func=cmd_check)

    p_repair = sub.add_parser("repair", help="Run official repair (and optional AI repair) once if unhealthy.")
    _add_config_arg(p_repair)
    p_repair.add_argument("--force", action="store_true", help="Ignore cooldown and attempt repair.")
    p_repair.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    p_repair.set_defaults(func=cmd_repair)

    p_mon = sub.add_parser("monitor", help="Run 24/7 monitor loop (requires config to exist).")
    _add_config_arg(p_mon)
    p_mon.set_defaults(func=cmd_monitor)

    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    code = args.func(args)
    raise SystemExit(code)
