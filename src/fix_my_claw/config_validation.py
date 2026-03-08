"""Configuration validation helpers.

This module contains generic validation helpers used by config.py parsers.
All default values must come from dataclass default instances, not from this module.
"""
from __future__ import annotations

from typing import Any


def get_value(d: dict[str, Any], key: str, default: Any) -> Any:
    """Get a value from dict, returning default if value is None.

    Args:
        d: Source dictionary
        key: Key to look up
        default: Default value to return if key missing or value is None

    Returns:
        The value from dict, or default if missing/None
    """
    v = d.get(key, default)
    return default if v is None else v


def clamp_int(value: Any, min_val: int, max_val: int | None = None) -> int:
    """Clamp an integer value to a range.

    Args:
        value: Value to clamp (will be converted to int)
        min_val: Minimum allowed value
        max_val: Maximum allowed value (None for no upper bound)

    Returns:
        Integer value clamped to [min_val, max_val]
    """
    int_val = int(value)
    clamped = max(min_val, int_val)
    if max_val is not None:
        clamped = min(max_val, clamped)
    return clamped


def clamp_float(value: Any, min_val: float, max_val: float | None = None) -> float:
    """Clamp a float value to a range.

    Args:
        value: Value to clamp (will be converted to float)
        min_val: Minimum allowed value
        max_val: Maximum allowed value (None for no upper bound)

    Returns:
        Float value clamped to [min_val, max_val]
    """
    float_val = float(value)
    clamped = max(min_val, float_val)
    if max_val is not None:
        clamped = min(max_val, clamped)
    return clamped


def parse_string_list(values: Any) -> list[str]:
    """Parse a list of values into stripped strings.

    Args:
        values: Iterable of values to convert

    Returns:
        List of stripped string values
    """
    return [str(x).strip() for x in values]


def validate_section_dict(data: dict[str, Any], key: str) -> dict[str, Any]:
    """Extract and validate a section dict from config data.

    Args:
        data: Full config dictionary
        key: Section key to extract

    Returns:
        Section dictionary (empty dict if missing)

    Raises:
        TypeError: If section exists but is not a dict
    """
    raw = data.get(key, {})
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise TypeError(f"{key} must be an object")
    return dict(raw)
