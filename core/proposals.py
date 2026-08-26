"""Helpers for roadmap proposals."""

from __future__ import annotations

from datetime import date
from typing import Any

from core.roadmap import issue_completed
from core.time import utc_today


def end_date_value(fields: dict[str, Any], end_field: str) -> date | None:
    if not end_field:
        return None
    entry = fields.get(end_field) or {}
    raw = entry.get("value") if isinstance(entry, dict) else entry
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def include_in_proposal_edit(
    item: dict[str, Any],
    fields: dict[str, Any],
    end_field: str,
    today: date | None = None,
) -> bool:
    """Keep incomplete issues, or completed ones whose end date is still ahead."""
    if not issue_completed(item):
        return True
    end = end_date_value(fields, end_field)
    if end is None:
        return False
    return end >= (today or utc_today())
