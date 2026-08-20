"""Tests for core.reviews review awards ranking and reviews.json cache shape."""

from core.reviews import build_awards, rank_reviewers


def test_rank_reviewers_counts_distinct_prs_and_marks_leader():
    pr_reviews = {
        "PR_1": {
            "author": "alice",
            "number": 1,
            "url": "https://example.test/1",
            "title": "One",
            "reviewers": {"bob", "carol"},
        },
        "PR_2": {
            "author": "alice",
            "number": 2,
            "url": "https://example.test/2",
            "title": "Two",
            "reviewers": {"bob"},
        },
        "PR_3": {
            "author": "bob",
            "number": 3,
            "url": "https://example.test/3",
            "title": "Three",
            "reviewers": {"carol"},
        },
    }
    ranked = rank_reviewers(pr_reviews)
    assert [r["login"] for r in ranked] == ["bob", "carol"]
    assert ranked[0]["count"] == 2
    assert ranked[0]["pr_numbers"] == [1, 2]
    assert ranked[0]["leader"] is True
    assert ranked[1]["count"] == 2
    assert ranked[1]["pr_numbers"] == [1, 3]
    assert ranked[1]["leader"] is True


def test_build_awards_writes_by_person_with_pr_numbers():
    pr_reviews = {
        "PR_1": {
            "author": "alice",
            "number": 10,
            "url": "https://example.test/10",
            "title": "Ten",
            "reviewers": {"inespot"},
        },
        "PR_2": {
            "author": "alice",
            "number": 20,
            "url": "https://example.test/20",
            "title": "Twenty",
            "reviewers": {"inespot"},
        },
    }
    payload = build_awards(pr_reviews)
    assert payload["version"] == 4
    person = payload["by_person"]["inespot"]
    assert person["name"] == "Ines"
    assert person["count"] == 2
    assert person["pr_numbers"] == [10, 20]
    assert person["prs"][0]["title"] == "Ten"


def test_rank_reviewers_excludes_author_self_review_and_bots():
    pr_reviews = {
        "PR_1": {
            "author": "alice",
            "number": 1,
            "url": "",
            "title": "",
            "reviewers": {"alice", "dependabot[bot]", "bob"},
        },
    }
    ranked = rank_reviewers(pr_reviews)
    assert len(ranked) == 1
    assert ranked[0]["login"] == "bob"
    assert ranked[0]["count"] == 1
    assert ranked[0]["leader"] is True


def test_rank_reviewers_empty():
    assert rank_reviewers({}) == []


def test_rank_reviewers_uses_display_names():
    pr_reviews = {
        "PR_1": {
            "author": "other",
            "number": 1,
            "url": "",
            "title": "",
            "reviewers": {"inespot"},
        },
    }
    ranked = rank_reviewers(pr_reviews)
    assert ranked[0]["name"] == "Ines"


def test_absorb_pr_counts_submitted_reviews_including_commented():
    from core.reviews import _absorb_pr

    result: dict = {}
    _absorb_pr(
        result,
        {
            "id": "PR_1",
            "number": 42,
            "url": "https://example.test/42",
            "title": "Forty-two",
            "author": {"login": "alice"},
            "reviews": {
                "nodes": [
                    {"state": "APPROVED", "author": {"login": "bob"}},
                    {"state": "COMMENTED", "author": {"login": "carol"}},
                    {"state": "CHANGES_REQUESTED", "author": {"login": "dave"}},
                    {"state": "PENDING", "author": {"login": "erin"}},
                    {"state": "COMMENTED", "author": {"login": "alice"}},
                    {"state": "APPROVED", "author": {"login": "alice"}},
                ],
            },
        },
    )
    assert result["PR_1"]["reviewers"] == {"bob", "carol", "dave"}
    assert result["PR_1"]["number"] == 42


def test_absorb_pr_excludes_author_comment_reviews():
    from core.reviews import _absorb_pr

    result: dict = {}
    _absorb_pr(
        result,
        {
            "id": "PR_1",
            "number": 7,
            "url": "",
            "title": "",
            "author": {"login": "burqen"},
            "reviews": {
                "nodes": [
                    {"state": "COMMENTED", "author": {"login": "burqen"}},
                    {"state": "COMMENTED", "author": {"login": "inespot"}},
                ],
            },
        },
    )
    assert result["PR_1"]["reviewers"] == {"inespot"}
