"""Tests for core.roadmap schedule comparison."""

from datetime import date
from unittest.mock import patch

from core.roadmap import issue_completed, roadmap_delta_days, workdays_between


def test_workdays_between_weekdays_only():
    # Mon 2026-08-17 to Fri 2026-08-21 = 5
    assert workdays_between(date(2026, 8, 17), date(2026, 8, 21)) == 5
    # Fri to next Mon = 2 (Fri, Mon)
    assert workdays_between(date(2026, 8, 21), date(2026, 8, 24)) == 2
    assert workdays_between(date(2026, 8, 21), date(2026, 8, 20)) == 0


def test_overdue_open_todo_owes_full_span():
    # Mon 8/10 – Fri 8/14 = 5 workdays; open Todo past end → earned 0, owed 5
    items = {
        "I_1": {
            "id": "I_1",
            "state": "OPEN",
            "stateReason": None,
            "project_status": "Todo",
            "milestone": {"title": "M1"},
        },
    }
    field_values = {
        "I_1": {
            "Start Date": {"value": "2026-08-10"},
            "Target End Date": {"value": "2026-08-14"},
        },
    }
    with patch("core.roadmap.progress_from_cache", return_value=0.0):
        delta = roadmap_delta_days(
            "M1", items, field_values, "Start Date", "Target End Date", date(2026, 8, 19)
        )
    assert delta == -5


def test_overdue_in_progress_partially_offsets_owed_span():
    # Span 5; In Progress at 20% → earned 1, owed 5 → delta -4
    items = {
        "I_1": {
            "id": "I_1",
            "state": "OPEN",
            "stateReason": None,
            "project_status": "In Progress",
            "milestone": {"title": "M1"},
        },
    }
    field_values = {
        "I_1": {
            "Start Date": {"value": "2026-08-10"},
            "Target End Date": {"value": "2026-08-14"},
        },
    }
    with patch("core.roadmap.progress_from_cache", return_value=0.20):
        delta = roadmap_delta_days(
            "M1", items, field_values, "Start Date", "Target End Date", date(2026, 8, 19)
        )
    assert delta == -4


def test_open_not_yet_due_is_ignored():
    items = {
        "I_1": {
            "id": "I_1",
            "state": "OPEN",
            "stateReason": None,
            "project_status": "In Progress",
            "milestone": {"title": "M1"},
        },
    }
    field_values = {
        "I_1": {
            "Start Date": {"value": "2026-08-17"},
            "Target End Date": {"value": "2026-08-21"},
        },
    }
    with patch("core.roadmap.progress_from_cache", return_value=0.70):
        delta = roadmap_delta_days(
            "M1", items, field_values, "Start Date", "Target End Date", date(2026, 8, 19)
        )
    assert delta is None


def test_completed_past_due_cancels_out():
    # Completed with end < today: owed and earned both get full span → 0
    items = {
        "I_1": {
            "id": "I_1",
            "state": "CLOSED",
            "stateReason": "COMPLETED",
            "project_status": "Done",
            "milestone": {"title": "M1"},
        },
    }
    field_values = {
        "I_1": {
            "Start Date": {"value": "2026-08-10"},
            "Target End Date": {"value": "2026-08-14"},
        },
    }
    delta = roadmap_delta_days(
        "M1", items, field_values, "Start Date", "Target End Date", date(2026, 8, 19)
    )
    assert delta == 0


def test_completed_early_earns_full_span_without_owed():
    # Completed with end still in the future → earned only
    items = {
        "I_1": {
            "id": "I_1",
            "state": "CLOSED",
            "stateReason": "COMPLETED",
            "project_status": "Done",
            "milestone": {"title": "M1"},
        },
    }
    field_values = {
        "I_1": {
            "Start Date": {"value": "2026-08-24"},
            "Target End Date": {"value": "2026-08-28"},
        },
    }
    delta = roadmap_delta_days(
        "M1", items, field_values, "Start Date", "Target End Date", date(2026, 8, 19)
    )
    assert delta == 5


def test_earned_minus_owed_net():
    # Past-due completed cancels; overdue open at 0% is pure debt → -5
    items = {
        "I_done": {
            "id": "I_done",
            "state": "CLOSED",
            "stateReason": "COMPLETED",
            "project_status": "Done",
            "milestone": {"title": "M1"},
        },
        "I_late": {
            "id": "I_late",
            "state": "OPEN",
            "stateReason": None,
            "project_status": "Todo",
            "milestone": {"title": "M1"},
        },
        "I_future": {
            "id": "I_future",
            "state": "OPEN",
            "stateReason": None,
            "project_status": "In Progress",
            "milestone": {"title": "M1"},
        },
    }
    field_values = {
        "I_done": {
            "Start Date": {"value": "2026-08-03"},
            "Target End Date": {"value": "2026-08-07"},
        },
        "I_late": {
            "Start Date": {"value": "2026-08-10"},
            "Target End Date": {"value": "2026-08-14"},
        },
        "I_future": {
            "Start Date": {"value": "2026-08-24"},
            "Target End Date": {"value": "2026-08-28"},
        },
    }
    with patch("core.roadmap.progress_from_cache", return_value=0.0):
        delta = roadmap_delta_days(
            "M1", items, field_values, "Start Date", "Target End Date", date(2026, 8, 19)
        )
    assert delta == -5


def test_skips_issues_without_both_dates():
    items = {
        "I_1": {
            "id": "I_1",
            "state": "OPEN",
            "stateReason": None,
            "project_status": "Todo",
            "milestone": {"title": "M1"},
        },
    }
    field_values = {
        "I_1": {
            "Target End Date": {"value": "2026-08-14"},
        },
    }
    assert roadmap_delta_days(
        "M1", items, field_values, "Start Date", "Target End Date", date(2026, 8, 19)
    ) is None


def test_issue_completed():
    assert issue_completed({"stateReason": "COMPLETED", "project_status": "Todo"})
    assert issue_completed({"stateReason": None, "project_status": "Done"})
    assert not issue_completed({"state": "OPEN", "stateReason": None, "project_status": "In Progress"})
