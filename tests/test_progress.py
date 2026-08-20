"""Tests for core.progress — pure, no network."""

from core.progress import progress, progress_from_cache, prefetch_prs, _pr_credit

OPEN_ISSUE = {"id": "I_1", "number": 1, "title": "T", "url": "", "state": "OPEN",
              "stateReason": None}
CLOSED_ISSUE = {"id": "I_2", "number": 2, "title": "T", "url": "", "state": "CLOSED",
                "stateReason": "COMPLETED"}
IN_PROGRESS_ISSUE = {
    "id": "I_3", "number": 3, "title": "T", "url": "", "state": "OPEN",
    "stateReason": None, "project_status": "In Progress",
}


def test_closed_completed_is_100():
    assert progress(CLOSED_ISSUE, closing_prs=[], linked_prs=[]) == 1.0


def test_open_no_prs_is_zero():
    assert progress(OPEN_ISSUE, closing_prs=[], linked_prs=[]) == 0.0


def test_in_progress_status_alone_is_20():
    assert progress(IN_PROGRESS_ISSUE, closing_prs=[], linked_prs=[]) == 0.20


def test_draft_closing_pr_is_30():
    prs = [{"id": "pr1", "isDraft": True, "state": "OPEN", "merged": False}]
    assert progress(OPEN_ISSUE, closing_prs=prs, linked_prs=[]) == 0.30


def test_review_ready_closing_pr_is_70():
    prs = [{"id": "pr1", "isDraft": False, "state": "OPEN", "merged": False}]
    assert progress(OPEN_ISSUE, closing_prs=prs, linked_prs=[]) == 0.70


def test_merged_closing_pr_is_100():
    prs = [{"id": "pr1", "isDraft": False, "state": "MERGED", "merged": True}]
    assert progress(OPEN_ISSUE, closing_prs=prs, linked_prs=[]) == 1.0


def test_max_not_sum_draft_and_review():
    """Draft closing PR + review-ready closing PR => 70, not 100."""
    prs = [
        {"id": "pr1", "isDraft": True, "state": "OPEN", "merged": False},
        {"id": "pr2", "isDraft": False, "state": "OPEN", "merged": False},
    ]
    assert progress(OPEN_ISSUE, closing_prs=prs, linked_prs=[]) == 0.70


def test_in_progress_plus_draft_pr_is_30():
    prs = [{"id": "pr1", "isDraft": True, "state": "OPEN", "merged": False}]
    assert progress(IN_PROGRESS_ISSUE, closing_prs=prs, linked_prs=[]) == 0.30


def test_non_closing_linked_pr_gives_no_credit():
    linked = [{"id": "pr1", "isDraft": False, "state": "OPEN", "merged": False}]
    assert progress(OPEN_ISSUE, closing_prs=[], linked_prs=linked) == 0.0


def test_non_closing_linked_pr_does_not_boost_in_progress():
    linked = [{"id": "pr1", "isDraft": False, "state": "OPEN", "merged": False}]
    assert progress(IN_PROGRESS_ISSUE, closing_prs=[], linked_prs=linked) == 0.20


def test_closed_pr_closing_link_gives_zero_credit():
    prs = [{"id": "pr1", "isDraft": False, "state": "CLOSED", "merged": False}]
    assert progress(OPEN_ISSUE, closing_prs=prs, linked_prs=[]) == 0.0


def test_progress_from_cache_status_only_when_none():
    assert progress_from_cache(IN_PROGRESS_ISSUE, None) == 0.20


def test_progress_from_cache_uses_cached_prs():
    prs = {
        "I_1": ([{"id": "pr1", "isDraft": False, "state": "OPEN", "merged": False}], []),
    }
    assert progress_from_cache(OPEN_ISSUE, prs) == 0.70


def test_prefetch_prs_parallel(monkeypatch):
    calls = []

    def fake_fetch(issue_id: str):
        calls.append(issue_id)
        return ([{"id": "pr", "isDraft": True, "state": "OPEN", "merged": False}], [])

    monkeypatch.setattr("core.progress._fetch_prs", fake_fetch)
    result = prefetch_prs(["A", "B", "C"])
    assert set(calls) == {"A", "B", "C"}
    assert set(result) == {"A", "B", "C"}
    assert progress(OPEN_ISSUE, *result["A"]) == 0.30


def test_draft_issue_never_fetches_pr_progress():
    draft_issue = {"id": "DI_1", "kind": "draft_issue", "state": "OPEN", "stateReason": None}
    assert progress(draft_issue, closing_prs=[], linked_prs=[]) == 0.0


def test_draft_issue_in_progress_is_20():
    draft_issue = {
        "id": "DI_1",
        "kind": "draft_issue",
        "state": "OPEN",
        "stateReason": None,
        "project_status": "In Progress",
    }
    assert progress(draft_issue, closing_prs=[], linked_prs=[]) == 0.20
