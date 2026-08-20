"""Tests for core.activity — pure, no network."""

from core.activity import (
    added_to_milestone,
    completed_in_window,
    currently_in_progress,
    since_date,
)

ITEMS = {
    "I_1": {"id": "I_1", "number": 1, "title": "Alpha", "url": "u1",
             "milestone": {"title": "9.3"}, "state": "OPEN", "assignees": ["inespot"]},
    "I_2": {"id": "I_2", "number": 2, "title": "Beta", "url": "u2",
             "milestone": {"title": "9.4"}, "state": "CLOSED", "assignees": ["samxbr"]},
    "I_3": {"id": "I_3", "number": 3, "title": "Gamma", "url": "u3",
             "milestone": None, "state": "CLOSED", "assignees": []},
}

TIMELINES = {
    "I_1": [
        {"kind": "milestoned", "at": "2026-08-10T10:00:00Z", "from_": None, "to": "9.3"},
    ],
    "I_2": [
        {"kind": "milestoned", "at": "2026-07-01T10:00:00Z", "from_": None, "to": "9.4"},
        {"kind": "closed", "at": "2026-08-12T10:00:00Z", "from_": None, "to": "COMPLETED"},
    ],
    "I_3": [
        {"kind": "closed", "at": "2026-08-13T10:00:00Z", "from_": None, "to": "COMPLETED"},
    ],
}


def test_added_to_milestone_filter():
    results = added_to_milestone("9.3", "2026-08-01", ITEMS, TIMELINES)
    assert len(results) == 1
    assert results[0]["number"] == 1
    assert results[0]["assignees"] == ["inespot"]


def test_added_to_all_milestone():
    results = added_to_milestone("all", "2026-08-01", ITEMS, TIMELINES)
    assert len(results) == 1  # only I_1 was milestoned after since date


def test_added_before_window_excluded():
    results = added_to_milestone("9.4", "2026-08-01", ITEMS, TIMELINES)
    assert len(results) == 0  # I_2 was milestoned in July


def test_completed_in_milestone():
    results = completed_in_window("9.4", "2026-08-01", ITEMS, TIMELINES)
    assert len(results) == 1
    assert results[0]["number"] == 2
    assert results[0]["assignees"] == ["samxbr"]


def test_completed_all_milestones():
    results = completed_in_window("all", "2026-08-01", ITEMS, TIMELINES)
    assert len(results) == 2


def test_completed_excludes_not_planned():
    items = {**ITEMS, "I_4": {"id": "I_4", "number": 4, "title": "D", "url": "", "milestone": None, "state": "CLOSED"}}
    timelines = {**TIMELINES, "I_4": [
        {"kind": "closed", "at": "2026-08-14T00:00:00Z", "from_": None, "to": "NOT_PLANNED"},
    ]}
    results = completed_in_window("all", "2026-08-01", items, timelines)
    # I_4 is NOT_PLANNED, should not appear
    assert all(r["number"] != 4 for r in results)


def test_currently_in_progress_uses_live_status_and_since_date():
    items = {
        "I_wip": {
            "id": "I_wip",
            "number": 10,
            "title": "Working",
            "url": "https://example.com/10",
            "milestone": {"title": "9.3"},
            "project_status": "In Progress",
            "assignees": ["alice"],
            "updatedAt": "2026-08-15T00:00:00Z",
        },
        "I_todo": {
            "id": "I_todo",
            "number": 11,
            "title": "Later",
            "url": "https://example.com/11",
            "milestone": {"title": "9.3"},
            "project_status": "Todo",
            "assignees": [],
            "updatedAt": "2026-08-15T00:00:00Z",
        },
        "I_other": {
            "id": "I_other",
            "number": 12,
            "title": "Other milestone",
            "url": "https://example.com/12",
            "milestone": {"title": "9.4"},
            "project_status": "In Progress",
            "assignees": ["bob"],
            "updatedAt": "2026-08-15T00:00:00Z",
        },
    }
    timelines = {
        "I_wip": [
            {
                "kind": "project_v2_status_changed",
                "at": "2026-08-01T12:00:00Z",
                "from_": "Todo",
                "to": "In Progress",
            },
            {
                "kind": "project_v2_status_changed",
                "at": "2026-08-05T12:00:00Z",
                "from_": "In Progress",
                "to": "Todo",
            },
            {
                "kind": "project_v2_status_changed",
                "at": "2026-08-10T12:00:00Z",
                "from_": "Todo",
                "to": "In progress",  # casing variant
            },
        ],
        "I_todo": [],
        "I_other": [
            {
                "kind": "project_v2_status_changed",
                "at": "2026-08-03T00:00:00Z",
                "from_": "Todo",
                "to": "In Progress",
            },
        ],
    }

    results = currently_in_progress("9.3", items, timelines)
    assert len(results) == 1
    assert results[0]["number"] == 10
    assert results[0]["assignees"] == ["alice"]
    assert results[0]["at"] == "2026-08-10T12:00:00Z"
    assert results[0]["url"] == "https://example.com/10"


def test_currently_in_progress_all_milestones():
    items = {
        "I_a": {
            "id": "I_a",
            "number": 1,
            "title": "A",
            "url": "",
            "milestone": {"title": "9.3"},
            "project_status": "In Progress",
            "assignees": [],
            "updatedAt": "2026-08-01T00:00:00Z",
        },
        "I_b": {
            "id": "I_b",
            "number": 2,
            "title": "B",
            "url": "",
            "milestone": {"title": "9.4"},
            "project_status": "In Progress",
            "assignees": [],
            "updatedAt": "2026-08-02T00:00:00Z",
        },
    }
    timelines = {"I_a": [], "I_b": []}
    results = currently_in_progress("all", items, timelines)
    assert [r["number"] for r in results] == [1, 2]
    # Falls back to updatedAt when no status events
    assert results[0]["at"] == "2026-08-01T00:00:00Z"
