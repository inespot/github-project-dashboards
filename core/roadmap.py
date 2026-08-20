"""Roadmap schedule comparison (planned span vs earned progress)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from core.progress import PrCache, prefetch_prs, progress_from_cache


def workdays_between(start: date, end: date) -> int:
    """Count weekdays in the inclusive range [start, end].

    Returns 0 if end < start.
    """
    if end < start:
        return 0
    total = 0
    current = start
    while current <= end:
        if current.weekday() < 5:
            total += 1
        current += timedelta(days=1)
    return total


def issue_completed(item: dict[str, Any]) -> bool:
    """True when the issue is done (closed completed or project Status Done)."""
    if item.get("stateReason") == "COMPLETED":
        return True
    if (item.get("project_status") or "") == "Done":
        return True
    return False


def roadmap_delta_days(
    milestone: str,
    items: dict[str, Any],
    field_values: dict[str, Any],
    start_field: str,
    end_field: str,
    today: date,
    pr_by_issue: PrCache | None = None,
    *,
    live_prs: bool = True,
) -> int | None:
    """Net planned-span delta vs roadmap + progress.

    Compares two working-day span totals (end − start, weekdays only):

    **Owed** — every issue (open or completed) whose planned end is before today:
      Σ (end − start)

    **Earned** —
      Σ (end − start) for completed issues
      + Σ (end − start) × progress for overdue open issues
        (same Status / PR weights as the Progress card)

    Open issues that are not yet due (end ≥ today) are ignored.
    Completed issues with end < today cancel out (full span in both owed and earned).
    Returns ``round(earned − owed)``. Positive = ahead, negative = behind.

    ``pr_by_issue`` / ``live_prs`` match ``weighted_progress_for_milestone``.
    """
    if not start_field or not end_field:
        return None

    owed = 0.0
    earned = 0.0
    considered = False
    overdue_open: list[tuple[dict[str, Any], float]] = []

    for issue_id, item in items.items():
        item_milestone = (item.get("milestone") or {}).get("title")
        if item_milestone != milestone:
            continue

        fv = field_values.get(issue_id) or {}
        start = _parse_date((fv.get(start_field) or {}).get("value"))
        end = _parse_date((fv.get(end_field) or {}).get("value"))
        if start is None or end is None:
            continue

        span = float(workdays_between(start, end))
        if span <= 0:
            continue

        completed = issue_completed(item)
        past_due = end < today

        if past_due:
            owed += span
            considered = True

        if completed:
            earned += span
            considered = True
            continue

        # Open but not yet due — ignore (no progress credit; not in owed)
        if not past_due:
            continue

        overdue_open.append((item, span))

    if overdue_open and pr_by_issue is None and live_prs:
        pr_by_issue = prefetch_prs([item["id"] for item, _span in overdue_open])

    for item, span in overdue_open:
        earned += span * float(progress_from_cache(item, pr_by_issue))
        considered = True

    if not considered:
        return None
    return int(round(earned - owed))


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value)[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None
