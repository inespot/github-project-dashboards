"""Open PRs currently in review for project issues."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from core import github, people

_PR_FIELDS = """
          id
          number
          title
          url
          isDraft
          state
          merged
          reviewDecision
          author { login }
          reviewRequests(first: 20) {
            nodes {
              requestedReviewer {
                __typename
                ... on User { login }
                ... on Team { name }
              }
            }
          }
          reviews(first: 50) {
            nodes {
              state
              author { login }
            }
          }
"""

_ISSUE_OPEN_PRS_QUERY = f"""
query IssueOpenPrs($id: ID!) {{
  rateLimit {{ remaining resetAt }}
  node(id: $id) {{
    ... on Issue {{
      closedByPullRequestsReferences(first: 20, includeClosedPrs: true) {{
        nodes {{
{_PR_FIELDS}
        }}
      }}
      timelineItems(first: 100, itemTypes: [CROSS_REFERENCED_EVENT, CONNECTED_EVENT]) {{
        nodes {{
          __typename
          ... on CrossReferencedEvent {{
            source {{
              __typename
              ... on PullRequest {{
{_PR_FIELDS}
              }}
            }}
          }}
          ... on ConnectedEvent {{
            subject {{
              __typename
              ... on PullRequest {{
{_PR_FIELDS}
              }}
            }}
          }}
        }}
      }}
    }}
  }}
}}
"""

_FETCH_WORKERS = 3
_SUBMITTED_REVIEW_STATES = frozenset(
    {"APPROVED", "CHANGES_REQUESTED", "COMMENTED", "DISMISSED"}
)


def list_prs_in_review(
    items: dict[str, Any],
    milestone: str | None = "all",
) -> list[dict[str, Any]]:
    """Fetch and rank open in-review PRs linked to milestone issues."""
    issue_ids = [
        iid
        for iid, item in items.items()
        if item.get("kind", "issue") == "issue"
        and item.get("id")
        and item.get("state") == "OPEN"
        and _issue_in_milestone(item, milestone)
    ]
    merged: dict[str, dict[str, Any]] = {}
    if not issue_ids:
        return []

    workers = min(_FETCH_WORKERS, len(issue_ids))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_fetch_prs_for_issue, iid): iid for iid in issue_ids}
        for fut in as_completed(futures):
            try:
                for pr in fut.result():
                    pid = pr.get("id")
                    if pid:
                        merged[pid] = pr
            except Exception:
                continue

    rows = [classify_pr(pr) for pr in merged.values() if is_in_review(pr)]
    rows.sort(key=lambda r: (-(r.get("number") or 0), (r.get("title") or "").lower()))
    return rows


def is_in_review(pr: dict[str, Any]) -> bool:
    """Open PR in review; drafts only if a review has already started."""
    if pr.get("merged") or pr.get("state") in ("MERGED", "CLOSED"):
        return False
    if pr.get("state") != "OPEN":
        return False
    submitted = _non_author_submitted_reviews(pr)
    if pr.get("isDraft") and not submitted:
        return False
    return True


def classify_pr(pr: dict[str, Any]) -> dict[str, Any]:
    """Normalize a PR node into a UI row."""
    reviewers = reviewer_names(pr)
    author_login = _pr_author_login(pr)
    return {
        "id": pr.get("id"),
        "number": pr.get("number"),
        "title": pr.get("title") or "",
        "url": pr.get("url") or "",
        "is_draft": bool(pr.get("isDraft")),
        "author_label": people.display_name(author_login) if author_login else "—",
        "reviewers_label": (
            ", ".join(reviewers) if reviewers else "Needs reviewer"
        ),
        "pending_on": pending_on(pr),
    }


def pending_on(pr: dict[str, Any]) -> str:
    """Who the PR is waiting on, or ready to merge.

    - Approved → ready to merge
    - Changes requested → author
    - Outstanding review request (including re-requests after comments) → reviewer
    - Someone already reviewed and nobody is currently requested → author
    - Otherwise → reviewer / needs reviewer
    """
    decision = (pr.get("reviewDecision") or "").upper()
    if decision == "APPROVED":
        return "Ready to merge"
    if decision == "CHANGES_REQUESTED":
        return "Pending on author"
    if _has_outstanding_review_requests(pr):
        return "Pending on reviewer"
    if _non_author_submitted_reviews(pr):
        return "Pending on author"
    return "Pending on reviewer"


def _has_outstanding_review_requests(pr: dict[str, Any]) -> bool:
    for node in (pr.get("reviewRequests") or {}).get("nodes") or []:
        if not node:
            continue
        reviewer = node.get("requestedReviewer") or {}
        if reviewer.get("__typename") in ("User", "Team"):
            return True
        # Some payloads omit __typename but still carry login/name.
        if reviewer.get("login") or reviewer.get("name"):
            return True
    return False


def reviewer_names(pr: dict[str, Any]) -> list[str]:
    """Requested reviewers plus anyone who already submitted a review.

    Excludes the PR author and bots.
    """
    author = ((pr.get("author") or {}).get("login") or "").lower()
    names: list[str] = []
    seen: set[str] = set()

    def add_login(login: str | None) -> None:
        if not login or login.endswith("[bot]"):
            return
        if login.lower() == author:
            return
        label = people.display_name(login)
        key = label.lower()
        if not label or key in seen:
            return
        seen.add(key)
        names.append(label)

    def add_team(name: str | None) -> None:
        if not name:
            return
        key = name.lower()
        if key in seen:
            return
        seen.add(key)
        names.append(name)

    for node in (pr.get("reviewRequests") or {}).get("nodes") or []:
        if not node:
            continue
        reviewer = node.get("requestedReviewer") or {}
        if reviewer.get("__typename") == "User":
            add_login(reviewer.get("login"))
        elif reviewer.get("__typename") == "Team":
            add_team(reviewer.get("name"))

    for node in _submitted_reviews(pr):
        add_login(((node.get("author") or {}).get("login")))

    return names


# Back-compat alias used by older tests / imports.
requested_reviewer_names = reviewer_names


def _pr_author_login(pr: dict[str, Any]) -> str:
    return ((pr.get("author") or {}).get("login") or "")


def _submitted_reviews(pr: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for node in (pr.get("reviews") or {}).get("nodes") or []:
        if not node:
            continue
        if node.get("state") in _SUBMITTED_REVIEW_STATES:
            out.append(node)
    return out


def _non_author_submitted_reviews(pr: dict[str, Any]) -> list[dict[str, Any]]:
    author = _pr_author_login(pr).lower()
    out: list[dict[str, Any]] = []
    for node in _submitted_reviews(pr):
        login = ((node.get("author") or {}).get("login") or "")
        if login.endswith("[bot]"):
            continue
        if author and login.lower() == author:
            continue
        out.append(node)
    return out


def _fetch_prs_for_issue(issue_id: str) -> list[dict[str, Any]]:
    data = github.query(_ISSUE_OPEN_PRS_QUERY, {"id": issue_id})
    node = data.get("node") or {}
    found: dict[str, dict[str, Any]] = {}

    for pr in (node.get("closedByPullRequestsReferences") or {}).get("nodes") or []:
        if pr and pr.get("id"):
            found[pr["id"]] = pr

    for ev in (node.get("timelineItems") or {}).get("nodes") or []:
        if not ev:
            continue
        src = ev.get("source") or ev.get("subject") or {}
        if src.get("__typename") == "PullRequest" and src.get("id"):
            found[src["id"]] = src

    return list(found.values())


def _issue_in_milestone(item: dict[str, Any], milestone: str | None) -> bool:
    if not milestone or milestone == "all":
        return True
    return (item.get("milestone") or {}).get("title") == milestone
