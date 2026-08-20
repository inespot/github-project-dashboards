"""PR-weighted issue progress.

Rules (take the max applicable credit):
  - Issue closed as COMPLETED              -> 1.00
  - Closing PR: merged                     -> 1.00
  - Closing PR: open, not draft            -> 0.70  (in review)
  - Closing PR: open, draft                -> 0.30
  - Project Status "In Progress"           -> 0.20
  - Otherwise (open, no progress signal)   -> 0.00

Returns a float in [0.0, 1.0].
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
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

_IN_PROGRESS_CREDIT = 0.20
_DRAFT_PR_CREDIT = 0.30
_IN_REVIEW_CREDIT = 0.70
_PR_FETCH_WORKERS = 4

# pr_by_issue maps issue_id -> (closing_prs, linked_prs)
PrCache = dict[str, tuple[list[dict[str, Any]], list[dict[str, Any]]]]


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

    credit = _project_status_credit(issue)

    for pr in closing_prs:
        credit = max(credit, _pr_credit(pr))

    return credit


def progress_from_cache(issue: dict[str, Any], pr_by_issue: PrCache | None) -> float:
    """Score an issue using a PR cache.

    ``pr_by_issue is None`` → Status-only (no network).
    Otherwise use cached PRs for the issue (missing id → no PRs).
    """
    if pr_by_issue is None:
        return progress(issue, closing_prs=[], linked_prs=[])
    closing, linked = pr_by_issue.get(issue["id"], ([], []))
    return progress(issue, closing_prs=closing, linked_prs=linked)


def open_issue_ids_needing_prs(items: dict[str, Any]) -> list[str]:
    """Issue node ids that would trigger a live PR fetch in ``progress()``."""
    ids: list[str] = []
    for issue_id, item in items.items():
        if item.get("kind", "issue") != "issue":
            continue
        if item.get("state") != "OPEN" or item.get("stateReason") == "COMPLETED":
            continue
        ids.append(issue_id)
    return ids


def prefetch_prs(issue_ids: list[str]) -> PrCache:
    """Fetch closing/linked PRs for many issues concurrently."""
    if not issue_ids:
        return {}
    if len(issue_ids) == 1:
        iid = issue_ids[0]
        try:
            return {iid: _fetch_prs(iid)}
        except Exception:
            return {iid: ([], [])}

    results: PrCache = {}
    workers = min(_PR_FETCH_WORKERS, len(issue_ids))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_fetch_prs, iid): iid for iid in issue_ids}
        for fut in as_completed(futures):
            iid = futures[fut]
            try:
                results[iid] = fut.result()
            except Exception:
                results[iid] = ([], [])
    return results


def _pr_credit(pr: dict[str, Any]) -> float:
    if pr.get("merged") or pr.get("state") == "MERGED":
        return 1.0
    if pr.get("state") == "CLOSED":
        return 0.0
    if pr.get("isDraft"):
        return _DRAFT_PR_CREDIT
    return _IN_REVIEW_CREDIT


def _project_status_credit(issue: dict[str, Any]) -> float:
    status = (issue.get("project_status") or "").lower()
    if status == "done":
        return 1.0
    if status == "in progress":
        return _IN_PROGRESS_CREDIT
    if status == "blocked":
        return _IN_PROGRESS_CREDIT
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
    pr_by_issue: PrCache | None = None,
    *,
    live_prs: bool = True,
) -> dict[str, Any]:
    """Compute weighted progress totals, broken down by parent task.

    ``pr_by_issue`` — pre-fetched PRs (preferred).
    ``live_prs=False`` — never hit the network; Status-only when cache missing.
    ``live_prs=True`` and no cache — prefetch open issues in parallel, then score.

    Returns:
      {
        "total_estimate": float,
        "done": float,
        "percent": float,
        "by_parent": [{parent, total_estimate, done, percent, issues: [...]}, ...]
      }
    """
    if pr_by_issue is None and live_prs:
        needed = [
            iid
            for iid in open_issue_ids_needing_prs(items)
            if _issue_in_milestone(items[iid], milestone)
            and _has_estimate(iid, estimate_field, live_field_values)
        ]
        pr_by_issue = prefetch_prs(needed)

    parents: dict[str | None, dict[str, Any]] = {}
    total_estimate = 0.0
    done = 0.0

    for issue_id, item in items.items():
        if not _issue_in_milestone(item, milestone):
            continue

        estimate = _estimate_value(issue_id, estimate_field, live_field_values)
        if estimate == 0.0:
            continue  # unestimated issues don't contribute

        p = progress_from_cache(item, pr_by_issue)
        total_estimate += estimate
        done += estimate * p

        parent = item.get("parent") or {}
        parent_num = parent.get("number")
        parent_title = parent.get("title")
        key = parent_num

        if key not in parents:
            parents[key] = {
                "parent_number": parent_num,
                "parent_title": parent_title or "(no parent)",
                "parent_url": _parent_issue_url(parent_num, item.get("url")),
                "total_estimate": 0.0,
                "done": 0.0,
                "issues": [],
            }
        elif not parents[key].get("parent_url"):
            parents[key]["parent_url"] = _parent_issue_url(parent_num, item.get("url"))

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


def _issue_in_milestone(item: dict[str, Any], milestone: str | None) -> bool:
    if not milestone or milestone == "all":
        return True
    return (item.get("milestone") or {}).get("title") == milestone


def _has_estimate(
    issue_id: str,
    estimate_field: str,
    live_field_values: dict[str, Any],
) -> bool:
    return _estimate_value(issue_id, estimate_field, live_field_values) > 0.0


def _estimate_value(
    issue_id: str,
    estimate_field: str,
    live_field_values: dict[str, Any],
) -> float:
    fv_entry = (live_field_values.get(issue_id) or {}).get(estimate_field)
    if fv_entry and fv_entry.get("value") is not None:
        return float(fv_entry["value"])
    return 0.0


def _parent_issue_url(parent_number: int | None, child_url: str | None) -> str:
    """Derive a parent issue URL from a child issue URL in the same repo."""
    if not parent_number or not child_url:
        return ""
    marker = "/issues/"
    if marker not in child_url:
        return ""
    base, _, _rest = child_url.partition(marker)
    return f"{base}{marker}{parent_number}"
