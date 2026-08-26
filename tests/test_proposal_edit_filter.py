"""Tests for proposal edit filtering helpers."""

from datetime import date

from core.proposals import include_in_proposal_edit


def test_include_incomplete_even_with_past_end():
    item = {"stateReason": None, "project_status": "In Progress"}
    fields = {"Target End Date": {"value": "2020-01-01"}}
    assert include_in_proposal_edit(
        item, fields, "Target End Date", today=date(2026, 8, 26)
    )


def test_exclude_completed_with_past_end():
    item = {"stateReason": "COMPLETED", "project_status": "Done"}
    fields = {"Target End Date": {"value": "2026-08-01"}}
    assert not include_in_proposal_edit(
        item, fields, "Target End Date", today=date(2026, 8, 26)
    )


def test_include_completed_with_today_or_future_end():
    item = {"stateReason": "COMPLETED", "project_status": "Done"}
    fields = {"Target End Date": {"value": "2026-08-26"}}
    assert include_in_proposal_edit(
        item, fields, "Target End Date", today=date(2026, 8, 26)
    )
    fields = {"Target End Date": {"value": "2026-09-01"}}
    assert include_in_proposal_edit(
        item, fields, "Target End Date", today=date(2026, 8, 26)
    )


def test_exclude_completed_without_end_date():
    item = {"stateReason": None, "project_status": "Done"}
    assert not include_in_proposal_edit(
        item, {}, "Target End Date", today=date(2026, 8, 26)
    )
