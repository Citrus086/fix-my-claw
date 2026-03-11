from __future__ import annotations

from typing import Any

API_VERSION = "1.0"


def with_api_version(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of a JSON payload with the protocol version."""
    return {"api_version": API_VERSION, **payload}


def build_status_payload(
    *,
    enabled: bool,
    config_path: str,
    config_exists: bool,
    state_path: str,
    last_ok_ts: int | None,
    last_repair_ts: int | None,
    last_ai_ts: int | None,
    ai_attempts_day: str | None,
    ai_attempts_count: int,
) -> dict[str, Any]:
    return with_api_version({
        "enabled": enabled,
        "config_path": config_path,
        "config_exists": config_exists,
        "state_path": state_path,
        "last_ok_ts": last_ok_ts,
        "last_repair_ts": last_repair_ts,
        "last_ai_ts": last_ai_ts,
        "ai_attempts_day": ai_attempts_day,
        "ai_attempts_count": ai_attempts_count,
    })


def build_check_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return with_api_version(payload)


def build_repair_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return with_api_version(payload)


def build_config_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return with_api_version(payload)


def build_service_status_payload(
    *,
    installed: bool,
    running: bool,
    label: str,
    plist_path: str,
    domain: str,
    program_path: str | None = None,
    config_path: str | None = None,
    expected_program_path: str | None = None,
    expected_config_path: str | None = None,
    drifted: bool = False,
) -> dict[str, Any]:
    return with_api_version({
        "installed": installed,
        "running": running,
        "label": label,
        "plist_path": plist_path,
        "domain": domain,
        "program_path": program_path,
        "config_path": config_path,
        "expected_program_path": expected_program_path,
        "expected_config_path": expected_config_path,
        "drifted": drifted,
    })


def build_service_reconcile_payload(
    *,
    action: str,
    reasons: list[str],
    service: dict[str, Any],
) -> dict[str, Any]:
    return with_api_version({
        "action": action,
        "reasons": reasons,
        "service": service,
    })
