"""Reconstruct issue state at a point in time from timeline events.

All inputs and outputs are plain dicts, no framework dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class IssueState:
    """Issue state at a given date, as reconstructed from timeline events."""
    issue_id: str
    open: bool
    close_reason: str | None          # COMPLETED, NOT_PLANNED, or None
    milestone: str | None
    assignees: list[str]
    labels: list[str]
    parent_number: int | None
    project_status: str | None
    in_project: bool


def state_at(
    issue: dict[str, Any],
    events: list[dict[str, Any]],
    at: str,                          # ISO-8601 datetime string
) -> IssueState:
    """Fold timeline events up to `at` to produce the issue state at that date.

    `issue` is the current item dict from core.timeline (the live snapshot of the issue).
    `events` are the normalised timeline events for this issue.
    `at` is an ISO-8601 datetime string (comparison is lexicographic, which is correct
    for ISO-8601 timestamps with the same timezone offset).
    """
    # Seed from current known state when that state is guaranteed to have held
    # since at least the item's last update. This is the best available fallback
    # for project items whose GitHub `content` is null and therefore have no
    # issue timeline to reconstruct from.
    updated_at = issue.get("updatedAt", "")
    known_by_at = bool(updated_at) and updated_at <= at

    open_ = True
    close_reason: str | None = None
    milestone: str | None = None
    assignees: list[str] = []
    labels: list[str] = []
    parent_number: int | None = None
    project_status: str | None = None
    in_project = False

    if known_by_at:
        milestone = (issue.get("milestone") or {}).get("title")
        project_status = issue.get("project_status")
        assignees = list(issue.get("assignees") or [])
        labels = list(issue.get("labels") or [])
        parent_number = (issue.get("parent") or {}).get("number")

        if issue.get("state") == "CLOSED":
            closed_at = issue.get("closedAt", "")
            if closed_at and closed_at <= at:
                open_ = False
                close_reason = issue.get("stateReason")
        elif project_status == "Done" and issue.get("kind") != "issue":
            close_reason = "COMPLETED"

    for ev in sorted(events, key=lambda e: e["at"]):
        if ev["at"] > at:
            break
        kind = ev["kind"]
        to = ev["to"]
        from_ = ev["from_"]

        if kind == "milestoned":
            milestone = to
        elif kind == "demilestoned":
            if milestone == to or to is None:
                milestone = None
        elif kind == "closed":
            open_ = False
            close_reason = to
        elif kind == "reopened":
            open_ = True
            close_reason = None
        elif kind == "assigned":
            if to and to not in assignees:
                assignees.append(to)
        elif kind == "unassigned":
            assignees = [a for a in assignees if a != to]
        elif kind == "labeled":
            if to and to not in labels:
                labels.append(to)
        elif kind == "unlabeled":
            labels = [l for l in labels if l != to]
        elif kind == "parent_issue_added":
            parent_number = to
        elif kind == "parent_issue_removed":
            parent_number = None
        elif kind == "added_to_project_v2":
            in_project = True
        elif kind == "removed_from_project_v2":
            in_project = False
        elif kind == "project_v2_status_changed":
            project_status = to

    return IssueState(
        issue_id=issue["id"],
        open=open_,
        close_reason=close_reason,
        milestone=milestone,
        assignees=list(assignees),
        labels=list(labels),
        parent_number=parent_number,
        project_status=project_status,
        in_project=in_project,
    )


def is_completed(state: IssueState) -> bool:
    """An issue counts as completed when closed with reason COMPLETED."""
    return state.close_reason == "COMPLETED" or state.project_status == "Done"
