"""Compare a proposal against a base (live data or a snapshot).

Usage::

    from core import diff as core_diff
    changes = core_diff.compute(p_items, p_fields, b_items, b_fields)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class FieldChange:
    issue_id: str
    number: int
    title: str
    url: str
    field: str
    base_value: Any
    proposal_value: Any


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
    return sorted(changes, key=lambda c: (c.number, c.field))
