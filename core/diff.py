"""Compare a proposal against a base (live data or a snapshot).

Usage::

    from core import diff as core_diff
    changes = core_diff.compute(p_items, p_fields, b_items, b_fields)
    rows = core_diff.issue_rows(p_items, p_fields, b_items, b_fields, columns)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core import people

ASSIGNEES_FIELD = "Assignees"


@dataclass
class FieldChange:
    issue_id: str
    number: int
    title: str
    url: str
    field: str
    base_value: Any
    proposal_value: Any


@dataclass
class CellDisplay:
    """How one column should render for an issue."""

    text: str
    changed: bool
    before: str = ""
    after: str = ""


@dataclass
class IssueDiffRow:
    issue_id: str
    number: int
    title: str
    url: str
    cells: dict[str, CellDisplay] = field(default_factory=dict)
    other_changes: list[FieldChange] = field(default_factory=list)


def compute(
    proposal_items: dict[str, Any],
    proposal_fields: dict[str, Any],
    base_items: dict[str, Any],
    base_fields: dict[str, Any],
) -> list[FieldChange]:
    """Return field-level differences between proposal and base, sorted by issue number."""
    changes: list[FieldChange] = []
    for issue_id, p_item in proposal_items.items():
        p_fv = proposal_fields.get(issue_id, {})
        b_fv = base_fields.get(issue_id, {})
        for field_name, p_entry in p_fv.items():
            if field_name.lower() == ASSIGNEES_FIELD.lower():
                # Assignees are compared from item.assignees below.
                continue
            p_val = p_entry.get("value") if isinstance(p_entry, dict) else p_entry
            b_entry = b_fv.get(field_name, {})
            b_val = b_entry.get("value") if isinstance(b_entry, dict) else None
            if p_val != b_val:
                changes.append(
                    FieldChange(
                        issue_id=issue_id,
                        number=p_item.get("number", 0),
                        title=p_item.get("title", ""),
                        url=p_item.get("url", ""),
                        field=field_name,
                        base_value=b_val,
                        proposal_value=p_val,
                    )
                )

        p_assignees = p_item.get("assignees")
        # Legacy proposals/snapshots without an assignees key skip this comparison.
        if p_assignees is None:
            continue
        b_item = base_items.get(issue_id) or {}
        b_assignees = list(b_item.get("assignees") or [])
        if sorted(p_assignees) != sorted(b_assignees):
            changes.append(
                FieldChange(
                    issue_id=issue_id,
                    number=p_item.get("number", 0),
                    title=p_item.get("title", ""),
                    url=p_item.get("url", ""),
                    field=ASSIGNEES_FIELD,
                    base_value=people.format_assignees(b_assignees),
                    proposal_value=people.format_assignees(p_assignees),
                )
            )

    return sorted(changes, key=lambda c: (c.number, c.field))


def issue_rows(
    proposal_items: dict[str, Any],
    proposal_fields: dict[str, Any],
    base_items: dict[str, Any],
    base_fields: dict[str, Any],
    columns: list[str],
) -> list[IssueDiffRow]:
    """One row per issue that has changes, with display cells for ``columns``.

    Changed cells use ``old → new``; unchanged cells show the proposal value.
    Field changes outside ``columns`` are attached as ``other_changes``.
    """
    columns = [c for c in columns if c]
    changes = compute(proposal_items, proposal_fields, base_items, base_fields)
    if not changes:
        return []

    by_issue: dict[str, list[FieldChange]] = {}
    for ch in changes:
        by_issue.setdefault(ch.issue_id, []).append(ch)

    column_keys = {c.lower(): c for c in columns}
    rows: list[IssueDiffRow] = []

    for issue_id, issue_changes in by_issue.items():
        p_item = proposal_items.get(issue_id) or {}
        sample = issue_changes[0]
        changed_by_field = {ch.field: ch for ch in issue_changes}
        other = [
            ch
            for ch in issue_changes
            if ch.field.lower() not in column_keys
        ]

        cells: dict[str, CellDisplay] = {}
        any_column_change = False
        for col in columns:
            ch = _change_for_column(changed_by_field, col)
            if ch is not None:
                any_column_change = True
                before = _format_cell_value(col, ch.base_value)
                after = _format_cell_value(col, ch.proposal_value)
                cells[col] = CellDisplay(
                    text=f"{before} → {after}",
                    changed=True,
                    before=before,
                    after=after,
                )
            else:
                value = _proposal_column_value(
                    col, issue_id, p_item, proposal_fields
                )
                text = _format_cell_value(col, value)
                cells[col] = CellDisplay(
                    text=text,
                    changed=False,
                    before="",
                    after=text,
                )

        # Skip issues that only changed fields outside the table columns
        # (e.g. Status-only) — those would render as a sparse dash row.
        if not any_column_change:
            continue

        rows.append(
            IssueDiffRow(
                issue_id=issue_id,
                number=sample.number,
                title=sample.title,
                url=sample.url,
                cells=cells,
                other_changes=other,
            )
        )

    start_col = next((c for c in columns if "start" in c.lower()), None)

    def _row_sort_key(row: IssueDiffRow) -> tuple[str, int]:
        if start_col:
            cell = row.cells.get(start_col)
            # Prefer new (proposal) start date; missing dates sort last.
            date_key = (cell.after if cell else "") or ""
            if not date_key or date_key == "—":
                date_key = "9999-99-99"
        else:
            date_key = "9999-99-99"
        return (date_key, row.number)

    return sorted(rows, key=_row_sort_key)


def _change_for_column(
    changed_by_field: dict[str, FieldChange], column: str
) -> FieldChange | None:
    if column in changed_by_field:
        return changed_by_field[column]
    lower = column.lower()
    for name, ch in changed_by_field.items():
        if name.lower() == lower:
            return ch
    return None


def _proposal_column_value(
    column: str,
    issue_id: str,
    p_item: dict[str, Any],
    proposal_fields: dict[str, Any],
) -> Any:
    if column.lower() == ASSIGNEES_FIELD.lower():
        assignees = p_item.get("assignees")
        if assignees is None:
            return None
        return people.format_assignees(assignees)
    entry = (proposal_fields.get(issue_id) or {}).get(column, {})
    if isinstance(entry, dict):
        return entry.get("value")
    return entry


def _format_cell_value(column: str, value: Any) -> str:
    if value is None or value == "":
        return "—"
    if column.lower() == ASSIGNEES_FIELD.lower():
        if isinstance(value, list):
            return people.format_assignees(value)
        return str(value)
    return str(value)
