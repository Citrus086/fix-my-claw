from __future__ import annotations

import json
import logging
import os
import re
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config import AppConfig

_SECRET_PATTERNS = [
    r"\bsk-[A-Za-z0-9]{16,}\b",
]

_AI_APPROVAL_ACTIVE_NAME = "ai_approval.active.json"
_AI_APPROVAL_DECISION_NAME = "ai_approval.decision.json"


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


def _parse_json_maybe(stdout: str) -> dict | list | None:
    s = stdout.strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None


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


def _write_attempt_file(dir_: Path, name: str, content: str) -> Path:
    """Write content to a file in the attempt directory."""
    path = dir_ / name
    path.write_text(content, encoding="utf-8")
    return path


def _write_json_file(path: Path, payload: dict[str, Any]) -> Path:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _read_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    return raw


def _ai_approval_active_path(state_dir: Path) -> Path:
    return state_dir / _AI_APPROVAL_ACTIVE_NAME


def _ai_approval_decision_path(state_dir: Path) -> Path:
    return state_dir / _AI_APPROVAL_DECISION_NAME


def _create_ai_approval_request(
    state_dir: Path,
    *,
    request_id: str,
    attempt_dir: Path,
    prompt: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_dir(state_dir)
    active_path = _ai_approval_active_path(state_dir)
    decision_path = _ai_approval_decision_path(state_dir)
    active_path.unlink(missing_ok=True)
    decision_path.unlink(missing_ok=True)
    payload: dict[str, Any] = {
        "request_id": request_id,
        "attempt_dir": str(attempt_dir.resolve()),
        "prompt": prompt,
        "status": "pending",
    }
    if metadata:
        payload.update(metadata)
    _write_json_file(active_path, payload)
    return payload


def _read_ai_approval_request(state_dir: Path) -> dict[str, Any] | None:
    return _read_json_file(_ai_approval_active_path(state_dir))


def _read_ai_approval_decision(state_dir: Path) -> dict[str, Any] | None:
    return _read_json_file(_ai_approval_decision_path(state_dir))


def _clear_ai_approval_request(
    state_dir: Path,
    *,
    request_id: str | None = None,
    clear_decision: bool = False,
) -> None:
    active_path = _ai_approval_active_path(state_dir)
    if request_id is None:
        active_path.unlink(missing_ok=True)
    else:
        active = _read_json_file(active_path)
        active_request_id = str(active.get("request_id", "")).strip() if active else ""
        if not active_request_id or active_request_id == request_id:
            active_path.unlink(missing_ok=True)
    if clear_decision:
        _ai_approval_decision_path(state_dir).unlink(missing_ok=True)


def _claim_ai_approval_decision(
    state_dir: Path,
    *,
    request_id: str,
    decision: str,
    source: str,
    metadata: dict[str, Any] | None = None,
) -> tuple[bool, dict[str, Any] | None]:
    ensure_dir(state_dir)
    decision_path = _ai_approval_decision_path(state_dir)
    payload: dict[str, Any] = {
        "request_id": request_id,
        "decision": decision,
        "source": source,
    }
    if metadata:
        payload.update(metadata)
    try:
        fd = os.open(decision_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False, _read_json_file(decision_path)

    # Use try-finally to ensure fd is always closed properly
    handle = None
    try:
        handle = os.fdopen(fd, "w", encoding="utf-8")
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2))
        handle.close()
        handle = None
    except Exception:
        # Close handle if it was opened but not yet closed
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass
        # Clean up the partially written file
        decision_path.unlink(missing_ok=True)
        raise
    _clear_ai_approval_request(state_dir, request_id=request_id, clear_decision=False)
    return True, payload


def _repair_progress_path(state_dir: Path) -> Path:
    return state_dir / "repair_progress.json"


def write_repair_progress(
    state_dir: Path,
    *,
    stage: str,
    status: str,
    attempt_dir: str | None = None,
    timestamp: float | None = None,
) -> None:
    """写入当前修复进度，供 GUI 轮询"""
    ensure_dir(state_dir)
    path = _repair_progress_path(state_dir)
    payload: dict[str, Any] = {
        "stage": stage,
        "status": status,
        "timestamp": timestamp or time.time(),
    }
    if attempt_dir is not None:
        payload["attempt_dir"] = attempt_dir
    _write_json_file(path, payload)


def clear_repair_progress(state_dir: Path) -> None:
    """清理修复进度文件"""
    _repair_progress_path(state_dir).unlink(missing_ok=True)


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
