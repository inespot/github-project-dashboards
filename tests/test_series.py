"""Tests for core.series."""

from datetime import date

from core.series import burnup


def test_burnup_does_not_skip_days_when_milestone_filter_excludes_items():
    items = {
        "I_1": {
            "id": "I_1",
            "number": 1,
            "title": "Alpha",
            "url": "",
            "state": "OPEN",
            "stateReason": None,
            "createdAt": "2026-08-01T00:00:00Z",
            "closedAt": None,
            "milestone": None,
            "assignees": [],
            "labels": [],
            "parent": None,
            "updatedAt": "2026-08-01T00:00:00Z",
        },
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
