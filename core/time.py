"""Time helpers for consistent UTC-based day boundaries across the app."""

from __future__ import annotations

from datetime import UTC, date, datetime


def utc_today() -> date:
    """Return today's date in UTC."""
    return datetime.now(UTC).date()


def utc_today_iso() -> str:
    """Return today's UTC date as YYYY-MM-DD."""
    return utc_today().isoformat()


def utc_now_iso() -> str:
    """Return the current UTC datetime as a proper ISO 8601 string: YYYY-MM-DDTHH:MM:SSZ."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_now_filename_label(prefix: str = "snapshot") -> str:
    """Return a filename-safe UTC datetime label with second precision."""
    return f"{prefix}-" + datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
