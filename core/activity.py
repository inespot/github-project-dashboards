"""Issue activity within a time window, derived entirely from timeline events.

No snapshots required: milestoning and closure are exact timeline facts.
"""

from __future__ import annotations

from typing import Any


def added_to_milestone(
    milestone: str | None,
    since: str,
    items: dict[str, Any],
    timelines: dict[str, Any],
) -> list[dict[str, Any]]:
    """Issues added to `milestone` after `since` (ISO-8601 date string).

    If milestone is None or "all", returns issues added to any milestone.
    Each entry is a dict with keys: id, number, title, url, milestone, assignees, at.
    """
    results = []
    for issue_id, events in timelines.items():
        item = items.get(issue_id)
        if not item:
            continue
        for ev in events:
            if ev["kind"] != "milestoned":
                continue
            if ev["at"][:10] < since:
                continue
            if milestone and milestone != "all" and ev["to"] != milestone:
                continue
            results.append({
                "id": issue_id,
                "number": item.get("number"),
                "title": item.get("title"),
                "url": item.get("url"),
                "milestone": ev["to"],
                "assignees": list(item.get("assignees") or []),
                "at": ev["at"],
            })
    return sorted(results, key=lambda r: r["at"], reverse=True)


def completed_in_window(
    milestone: str | None,
    since: str,
    items: dict[str, Any],
    timelines: dict[str, Any],
) -> list[dict[str, Any]]:
    """Issues closed with stateReason=COMPLETED after `since`.

    Filters by milestone if given (uses the issue's current milestone from items,
    since milestone membership at close time is not directly in the ClosedEvent).
    """
    results = []
    for issue_id, events in timelines.items():
        item = items.get(issue_id)
        if not item:
            continue
        saw_completion = False
        for ev in events:
            if ev["kind"] != "closed":
                continue
            if ev["to"] != "COMPLETED":
                continue
            if ev["at"][:10] < since:
                continue
            # Milestone filter: use the item's current milestone as a proxy.
            if milestone and milestone != "all":
                item_milestone = (item.get("milestone") or {}).get("title")
                if item_milestone != milestone:
                    continue
            results.append({
                "id": issue_id,
                "number": item.get("number"),
                "title": item.get("title"),
                "url": item.get("url"),
                "milestone": (item.get("milestone") or {}).get("title"),
                "assignees": list(item.get("assignees") or []),
                "at": ev["at"],
            })
            saw_completion = True

        if saw_completion:
            continue

        # Fallback for project items where GitHub returns no issue content or
        # timeline, but the project status still records a current "Done" state.
        if item.get("project_status") != "Done":
            continue
        updated_at = item.get("updatedAt", "")
        if not updated_at or updated_at[:10] < since:
            continue
        if milestone and milestone != "all":
            item_milestone = (item.get("milestone") or {}).get("title")
            if item_milestone != milestone:
                continue
        results.append({
            "id": issue_id,
            "number": item.get("number"),
            "title": item.get("title"),
            "url": item.get("url"),
            "milestone": (item.get("milestone") or {}).get("title"),
            "assignees": list(item.get("assignees") or []),
            "at": updated_at,
        })

    return sorted(results, key=lambda r: r["at"], reverse=True)


def currently_in_progress(
    milestone: str | None,
    items: dict[str, Any],
    timelines: dict[str, Any],
) -> list[dict[str, Any]]:
    """Issues whose current project Status is In Progress.

    Each entry: id, number, title, url, milestone, assignees, at
    where `at` is the most recent Status transition into In Progress
    (from timeline events), or the item's updatedAt as a fallback.
    """
    results = []
    for issue_id, item in items.items():
        status = (item.get("project_status") or "").lower()
        if status != "in progress":
            continue

        if milestone and milestone != "all":
            item_milestone = (item.get("milestone") or {}).get("title")
            if item_milestone != milestone:
                continue

        since = _in_progress_since(timelines.get(issue_id, [])) or item.get("updatedAt") or ""
        results.append({
            "id": issue_id,
            "number": item.get("number"),
            "title": item.get("title"),
            "url": item.get("url"),
            "milestone": (item.get("milestone") or {}).get("title"),
            "assignees": list(item.get("assignees") or []),
            "at": since,
        })

    return sorted(results, key=lambda r: r["at"] or "")


def _in_progress_since(events: list[dict[str, Any]]) -> str | None:
    """Latest timestamp when Status changed to In Progress."""
    latest: str | None = None
    for ev in events:
        if ev.get("kind") != "project_v2_status_changed":
            continue
        if (ev.get("to") or "").lower() != "in progress":
            continue
        at = ev.get("at") or ""
        if at and (latest is None or at > latest):
            latest = at
    return latest


def since_date(days: int) -> str:
    """Return an ISO-8601 date string `days` ago."""
    from datetime import timedelta

    from core.time import utc_today

    return (utc_today() - timedelta(days=days)).isoformat()


WINDOW_OPTIONS = {
    "1 week": 7,
    "2 weeks": 14,
    "1 month": 30,
}
