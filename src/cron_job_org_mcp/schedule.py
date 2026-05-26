"""Cron expression ↔ cron-job.org schedule dict converter.

cron-job.org format:
    {
        "timezone": "Europe/Warsaw",
        "expiresAt": 0,
        "hours": [8],         # [-1] = wildcard
        "mdays": [-1],         # day of month
        "minutes": [0],
        "months": [-1],
        "wdays": [1]           # day of week (0=Sun, 6=Sat)
    }

Standard cron (5 fields):
    minute hour day_of_month month day_of_week
    np. "*/2 * * * *"  → co 2 min
        "0 8 * * 1"    → Monday 8:00
        "30 7 * * *"   → daily 7:30
"""

from __future__ import annotations

from typing import Any


CRON_FIELD_RANGES = {
    "minute": (0, 59),
    "hour": (0, 23),
    "day": (1, 31),
    "month": (1, 12),
    "weekday": (0, 6),  # 0=Sunday
}

_FIELD_NAMES_ORDER = ["minute", "hour", "day", "month", "weekday"]


def _expand_field(field: str, name: str) -> list[int]:
    """Expand single cron field (e.g. '*/2', '1,5', '0-10', '*') to list of ints.

    Returns [-1] for wildcard (cron-job.org convention).
    """
    field = field.strip()
    if field == "*":
        return [-1]

    low, high = CRON_FIELD_RANGES[name]

    # Step value: */N or X/N or X-Y/N
    if "/" in field:
        base, step_str = field.split("/", 1)
        step = int(step_str)
        if base == "*":
            return list(range(low, high + 1, step))
        # X-Y/N
        if "-" in base:
            start, end = map(int, base.split("-"))
            return list(range(start, end + 1, step))
        # X/N — od X w górę co N do high
        start = int(base)
        return list(range(start, high + 1, step))

    # List: 1,2,3
    if "," in field:
        result = []
        for part in field.split(","):
            result.extend(_expand_field(part, name))
        # Deduplicate + sort
        return sorted(set(result))

    # Range: X-Y
    if "-" in field:
        start, end = map(int, field.split("-"))
        return list(range(start, end + 1))

    # Single int
    return [int(field)]


def cron_to_dict(expression: str, timezone: str = "Europe/Warsaw") -> dict[str, Any]:
    """Convert standard 5-field cron expression to cron-job.org schedule dict.

    Args:
        expression: standard cron ("*/2 * * * *", "0 8 * * 1", ...)
        timezone: IANA tz name (default "Europe/Warsaw")

    Returns: dict zgodny z cron-job.org API format.

    Raises: ValueError jeśli expression invalid.
    """
    parts = expression.strip().split()
    if len(parts) != 5:
        raise ValueError(
            f"Expected 5 cron fields (minute hour day month weekday), got {len(parts)}: {expression!r}"
        )

    minute_str, hour_str, day_str, month_str, weekday_str = parts

    return {
        "timezone": timezone,
        "expiresAt": 0,
        "minutes": _expand_field(minute_str, "minute"),
        "hours": _expand_field(hour_str, "hour"),
        "mdays": _expand_field(day_str, "day"),
        "months": _expand_field(month_str, "month"),
        "wdays": _expand_field(weekday_str, "weekday"),
    }


def _compact_field(values: list[int], name: str) -> str:
    """Reverse: compact list of ints back to cron field string.

    [-1] → "*"
    [0,2,4,...,58] (step) → "*/2"
    [1,2,3,4,5] (range) → "1-5"
    [1,5,10] (list) → "1,5,10"
    [7] → "7"
    """
    if not values or values == [-1]:
        return "*"

    # Single value: no range/list needed
    if len(values) == 1:
        return str(values[0])

    low, high = CRON_FIELD_RANGES[name]
    full = list(range(low, high + 1))

    # Detect step from 0/low
    if len(values) >= 2 and values[0] == low:
        candidate_step = values[1] - values[0]
        if candidate_step >= 2:
            expected = list(range(low, high + 1, candidate_step))
            if values == expected:
                return f"*/{candidate_step}"

    # Detect contiguous range
    if values == list(range(values[0], values[-1] + 1)):
        if values == full:
            return "*"
        return f"{values[0]}-{values[-1]}"

    # Fallback: comma list
    return ",".join(str(v) for v in values)


def dict_to_cron(schedule: dict[str, Any]) -> str:
    """Convert cron-job.org schedule dict back to standard 5-field cron expression.

    Args:
        schedule: dict z cron-job.org (z minutes, hours, mdays, months, wdays)

    Returns: cron expression "M H D Mo Wd" or "?" jeśli brak danych.
    """
    if not schedule:
        return "?"
    try:
        m = _compact_field(schedule.get("minutes", [-1]), "minute")
        h = _compact_field(schedule.get("hours", [-1]), "hour")
        d = _compact_field(schedule.get("mdays", [-1]), "day")
        mo = _compact_field(schedule.get("months", [-1]), "month")
        w = _compact_field(schedule.get("wdays", [-1]), "weekday")
        return f"{m} {h} {d} {mo} {w}"
    except Exception:
        return "?"
