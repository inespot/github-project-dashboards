"""PR-weighted issue progress.

Rules:
  - Issue closed as COMPLETED              -> 1.00
  - Closing PR: merged                     -> 1.00
  - Closing PR: open, not draft            -> 0.70  (in review)
  - Closing PR: open, draft                -> 0.40
  - Non-closing PR linked to the issue     -> 0.20
  - No linked PR, issue open               -> 0.00

Returns a float in [0.0, 1.0].
"""

from __future__ import annotations

from typing import Any

from core import github

_CLOSING_PRS_QUERY = """
query ClosingPRs($id: ID!, $after: String) {
  rateLimit { remaining resetAt }
  node(id: $id) {
    ... on Issue {
      closedByPullRequestsReferences(first: 20, after: $after, includeClosedPrs: true) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          isDraft
          state
          merged
        }
      }
      timelineItems(first: 50, itemTypes: [CROSS_REFERENCED_EVENT, CONNECTED_EVENT]) {
        nodes {
          __typename
          ... on CrossReferencedEvent {
            source {
              __typename
              ... on PullRequest {
                id
                isDraft
                state
                merged
              }
            }
          }
        }
      }
    }
  }
}
"""


def progress(
    issue: dict[str, Any],
    closing_prs: list[dict[str, Any]] | None = None,
    linked_prs: list[dict[str, Any]] | None = None,
) -> float:
    """Return a progress float in [0.0, 1.0].

    If `closing_prs` and `linked_prs` are provided (e.g. from a pre-fetched
    batch), no API calls are made. Otherwise the issue is queried live.
    """
    kind = issue.get("kind", "issue")
    if kind != "issue":
        return _project_status_credit(issue)

    if not issue["state"] == "OPEN" or issue.get("stateReason") == "COMPLETED":
        return 1.0

    if closing_prs is None or linked_prs is None:
        try:
            closing_prs, linked_prs = _fetch_prs(issue["id"])
        except Exception:
            return _project_status_credit(issue)

    closing_ids = {pr["id"] for pr in closing_prs}

    credit = 0.0

    for pr in closing_prs:
        credit = max(credit, _pr_credit(pr))

    for pr in linked_prs:
        if pr.get("id") not in closing_ids:
            credit = max(credit, 0.20)

    return credit


def _pr_credit(pr: dict[str, Any]) -> float:
    if pr.get("merged") or pr.get("state") == "MERGED":
        return 1.0
    if pr.get("state") == "CLOSED":
        return 0.0
    if pr.get("isDraft"):
        return 0.40
    return 0.70


def _project_status_credit(issue: dict[str, Any]) -> float:
    status = (issue.get("project_status") or "").lower()
    if status == "done":
        return 1.0
    if status == "in progress":
        return 0.70
    if status == "blocked":
        return 0.20
    return 0.0


def _fetch_prs(issue_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    closing_prs = []
    linked_prs = []

    for pr_node in github.paginate(
        _CLOSING_PRS_QUERY,
        {"id": issue_id},
        ["node", "closedByPullRequestsReferences"],
    ):
        if pr_node:
            closing_prs.append(pr_node)

    data = github.query(_CLOSING_PRS_QUERY, {"id": issue_id, "after": None})
    issue_node = data.get("node", {})
    timeline = issue_node.get("timelineItems", {}).get("nodes", [])
    for ev in timeline:
        if ev and ev.get("__typename") == "CrossReferencedEvent":
            src = ev.get("source") or {}
            if src.get("__typename") == "PullRequest":
                linked_prs.append(src)

    return closing_prs, linked_prs


def weighted_progress_for_milestone(
    milestone: str | None,
    items: dict[str, Any],
    estimate_field: str,
    live_field_values: dict[str, Any],
) -> dict[str, Any]:
    """Compute weighted progress totals, broken down by parent task.

    Returns:
      {
        "total_estimate": float,
        "done": float,
        "percent": float,
        "by_parent": [{parent, total_estimate, done, percent, issues: [...]}, ...]
      }
    """
    parents: dict[str | None, dict[str, Any]] = {}
    total_estimate = 0.0
    done = 0.0

    for issue_id, item in items.items():
        # Milestone filter
        if milestone and milestone != "all":
            item_milestone = (item.get("milestone") or {}).get("title")
            if item_milestone != milestone:
                continue

        # Estimate
        fv_entry = (live_field_values.get(issue_id) or {}).get(estimate_field)
        estimate = float(fv_entry["value"]) if fv_entry and fv_entry.get("value") is not None else 0.0
        if estimate == 0.0:
            continue  # unestimated issues don't contribute

        p = progress(item)
        total_estimate += estimate
        done += estimate * p

        parent_num = (item.get("parent") or {}).get("number")
        parent_title = (item.get("parent") or {}).get("title")
        key = parent_num

        if key not in parents:
            parents[key] = {
                "parent_number": parent_num,
                "parent_title": parent_title or "(no parent)",
                "total_estimate": 0.0,
                "done": 0.0,
                "issues": [],
            }

        parents[key]["total_estimate"] += estimate
        parents[key]["done"] += estimate * p
        parents[key]["issues"].append({
            "number": item["number"],
            "title": item["title"],
            "url": item["url"],
            "estimate": estimate,
            "progress": p,
        })

    by_parent = []
    for v in sorted(parents.values(), key=lambda x: x["total_estimate"], reverse=True):
        tot = v["total_estimate"]
        wd = v["done"]
        v["percent"] = round(wd / tot * 100, 1) if tot else 0.0
        by_parent.append(v)

    return {
        "total_estimate": total_estimate,
        "done": done,
        "percent": round(done / total_estimate * 100, 1) if total_estimate else 0.0,
        "by_parent": by_parent,
    }
