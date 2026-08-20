"""Burn-up series derivation.

Produces a daily series of:
  date, scope, completed, in_progress, todo, remaining, added, confidence

where:
  - completed + in_progress + todo == scope (stacked status buckets)
  - remaining == scope - completed (legacy gap metric)
  - confidence is "exact" if all estimates for that date are exact,
    "partial" if some are assumed, or "assumed" if all are assumed

Designed to be used with Polars DataFrames but returns plain dicts so
tests have no Polars dependency.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from core import fields as fields_mod, reconstruct


def burnup(
    project_id: str,
    milestone: str | None,          # None or "all" means all milestones
    estimate_field: str,
    items: dict[str, Any],
    timelines: dict[str, Any],
    live_field_values: dict[str, Any],
    start: date,
    end: date,
    snapshots: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return a list of daily row dicts for the burn-up chart.

    Each row: date, scope, completed, in_progress, todo, remaining, added, confidence
    """
    rows: list[dict[str, Any]] = []
    prev_scope = 0.0
    current_date = start

    while current_date <= end:
        date_str = current_date.isoformat()

        scope = 0.0
        completed = 0.0
        in_progress = 0.0
        confidences = []

        for issue_id, item in items.items():
            created_at = item.get("createdAt", "")
            if created_at and created_at[:10] > date_str:
                continue

            state = reconstruct.state_at(item, timelines.get(issue_id, []), date_str + "T23:59:59Z")

            # Milestone filter
            if milestone and milestone != "all":
                if state.milestone != milestone:
                    continue

            est, conf = fields_mod.value_at(
                project_id,
                issue_id,
                estimate_field,
                date_str,
                live_field_values,
                snapshots,
            )
            if est is None:
                continue

            est_float = float(est)
            scope += est_float
            confidences.append(conf)

            if reconstruct.is_completed(state):
                completed += est_float
            elif reconstruct.is_in_progress(state):
                in_progress += est_float

        todo = scope - completed - in_progress

        if not confidences:
            confidence = "assumed"
        elif all(c == "exact" for c in confidences):
            confidence = "exact"
        elif any(c == "exact" for c in confidences):
            confidence = "partial"
        else:
            confidence = "assumed"

        added = max(0.0, scope - prev_scope)
        rows.append({
            "date": date_str,
            "scope": scope,
            "completed": completed,
            "in_progress": in_progress,
            "todo": todo,
            "remaining": scope - completed,
            "added": added,
            "confidence": confidence,
        })
        prev_scope = scope
        current_date += timedelta(days=1)

    return rows
