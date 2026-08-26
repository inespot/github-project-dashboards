"""Tests for proposal vs base field diffs."""

from core.diff import ASSIGNEES_FIELD, compute


def test_compute_includes_assignee_changes():
    p_items = {
        "I1": {
            "number": 1,
            "title": "One",
            "url": "https://example.test/1",
            "assignees": ["inespot"],
        }
    }
    b_items = {
        "I1": {
            "number": 1,
            "title": "One",
            "url": "https://example.test/1",
            "assignees": ["samxbr"],
        }
    }
    changes = compute(p_items, {"I1": {}}, b_items, {"I1": {}})
    assert len(changes) == 1
    assert changes[0].field == ASSIGNEES_FIELD
    assert changes[0].base_value == "Sam"
    assert changes[0].proposal_value == "Ines"


def test_compute_ignores_assignee_order():
    p_items = {
        "I1": {
            "number": 1,
            "title": "One",
            "url": "",
            "assignees": ["samxbr", "inespot"],
        }
    }
    b_items = {
        "I1": {
            "number": 1,
            "title": "One",
            "url": "",
            "assignees": ["inespot", "samxbr"],
        }
    }
    assert compute(p_items, {}, b_items, {}) == []


def test_legacy_proposal_without_assignees_key_skips_assignee_diff():
    p_items = {
        "I1": {
            "number": 1,
            "title": "One",
            "url": "",
            "assignees": None,
        }
    }
    b_items = {
        "I1": {
            "number": 1,
            "title": "One",
            "url": "",
            "assignees": ["inespot"],
        }
    }
    assert compute(p_items, {}, b_items, {}) == []


def test_compute_still_diffs_regular_fields():
    p_items = {"I1": {"number": 2, "title": "Two", "url": "", "assignees": []}}
    p_fields = {"I1": {"Estimate": {"value": "3"}}}
    b_items = {"I1": {"number": 2, "title": "Two", "url": "", "assignees": []}}
    b_fields = {"I1": {"Estimate": {"value": "5"}}}
    changes = compute(p_items, p_fields, b_items, b_fields)
    assert len(changes) == 1
    assert changes[0].field == "Estimate"
    assert changes[0].base_value == "5"
    assert changes[0].proposal_value == "3"


def test_issue_rows_groups_changes_and_marks_cells():
    from core.diff import issue_rows

    p_items = {
        "I1": {
            "number": 10,
            "title": "Alpha",
            "url": "https://example.test/10",
            "assignees": ["inespot"],
        }
    }
    p_fields = {
        "I1": {
            "Start Date": {"value": "2026-09-01"},
            "Target End Date": {"value": "2026-09-10"},
            "Estimate": {"value": "4.0"},
        }
    }
    b_items = {
        "I1": {
            "number": 10,
            "title": "Alpha",
            "url": "https://example.test/10",
            "assignees": ["samxbr"],
        }
    }
    b_fields = {
        "I1": {
            "Start Date": {"value": "2026-09-01"},
            "Target End Date": {"value": "2026-09-20"},
            "Estimate": {"value": "5.0"},
        }
    }
    rows = issue_rows(
        p_items,
        p_fields,
        b_items,
        b_fields,
        ["Start Date", "Target End Date", "Estimate", "Assignees"],
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.cells["Start Date"].changed is False
    assert row.cells["Start Date"].text == "2026-09-01"
    assert row.cells["Target End Date"].changed is True
    assert row.cells["Target End Date"].text == "2026-09-20 → 2026-09-10"
    assert row.cells["Estimate"].text == "5.0 → 4.0"
    assert row.cells["Assignees"].text == "Sam → Ines"


def test_issue_rows_skips_status_only_changes():
    from core.diff import issue_rows

    p_items = {
        "I1": {
            "number": 1,
            "title": "Status only",
            "url": "",
            "assignees": [],
        }
    }
    p_fields = {
        "I1": {
            "Status": {"value": "Done"},
            "Estimate": {"value": "5.0"},
        }
    }
    b_items = {
        "I1": {
            "number": 1,
            "title": "Status only",
            "url": "",
            "assignees": [],
        }
    }
    b_fields = {
        "I1": {
            "Status": {"value": "Todo"},
            "Estimate": {"value": "5.0"},
        }
    }
    rows = issue_rows(
        p_items,
        p_fields,
        b_items,
        b_fields,
        ["Start Date", "Target End Date", "Estimate", "Assignees"],
    )
    assert rows == []


def test_issue_rows_ordered_by_new_start_date():
    from core.diff import issue_rows

    p_items = {
        "I1": {"number": 1, "title": "Late", "url": "", "assignees": []},
        "I2": {"number": 2, "title": "Early", "url": "", "assignees": []},
    }
    p_fields = {
        "I1": {"Start Date": {"value": "2026-09-20"}},
        "I2": {"Start Date": {"value": "2026-09-01"}},
    }
    b_items = {
        "I1": {"number": 1, "title": "Late", "url": "", "assignees": []},
        "I2": {"number": 2, "title": "Early", "url": "", "assignees": []},
    }
    b_fields = {
        "I1": {"Start Date": {"value": "2026-08-01"}},
        "I2": {"Start Date": {"value": "2026-08-01"}},
    }
    rows = issue_rows(
        p_items,
        p_fields,
        b_items,
        b_fields,
        ["Start Date", "Target End Date", "Estimate", "Assignees"],
    )
    assert [r.number for r in rows] == [2, 1]
