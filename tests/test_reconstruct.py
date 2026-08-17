"""Tests for core.reconstruct — pure, no network."""

from core.reconstruct import state_at, is_completed, IssueState

ISSUE = {"id": "I_1", "number": 1, "title": "Test", "url": "", "state": "OPEN",
         "stateReason": None, "createdAt": "2026-01-01T00:00:00Z", "closedAt": None,
         "milestone": None, "assignees": [], "labels": [], "parent": None, "updatedAt": ""}


def test_empty_events_gives_open_state():
    s = state_at(ISSUE, [], "2026-08-01T00:00:00Z")
    assert s.open
    assert s.milestone is None
    assert s.assignees == []


def test_milestoned_then_demilestoned():
    events = [
        {"kind": "milestoned", "at": "2026-02-01T00:00:00Z", "from_": None, "to": "9.3"},
        {"kind": "demilestoned", "at": "2026-03-01T00:00:00Z", "from_": None, "to": "9.3"},
    ]
    s = state_at(ISSUE, events, "2026-02-15T00:00:00Z")
    assert s.milestone == "9.3"
    s2 = state_at(ISSUE, events, "2026-03-15T00:00:00Z")
    assert s2.milestone is None


def test_closed_completed():
    events = [
        {"kind": "closed", "at": "2026-04-01T00:00:00Z", "from_": None, "to": "COMPLETED"},
    ]
    s = state_at(ISSUE, events, "2026-04-02T00:00:00Z")
    assert not s.open
    assert s.close_reason == "COMPLETED"
    assert is_completed(s)


def test_closed_then_reopened():
    events = [
        {"kind": "closed", "at": "2026-04-01T00:00:00Z", "from_": None, "to": "COMPLETED"},
        {"kind": "reopened", "at": "2026-04-10T00:00:00Z", "from_": None, "to": None},
    ]
    before = state_at(ISSUE, events, "2026-04-05T00:00:00Z")
    assert is_completed(before)
    after = state_at(ISSUE, events, "2026-04-15T00:00:00Z")
    assert after.open
    assert not is_completed(after)


def test_events_after_query_date_ignored():
    events = [
        {"kind": "milestoned", "at": "2026-09-01T00:00:00Z", "from_": None, "to": "9.4"},
    ]
    s = state_at(ISSUE, events, "2026-08-01T00:00:00Z")
    assert s.milestone is None


def test_assignees_accumulate_and_remove():
    events = [
        {"kind": "assigned", "at": "2026-01-10T00:00:00Z", "from_": None, "to": "alice"},
        {"kind": "assigned", "at": "2026-01-11T00:00:00Z", "from_": None, "to": "bob"},
        {"kind": "unassigned", "at": "2026-01-12T00:00:00Z", "from_": None, "to": "alice"},
    ]
    s = state_at(ISSUE, events, "2026-01-20T00:00:00Z")
    assert s.assignees == ["bob"]


def test_labels():
    events = [
        {"kind": "labeled", "at": "2026-01-05T00:00:00Z", "from_": None, "to": "bug"},
        {"kind": "labeled", "at": "2026-01-06T00:00:00Z", "from_": None, "to": "team:dist"},
        {"kind": "unlabeled", "at": "2026-01-07T00:00:00Z", "from_": None, "to": "bug"},
    ]
    s = state_at(ISSUE, events, "2026-01-10T00:00:00Z")
    assert s.labels == ["team:dist"]


def test_project_status_changes():
    events = [
        {"kind": "project_v2_status_changed", "at": "2026-02-01T00:00:00Z",
         "from_": "Todo", "to": "In Progress"},
        {"kind": "project_v2_status_changed", "at": "2026-02-10T00:00:00Z",
         "from_": "In Progress", "to": "Done"},
    ]
    s = state_at(ISSUE, events, "2026-02-05T00:00:00Z")
    assert s.project_status == "In Progress"
    s2 = state_at(ISSUE, events, "2026-02-15T00:00:00Z")
    assert s2.project_status == "Done"
