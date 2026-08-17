"""Tests for core.activity — pure, no network."""

from core.activity import added_to_milestone, completed_in_window, since_date

ITEMS = {
    "I_1": {"id": "I_1", "number": 1, "title": "Alpha", "url": "u1",
             "milestone": {"title": "9.3"}, "state": "OPEN"},
    "I_2": {"id": "I_2", "number": 2, "title": "Beta", "url": "u2",
             "milestone": {"title": "9.4"}, "state": "CLOSED"},
    "I_3": {"id": "I_3", "number": 3, "title": "Gamma", "url": "u3",
             "milestone": None, "state": "CLOSED"},
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
