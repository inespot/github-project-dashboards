"""Tests for PRs-in-review classification."""

from core.prs_in_review import classify_pr, is_in_review, pending_on, reviewer_names


def _pr(**kwargs):
    base = {
        "id": "PR_1",
        "number": 1,
        "title": "Fix thing",
        "url": "https://example.test/pull/1",
        "isDraft": False,
        "state": "OPEN",
        "merged": False,
        "reviewDecision": "REVIEW_REQUIRED",
        "author": {"login": "alice"},
        "reviewRequests": {"nodes": []},
        "reviews": {"nodes": []},
    }
    base.update(kwargs)
    return base


def test_open_ready_for_review_pr_counts():
    assert is_in_review(_pr())


def test_draft_without_reviews_excluded():
    assert not is_in_review(_pr(isDraft=True, reviews={"nodes": []}))


def test_draft_with_submitted_review_included():
    assert is_in_review(
        _pr(
            isDraft=True,
            reviews={
                "nodes": [
                    {"state": "COMMENTED", "author": {"login": "bob"}},
                ]
            },
        )
    )


def test_merged_and_closed_excluded():
    assert not is_in_review(_pr(merged=True, state="MERGED"))
    assert not is_in_review(_pr(state="CLOSED"))


def test_ready_to_merge_when_approved():
    assert pending_on(_pr(reviewDecision="APPROVED")) == "Ready to merge"


def test_pending_on_author_when_someone_responded_and_no_open_requests():
    assert (
        pending_on(
            _pr(
                reviewDecision="REVIEW_REQUIRED",
                reviewRequests={"nodes": []},
                reviews={
                    "nodes": [
                        {"state": "COMMENTED", "author": {"login": "inespot"}},
                    ]
                },
            )
        )
        == "Pending on author"
    )


def test_pending_on_reviewer_when_rerequested_after_comments():
    # David already commented, then was re-requested → waiting on reviewer.
    assert (
        pending_on(
            _pr(
                author={"login": "inespot"},
                reviewDecision="REVIEW_REQUIRED",
                reviewRequests={
                    "nodes": [
                        {
                            "requestedReviewer": {
                                "__typename": "User",
                                "login": "DaveCTurner",
                            }
                        }
                    ]
                },
                reviews={
                    "nodes": [
                        {"state": "COMMENTED", "author": {"login": "DaveCTurner"}},
                    ]
                },
            )
        )
        == "Pending on reviewer"
    )


def test_pending_on_author_when_changes_requested():
    assert pending_on(_pr(reviewDecision="CHANGES_REQUESTED")) == "Pending on author"


def test_pending_on_reviewer_when_nobody_responded():
    assert (
        pending_on(
            _pr(
                reviewDecision="REVIEW_REQUIRED",
                reviewRequests={
                    "nodes": [
                        {
                            "requestedReviewer": {
                                "__typename": "User",
                                "login": "samxbr",
                            }
                        }
                    ]
                },
            )
        )
        == "Pending on reviewer"
    )


def test_needs_reviewer_when_no_requests_or_reviews():
    row = classify_pr(_pr())
    assert row["reviewers_label"] == "Needs reviewer"
    assert row["pending_on"] == "Pending on reviewer"


def test_reviewers_include_requests_and_respondents_exclude_author():
    pr = _pr(
        author={"login": "burqen"},
        reviewRequests={
            "nodes": [
                {
                    "requestedReviewer": {
                        "__typename": "User",
                        "login": "samxbr",
                    }
                },
            ]
        },
        reviews={
            "nodes": [
                {"state": "COMMENTED", "author": {"login": "inespot"}},
                {"state": "COMMENTED", "author": {"login": "burqen"}},
            ]
        },
    )
    assert reviewer_names(pr) == ["Sam", "Ines"]
    row = classify_pr(pr)
    assert row["author_label"] == "Anton"
    assert row["reviewers_label"] == "Sam, Ines"
    # Sam still requested → waiting on reviewer, even though Ines already commented.
    assert row["pending_on"] == "Pending on reviewer"


def test_approved_reviewers_exclude_author_comments():
    pr = _pr(
        author={"login": "inespot"},
        reviewDecision="APPROVED",
        reviews={
            "nodes": [
                {"state": "COMMENTED", "author": {"login": "inespot"}},
                {"state": "APPROVED", "author": {"login": "DaveCTurner"}},
                {"state": "APPROVED", "author": {"login": "burqen"}},
                {"state": "APPROVED", "author": {"login": "lkts"}},
                {"state": "APPROVED", "author": {"login": "samxbr"}},
            ]
        },
    )
    assert reviewer_names(pr) == ["David", "Anton", "Sasha", "Sam"]
    assert classify_pr(pr)["pending_on"] == "Ready to merge"
