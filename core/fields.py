"""Determine a ProjectV2 field value at a point in time.

Because GitHub stores no history for project field values, we reconstruct
using a combination of:

  1. Snapshots: each snapshot records every field value with its updatedAt.
     Two consecutive snapshots where updatedAt falls between them pin down
     the exact change timestamp for that field.
  2. Live field values from the most recent crawl, with their updatedAt.

The four cases, in precedence order:

  a. date >= a snapshot's captured_at AND that snapshot has the value
       => exact (as of that snapshot, it was this value)
  b. date >= live updatedAt
       => the current value has held at least since updatedAt; exact
  c. a later snapshot's updatedAt for this field falls *after* date
       => the value at the earlier snapshot is still correct; exact
  d. none of the above (date predates all snapshots and updatedAt)
       => use the oldest known value; confidence = "assumed"

Returns (value, confidence) where confidence is "exact" or "assumed".
"""

from __future__ import annotations

from typing import Any

from core import store


def value_at(
    project_id: str,
    issue_id: str,
    field_name: str,
    date: str,                      # ISO-8601 date string YYYY-MM-DD
    live_field_values: dict[str, Any],  # {issue_id: {field_name: {value, updatedAt}}}
    snapshots: dict[str, dict[str, Any]] | None = None,
) -> tuple[Any, str]:
    """Return (value, confidence) for a field at a given date.

    `live_field_values` comes from core.timeline.load()'s field_values output.
    `snapshots` maps label -> snapshot dict; if None, loaded from disk.
    """
    if snapshots is None:
        labels = store.list_snapshots(project_id)
        snapshots = {
            label: store.read_snapshot(project_id, label)
            for label in labels
            if store.read_snapshot(project_id, label)
        }

    # Sort snapshots by label (which is a date string, so lexicographic = chronological).
    sorted_snaps = sorted(snapshots.items())

    # Build a list of (captured_at, value, field_updated_at) from snapshots.
    snap_entries: list[tuple[str, Any, str]] = []
    for label, snap in sorted_snaps:
        if snap is None:
            continue
        captured_at = snap.get("captured_at", label)[:10]  # normalise to date
        items = snap.get("items", {})
        issue_snap = items.get(issue_id)
        if issue_snap is None:
            continue
        fields = issue_snap.get("fields", {})
        entry = fields.get(field_name)
        if entry is None:
            continue
        snap_entries.append((captured_at, entry["value"], entry.get("updatedAt", "")))

    live_entry = (live_field_values.get(issue_id) or {}).get(field_name)
    live_value = live_entry["value"] if live_entry else None
    live_updated_at = (live_entry.get("updatedAt", "") if live_entry else "")[:10]

    # Case b: if date is on or after the live updatedAt, the live value is exact.
    if live_updated_at and date >= live_updated_at:
        return live_value, "exact"

    # Work backwards through snapshot entries.
    # Find the latest snapshot whose captured_at <= date.
    candidates = [(cap, val, upd) for cap, val, upd in snap_entries if cap <= date]
    if candidates:
        # The latest one wins.
        cap, val, upd = candidates[-1]
        # Case c: is there a later snapshot whose field_updated_at > date?
        # If so, the field did not change in that interval; val is still correct.
        later = [(c2, v2, u2) for c2, v2, u2 in snap_entries if c2 > cap]
        for c2, v2, u2 in later:
            if u2[:10] <= date:
                # The field changed before or on `date` in this interval; v2 is correct.
                # (We only reach here if c2 > date, so c2 > date >= u2, meaning the
                # change happened before our query date but after the earlier snapshot.)
                val = v2
                cap = c2
            # If u2[:10] > date, the field changed after our query date; ignore.
        return val, "exact"

    # Case d: date predates all snapshots. Use the oldest snapshot value or live value.
    if snap_entries:
        return snap_entries[0][1], "assumed"
    if live_value is not None:
        return live_value, "assumed"

    return None, "assumed"
