"""Time helpers for consistent UTC-based day boundaries across the app."""

from __future__ import annotations

from datetime import UTC, date, datetime


def utc_today() -> date:
    """Return today's date in UTC."""
    return datetime.now(UTC).date()


def utc_today_iso() -> str:
    """Return today's UTC date as YYYY-MM-DD."""
    return utc_today().isoformat()
