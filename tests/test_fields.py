"""Tests for core.fields — pure, no network, no disk."""

from core.fields import value_at

ISSUE_ID = "I_1"
FIELD = "Estimate"

# live_field_values: the current live value, updated 2026-07-20
LIVE = {ISSUE_ID: {FIELD: {"value": 8, "updatedAt": "2026-07-20T00:00:00Z"}}}

# Snapshots: sparse
SNAPS = {
    "2026-07-01": {
        "captured_at": "2026-07-01T00:00:00Z",
        "items": {ISSUE_ID: {"fields": {FIELD: {"value": 3, "updatedAt": "2026-06-01T00:00:00Z"}}}},
    },
    "2026-08-01": {
        "captured_at": "2026-08-01T00:00:00Z",
        "items": {ISSUE_ID: {"fields": {FIELD: {"value": 8, "updatedAt": "2026-07-20T00:00:00Z"}}}},
    },
}


def val(date, live=LIVE, snaps=SNAPS):
    return value_at("proj", ISSUE_ID, FIELD, date, live, snaps)


def test_after_live_updated_at_is_exact():
    v, conf = val("2026-07-25")
    assert v == 8
    assert conf == "exact"


def test_after_august_snapshot_is_exact():
    v, conf = val("2026-08-10")
    assert v == 8
    assert conf == "exact"


def test_between_snapshots_change_pinpointed():
    # Between July-1 and Aug-1 snapshots.
    # Aug-1 snapshot's updatedAt for the field is 2026-07-20.
    # Querying 2026-07-25 (after the change): value should be 8.
    v, conf = val("2026-07-25")
    assert v == 8
    assert conf == "exact"


def test_before_change_within_interval():
    # Querying 2026-07-15 (before the change within the interval).
    # July-1 snapshot says 3; the field changed on Jul-20 per Aug-1 snapshot.
    # So on Jul-15, value should still be 3.
    v, conf = val("2026-07-15")
    assert v == 3
    assert conf == "exact"


def test_before_all_snapshots_is_assumed():
    v, conf = val("2026-05-01")
    assert conf == "assumed"


def test_no_snapshots_before_updated_at_is_assumed():
    v, conf = value_at("proj", ISSUE_ID, FIELD, "2026-01-01", LIVE, {})
    assert conf == "assumed"
    assert v == 8  # oldest known = live


def test_missing_issue_in_snapshot():
    v, conf = value_at("proj", "I_MISSING", FIELD, "2026-08-01", {}, SNAPS)
    assert v is None
    assert conf == "assumed"
