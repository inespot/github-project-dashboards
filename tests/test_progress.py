"""Tests for core.progress — pure, no network."""

from core.progress import progress, _pr_credit

OPEN_ISSUE = {"id": "I_1", "number": 1, "title": "T", "url": "", "state": "OPEN",
              "stateReason": None}
CLOSED_ISSUE = {"id": "I_2", "number": 2, "title": "T", "url": "", "state": "CLOSED",
                "stateReason": "COMPLETED"}


def test_closed_completed_is_100():
    assert progress(CLOSED_ISSUE, closing_prs=[], linked_prs=[]) == 1.0


def test_open_no_prs_is_zero():
    assert progress(OPEN_ISSUE, closing_prs=[], linked_prs=[]) == 0.0


def test_draft_closing_pr_is_40():
    prs = [{"id": "pr1", "isDraft": True, "state": "OPEN", "merged": False}]
    assert progress(OPEN_ISSUE, closing_prs=prs, linked_prs=[]) == 0.40


def test_review_ready_closing_pr_is_70():
    prs = [{"id": "pr1", "isDraft": False, "state": "OPEN", "merged": False}]
    assert progress(OPEN_ISSUE, closing_prs=prs, linked_prs=[]) == 0.70


def test_merged_closing_pr_is_100():
    prs = [{"id": "pr1", "isDraft": False, "state": "MERGED", "merged": True}]
    assert progress(OPEN_ISSUE, closing_prs=prs, linked_prs=[]) == 1.0


def test_max_not_sum_draft_and_review():
    """Draft closing PR + review-ready closing PR => 70, not 110."""
    prs = [
        {"id": "pr1", "isDraft": True, "state": "OPEN", "merged": False},
        {"id": "pr2", "isDraft": False, "state": "OPEN", "merged": False},
    ]
    assert progress(OPEN_ISSUE, closing_prs=prs, linked_prs=[]) == 0.70


def test_non_closing_linked_pr_is_20():
    # pr2 is linked but NOT closing (different id not in closing set)
    closing = [{"id": "pr1", "isDraft": True, "state": "OPEN", "merged": False}]
    linked = [{"id": "pr2", "isDraft": False, "state": "OPEN", "merged": False}]
    # max(0.40 from closing, 0.20 from linked) = 0.40
    assert progress(OPEN_ISSUE, closing_prs=closing, linked_prs=linked) == 0.40


def test_only_linked_pr_is_20():
    linked = [{"id": "pr1", "isDraft": False, "state": "OPEN", "merged": False}]
    assert progress(OPEN_ISSUE, closing_prs=[], linked_prs=linked) == 0.20


def test_closed_pr_closing_link_gives_zero_credit():
    prs = [{"id": "pr1", "isDraft": False, "state": "CLOSED", "merged": False}]
    assert progress(OPEN_ISSUE, closing_prs=prs, linked_prs=[]) == 0.0


def test_draft_issue_never_fetches_pr_progress():
    draft_issue = {"id": "DI_1", "kind": "draft_issue", "state": "OPEN", "stateReason": None}
    assert progress(draft_issue, closing_prs=[], linked_prs=[]) == 0.0
