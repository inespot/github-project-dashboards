"""Project review awards: distinct PRs formally reviewed per person."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from typing import Any

from core import github, people, store

_ISSUE_PR_REVIEWS_QUERY = """
query IssuePrReviews($id: ID!) {
  rateLimit { remaining resetAt }
  node(id: $id) {
    ... on Issue {
      closedByPullRequestsReferences(first: 20, includeClosedPrs: true) {
        nodes {
          id
          number
          url
          title
          author { login }
          reviews(first: 100) {
            nodes {
              state
              author { login }
            }
          }
        }
      }
      timelineItems(first: 100, itemTypes: [CROSS_REFERENCED_EVENT, CONNECTED_EVENT]) {
        nodes {
          __typename
          ... on CrossReferencedEvent {
            source {
              __typename
              ... on PullRequest {
                id
                number
                url
                title
                author { login }
                reviews(first: 100) {
                  nodes {
                    state
                    author { login }
                  }
                }
              }
            }
          }
          ... on ConnectedEvent {
            subject {
              __typename
              ... on PullRequest {
                id
                number
                url
                title
                author { login }
                reviews(first: 100) {
                  nodes {
                    state
                    author { login }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""

# Keep concurrency low — awards fan out one GraphQL call per issue.
_FETCH_WORKERS = 2

# Submitted reviews (Approve, Request changes, or Comment via the review UI).
_COUNTABLE_STATES = frozenset({"APPROVED", "CHANGES_REQUESTED", "COMMENTED"})

_CACHE_NAME = "reviews"
_CACHE_VERSION = 4  # reviews.json with pr_numbers per person


def read_local_awards(project_id: str) -> list[dict[str, Any]] | None:
    """Return disk-cached award rows (login/name/count/leader) if compatible."""
    cached = read_local_reviews(project_id)
    if cached is None:
        return None
    return cached.get("awards")


def read_local_reviews(project_id: str) -> dict[str, Any] | None:
    """Return full ``reviews.json`` payload if present and compatible."""
    cached = store.read_cache(project_id, _CACHE_NAME)
    if not isinstance(cached, dict):
        return None
    if cached.get("version") != _CACHE_VERSION:
        return None
    awards = cached.get("awards")
    by_person = cached.get("by_person")
    if not isinstance(awards, list) or not isinstance(by_person, dict):
        return None
    return cached


def review_awards(
    items: dict[str, Any],
    project_id: str | None = None,
    *,
    force: bool = False,
) -> list[dict[str, Any]]:
    """Rank people by how many project-linked PRs they formally reviewed.

    A PR counts if it closes or is linked/related to a project issue, and the
    person submitted APPROVED, CHANGES_REQUESTED, or COMMENTED via the review
    UI (once per PR). PENDING / bots / self-reviews on own PRs are excluded.

    When ``project_id`` is set, a successful complete fetch writes ``reviews.json``
    with per-person counts and PR numbers. Partial fetches keep the previous
    disk cache instead of under-counting.
    """
    del force  # disk bypass is handled by the Overview prefetch path

    issue_ids = [
        iid
        for iid, item in items.items()
        if item.get("kind", "issue") == "issue" and item.get("id")
    ]
    pr_reviews, failures = _fetch_pr_reviews_for_issues(issue_ids)

    if failures:
        if project_id:
            local = read_local_awards(project_id)
            if local is not None:
                return local
        if not pr_reviews:
            raise RuntimeError(
                f"Failed to fetch review data for all {len(failures)} issues "
                f"(likely rate-limited)."
            )
        return build_awards(pr_reviews)["awards"]

    payload = build_awards(pr_reviews)
    if project_id:
        store.write_cache(project_id, _CACHE_NAME, payload)
    return payload["awards"]


def build_awards(pr_reviews: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Build the ``reviews.json`` payload from a PR → reviewers map."""
    by_login: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for _pr_id, info in pr_reviews.items():
        author = info.get("author")
        number = info.get("number")
        if number is None:
            continue
        pr_meta = {
            "number": int(number),
            "url": info.get("url") or "",
            "title": info.get("title") or "",
        }
        for login in info.get("reviewers") or []:
            if not login or login == author:
                continue
            if login.endswith("[bot]"):
                continue
            by_login[login].append(pr_meta)

    by_person: dict[str, Any] = {}
    awards: list[dict[str, Any]] = []
    for login, prs in by_login.items():
        # Distinct by PR number (same PR may appear via multiple issues).
        unique: dict[int, dict[str, Any]] = {}
        for pr in prs:
            unique[pr["number"]] = pr
        ordered = sorted(unique.values(), key=lambda p: p["number"])
        numbers = [p["number"] for p in ordered]
        entry = {
            "login": login,
            "name": people.display_name(login),
            "count": len(numbers),
            "pr_numbers": numbers,
            "prs": ordered,
        }
        by_person[login] = entry
        awards.append(
            {
                "login": login,
                "name": entry["name"],
                "count": entry["count"],
                "pr_numbers": numbers,
            }
        )

    awards.sort(key=lambda row: (-row["count"], row["name"].lower()))
    if awards:
        top = awards[0]["count"]
        for row in awards:
            row["leader"] = row["count"] == top
            by_person[row["login"]]["leader"] = row["leader"]

    return {
        "version": _CACHE_VERSION,
        "awards": awards,
        "by_person": by_person,
    }


def rank_reviewers(
    pr_reviews: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Backward-compatible wrapper: award rows only."""
    return build_awards(pr_reviews)["awards"]


def _fetch_pr_reviews_for_issues(
    issue_ids: list[str],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Return ``(pr_map, failed_issue_ids)``."""
    if not issue_ids:
        return {}, []

    merged: dict[str, dict[str, Any]] = {}
    failures: list[str] = []
    workers = min(_FETCH_WORKERS, len(issue_ids))

    def one(issue_id: str) -> tuple[str, dict[str, dict[str, Any]] | None, str | None]:
        try:
            return issue_id, _prs_with_reviewers(issue_id), None
        except Exception as exc:
            return issue_id, None, str(exc)

    if len(issue_ids) == 1:
        _iid, result, err = one(issue_ids[0])
        if err or result is None:
            return {}, [issue_ids[0]]
        return result, []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one, iid) for iid in issue_ids]
        for fut in as_completed(futures):
            issue_id, result, err = fut.result()
            if err or result is None:
                failures.append(issue_id)
                continue
            for pr_id, info in result.items():
                existing = merged.get(pr_id)
                if existing is None:
                    merged[pr_id] = {
                        "author": info.get("author"),
                        "number": info.get("number"),
                        "url": info.get("url"),
                        "title": info.get("title"),
                        "reviewers": set(info.get("reviewers") or []),
                    }
                else:
                    existing["reviewers"].update(info.get("reviewers") or [])
                    if not existing.get("author") and info.get("author"):
                        existing["author"] = info["author"]
                    if existing.get("number") is None and info.get("number") is not None:
                        existing["number"] = info["number"]
                        existing["url"] = info.get("url")
                        existing["title"] = info.get("title")
    return merged, failures


def _prs_with_reviewers(issue_id: str) -> dict[str, dict[str, Any]]:
    data = github.query(_ISSUE_PR_REVIEWS_QUERY, {"id": issue_id})
    node = data.get("node") or {}
    result: dict[str, dict[str, Any]] = {}

    for pr in (node.get("closedByPullRequestsReferences") or {}).get("nodes") or []:
        _absorb_pr(result, pr)

    for ev in (node.get("timelineItems") or {}).get("nodes") or []:
        if not ev:
            continue
        src = ev.get("source") or ev.get("subject") or {}
        if src.get("__typename") == "PullRequest":
            _absorb_pr(result, src)

    return result


def _absorb_pr(result: dict[str, dict[str, Any]], pr: dict[str, Any] | None) -> None:
    if not pr or not pr.get("id"):
        return
    author = ((pr.get("author") or {}).get("login")) or None
    reviewers: set[str] = set()
    for review in (pr.get("reviews") or {}).get("nodes") or []:
        if not review:
            continue
        if review.get("state") not in _COUNTABLE_STATES:
            continue
        login = ((review.get("author") or {}).get("login")) or None
        # Never count someone reviewing / commenting on their own PR.
        if not login or login == author:
            continue
        if login.endswith("[bot]"):
            continue
        reviewers.add(login)
    existing = result.get(pr["id"])
    if existing is None:
        result[pr["id"]] = {
            "author": author,
            "number": pr.get("number"),
            "url": pr.get("url"),
            "title": pr.get("title"),
            "reviewers": reviewers,
        }
    else:
        existing["reviewers"].update(reviewers)
        if not existing.get("author") and author:
            existing["author"] = author
        if existing.get("number") is None and pr.get("number") is not None:
            existing["number"] = pr.get("number")
            existing["url"] = pr.get("url")
            existing["title"] = pr.get("title")
