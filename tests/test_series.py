"""Tests for core.series."""

from datetime import date

from core.series import burnup


def _issue(issue_id: str, number: int, created: str, estimate: float, milestone=None):
    return {
        "id": issue_id,
        "number": number,
        "title": f"Issue {number}",
        "url": "",
        "state": "OPEN",
        "stateReason": None,
        "createdAt": created,
        "closedAt": None,
        "milestone": {"title": milestone} if milestone else None,
        "assignees": [],
        "labels": [],
        "parent": None,
        "updatedAt": created,
        "project_status": None,
    }


def test_burnup_does_not_skip_days_when_milestone_filter_excludes_items():
    items = {
        "I_1": _issue("I_1", 1, "2026-08-01T00:00:00Z", 5),
    }
    timelines = {"I_1": []}
    field_values = {
        "I_1": {
            "Estimate": {"value": 5, "updatedAt": "2026-08-01T00:00:00Z"},
        },
    }

    rows = burnup(
        project_id="proj",
        milestone="9.3",
        estimate_field="Estimate",
        items=items,
        timelines=timelines,
        live_field_values=field_values,
        start=date(2026, 8, 1),
        end=date(2026, 8, 3),
        snapshots={},
    )

    assert [row["date"] for row in rows] == ["2026-08-01", "2026-08-02", "2026-08-03"]


def test_burnup_stacks_done_in_progress_and_todo_to_scope():
    items = {
        "I_done": _issue("I_done", 1, "2026-08-01T00:00:00Z", 3, milestone="9.3"),
        "I_wip": _issue("I_wip", 2, "2026-08-01T00:00:00Z", 2, milestone="9.3"),
        "I_todo": _issue("I_todo", 3, "2026-08-01T00:00:00Z", 5, milestone="9.3"),
    }
    timelines = {
        "I_done": [
            {"kind": "milestoned", "at": "2026-08-01T00:00:00Z", "from_": None, "to": "9.3"},
            {"kind": "closed", "at": "2026-08-02T00:00:00Z", "from_": None, "to": "COMPLETED"},
        ],
        "I_wip": [
            {"kind": "milestoned", "at": "2026-08-01T00:00:00Z", "from_": None, "to": "9.3"},
            {
                "kind": "project_v2_status_changed",
                "at": "2026-08-02T00:00:00Z",
                "from_": "Todo",
                "to": "In Progress",
            },
        ],
        "I_todo": [
            {"kind": "milestoned", "at": "2026-08-01T00:00:00Z", "from_": None, "to": "9.3"},
        ],
    }
    field_values = {
        "I_done": {"Estimate": {"value": 3, "updatedAt": "2026-08-01T00:00:00Z"}},
        "I_wip": {"Estimate": {"value": 2, "updatedAt": "2026-08-01T00:00:00Z"}},
        "I_todo": {"Estimate": {"value": 5, "updatedAt": "2026-08-01T00:00:00Z"}},
    }

    rows = burnup(
        project_id="proj",
        milestone="9.3",
        estimate_field="Estimate",
        items=items,
        timelines=timelines,
        live_field_values=field_values,
        start=date(2026, 8, 1),
        end=date(2026, 8, 3),
        snapshots={},
    )

    day1 = rows[0]
    assert day1["scope"] == 10.0
    assert day1["completed"] == 0.0
    assert day1["in_progress"] == 0.0
    assert day1["todo"] == 10.0

    day2 = rows[1]
    assert day2["scope"] == 10.0
    assert day2["completed"] == 3.0
    assert day2["in_progress"] == 2.0
    assert day2["todo"] == 5.0
    assert day2["completed"] + day2["in_progress"] + day2["todo"] == day2["scope"]
