from __future__ import annotations

import errno
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .shared import ensure_dir

LOCK_INITIALIZING_GRACE_SECONDS = 2.0
MONITOR_ENABLED_DEFAULT = True


class StateLockTimeoutError(TimeoutError):
    """Raised when acquiring the state lock times out.

    This is distinct from TimeoutError raised by the wrapped function,
    making it easier to diagnose lock contention vs function timeout.
    """
    pass


def _normalize_enabled(value: Any, *, legacy_desired_state: Any = None) -> bool:
    """Normalize the enabled flag from various input formats.

    Handles both the current 'enabled' field and the legacy 'desired_state' field
    for backwards compatibility with older config files.

    Args:
        value: The current 'enabled' value (bool, str, int, or None)
        legacy_desired_state: The legacy 'desired_state' value (e.g., "stopped")

    Returns:
        True if monitoring should be enabled, False otherwise

    Logic:
        1. If 'enabled' is None but 'desired_state' exists, derive from legacy format
        2. If still None, return the default (True)
        3. If boolean, return as-is
        4. Otherwise, parse string/int: falsey values are {"0", "false", "off", "disabled", "no", "stopped"}
    """
    # Handle legacy format: desired_state="stopped" means enabled=False
    if value is None and legacy_desired_state is not None:
        value = str(legacy_desired_state).strip().lower() != "stopped"
    # Use default if still None
    if value is None:
        return MONITOR_ENABLED_DEFAULT
    # Return boolean directly
    if isinstance(value, bool):
        return value
    # Parse string/int: treat these falsey strings as False
    return str(value).strip().lower() not in {"0", "false", "off", "disabled", "no", "stopped"}


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

    def _lock_stat(self) -> os.stat_result | None:
        try:
            return self.path.stat()
        except FileNotFoundError:
            return None

    def _lock_signature(self) -> tuple[int, int] | None:
        stat_result = self._lock_stat()
        if stat_result is None:
            return None
        return (stat_result.st_dev, stat_result.st_ino)

    def _unlink_if_same_lock(self, expected_signature: tuple[int, int] | None) -> bool:
        if expected_signature is None:
            return self._lock_signature() is None
        current_signature = self._lock_signature()
        if current_signature is None:
            return True
        if current_signature != expected_signature:
            return False
        try:
            self.path.unlink()
            return True
        except FileNotFoundError:
            return True
        except Exception:
            return False

    def _try_break_stale_lock(self) -> bool:
        initial_stat = self._lock_stat()
        if initial_stat is None:
            return True
        initial_signature = (initial_stat.st_dev, initial_stat.st_ino)
        try:
            pid_text = self.path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return True
        except Exception:
            pid_text = ""

        current_stat = self._lock_stat()
        if current_stat is None:
            return True
        current_signature = (current_stat.st_dev, current_stat.st_ino)
        if current_signature != initial_signature:
            return False

        try:
            pid = int(pid_text) if pid_text else None
        except Exception:
            pid = None

        if pid is None:
            age_seconds = max(0.0, time.time() - current_stat.st_mtime)
            if age_seconds < LOCK_INITIALIZING_GRACE_SECONDS:
                return False
            return self._unlink_if_same_lock(current_signature)

        try:
            os.kill(pid, 0)
            return False
        except ProcessLookupError:
            return self._unlink_if_same_lock(current_signature)
        except PermissionError:
            return False
        except OSError as e:
            if e.errno == errno.EPERM:
                return False
            if e.errno != errno.ESRCH:
                return False
            return self._unlink_if_same_lock(current_signature)

    def release(self) -> None:
        # Always try to unlink the lock file first, even if close fails
        # This ensures we don't leave stale lock files behind
        unlink_error: Exception | None = None
        try:
            self.path.unlink(missing_ok=True)
        except Exception as e:
            unlink_error = e

        # Close the file descriptor if we have one
        if self._fd is not None:
            fd_to_close = self._fd
            self._fd = None  # Clear first to prevent double-close
            try:
                os.close(fd_to_close)
            except OSError:
                pass  # Already closed or invalid, ignore

        # Re-raise unlink error if it occurred (after cleanup)
        if unlink_error is not None:
            raise unlink_error


def _now_ts() -> int:
    return int(time.time())


def _today_ymd() -> str:
    return time.strftime("%Y-%m-%d", time.localtime())


@dataclass
class State:
    enabled: bool = MONITOR_ENABLED_DEFAULT
    last_ok_ts: int | None = None
    last_repair_ts: int | None = None
    last_ai_ts: int | None = None
    ai_attempts_day: str | None = None
    ai_attempts_count: int = 0

    def to_json(self) -> dict:
        return {
            "enabled": self.enabled,
            "last_ok_ts": self.last_ok_ts,
            "last_repair_ts": self.last_repair_ts,
            "last_ai_ts": self.last_ai_ts,
            "ai_attempts_day": self.ai_attempts_day,
            "ai_attempts_count": self.ai_attempts_count,
        }

    @staticmethod
    def from_json(d: dict) -> "State":
        s = State()
        s.enabled = _normalize_enabled(d.get("enabled"), legacy_desired_state=d.get("desired_state"))
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
            # Use custom exception to distinguish lock timeout from function timeout
            raise StateLockTimeoutError(f"timed out waiting for state lock: {self.lock_path}")
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

    def is_enabled(self) -> bool:
        return self.load().enabled

    def set_enabled(self, enabled: bool) -> State:
        normalized = _normalize_enabled(enabled)

        def _update() -> State:
            s = self._load_unlocked()
            s.enabled = normalized
            self._save_unlocked(s)
            return State.from_json(s.to_json())

        return self._with_lock(_update)
