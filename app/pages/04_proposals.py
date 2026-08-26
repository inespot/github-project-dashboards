"""Proposals page — create, view, edit, and compare roadmap proposals."""

from __future__ import annotations

from typing import Any

import solara

from app import state
from app.components.empty_state import NoProjectSelected
from core import diff as core_diff
from core import people, proposals as proposals_mod, store
from core.diff import ASSIGNEES_FIELD


# ---------------------------------------------------------------------------
# Helpers shared with the roadmaps page
# ---------------------------------------------------------------------------

def _snap_to_items_and_fields(snap: dict) -> tuple[dict, dict]:
    """Convert snapshot/proposal JSON → (items, field_values)."""
    items: dict[str, Any] = {}
    field_values: dict[str, Any] = {}
    for issue_id, entry in snap.get("items", {}).items():
        fields = entry.get("fields", {})
        items[issue_id] = {
            "number": entry.get("number"),
            "title": entry.get("title", ""),
            "url": entry.get("url", ""),
            "state": entry.get("state", "OPEN"),
            "stateReason": entry.get("stateReason"),
            "milestone": _milestone_from_fields(fields),
            "project_status": _status_from_fields(fields),
            "assignees": (
                list(entry.get("assignees") or [])
                if "assignees" in entry
                else None
            ),
            "parent": None,
        }
        field_values[issue_id] = fields
    return items, field_values


def _milestone_from_fields(fields: dict[str, Any]) -> dict[str, Any] | None:
    for name, entry in fields.items():
        if name.lower() == "milestone" and entry.get("value"):
            return {"title": str(entry["value"])}
    return None


def _status_from_fields(fields: dict[str, Any]) -> str | None:
    for name, entry in fields.items():
        if name.lower() == "status" and entry.get("value"):
            return str(entry["value"])
    return None


def _live_to_snap_items(live_data: dict) -> dict[str, Any]:
    """Convert live project data → snapshot items dict suitable for writing."""
    result: dict[str, Any] = {}
    for issue_id, item in live_data["items"].items():
        fv = live_data["field_values"].get(issue_id) or {}
        result[issue_id] = {
            "number": item.get("number"),
            "title": item.get("title"),
            "url": item.get("url"),
            "state": item.get("state"),
            "stateReason": item.get("stateReason"),
            "assignees": list(item.get("assignees") or []),
            "fields": {
                fname: {
                    "value": entry["value"],
                    "updatedAt": entry.get("updatedAt", ""),
                }
                for fname, entry in fv.items()
            },
        }
    return result


def _load_base(
    project_id: str, base: str, live_data: dict | None
) -> tuple[dict, dict] | None:
    """Return (items, field_values) for the base of a proposal, or None."""
    if base == "current":
        if live_data is None:
            return None
        return live_data["items"], live_data["field_values"]
    snap = store.read_snapshot(project_id, base)
    if snap is not None:
        return _snap_to_items_and_fields(snap)
    return None


# ---------------------------------------------------------------------------
# New-proposal form
# ---------------------------------------------------------------------------

@solara.component
def _NewProposalForm(
    project_id: str,
    live_data,
    snapshot_labels: list[str],
    on_created,
):
    name, set_name = solara.use_state("")
    base_options = ["current"] + snapshot_labels
    base, set_base = solara.use_state("current")
    error, set_error = solara.use_state("")

    def create(*_):
        label = name.strip()
        if not label:
            set_error("Name is required.")
            return
        existing = store.list_proposals(project_id)
        if label in existing:
            set_error(f"A proposal named '{label}' already exists.")
            return
        if base == "current":
            if live_data is None:
                set_error("Live data not loaded. Visit the Roadmap page first to fetch it.")
                return
            snap_items = _live_to_snap_items(live_data)
        else:
            snap = store.read_snapshot(project_id, base)
            if snap is None:
                set_error(f"Snapshot '{base}' not found.")
                return
            snap_items = snap.get("items", {})

        proposal = {
            "name": label,
            "base": base,
            "created_at": store.now_iso(),
            "items": snap_items,
        }
        store.write_proposal(project_id, label, proposal)
        on_created(label)

    with solara.Card(title="New proposal", style="margin-bottom: 20px; max-width: 480px;"):
        with solara.Column(gap="12px"):
            solara.InputText(
                label="Proposal name",
                value=name,
                on_value=set_name,
                continuous_update=True,
            )
            solara.Select(
                label="Base (starting point)",
                value=base,
                values=base_options,
                on_value=set_base,
            )
            if error:
                solara.Text(
                    error,
                    style="color: var(--color-danger-fg, #d03b3b); font-size: 0.85rem;",
                )
            with solara.Row(gap="8px"):
                solara.Button("Create", color="primary", on_click=create)
                solara.Button("Cancel", text=True, on_click=lambda *_: on_created(None))


# ---------------------------------------------------------------------------
# Proposal card
# ---------------------------------------------------------------------------

@solara.component
def _ProposalCard(label: str, prop: dict, selected: bool, on_select, on_delete):
    name = prop.get("name", label)
    base = prop.get("base", "current")
    created_at = prop.get("created_at", "")[:16].replace("T", " ")
    border = (
        "2px solid var(--color-accent-fg)"
        if selected
        else "1px solid var(--color-border-default)"
    )

    def select(*_args):
        on_select(label)

    def delete(*_args):
        on_delete(label)

    # Card provides elevation/chrome; click is on an inner Button (Card
    # ignores on_click — same pattern as the projects list).
    with solara.v.Card(
        style_=(
            f"padding: 12px 16px; cursor: pointer; border: {border}; "
            "border-radius: 8px; margin: 0; min-width: 200px; max-width: 280px;"
        ),
        elevation=3 if selected else 1,
    ):
        with solara.Row(
            justify="space-between",
            style="align-items: flex-start; gap: 8px; width: 100%;",
        ):
            with solara.Button(
                label="",
                text=True,
                on_click=select,
                style=(
                    "text-transform: none; letter-spacing: normal; "
                    "justify-content: flex-start; padding: 0; height: auto; "
                    "min-width: 0; flex: 1;"
                ),
            ):
                with solara.Column(gap="2px", style="min-width: 0; text-align: left;"):
                    solara.Text(name, style="font-weight: 600; font-size: 0.95rem;")
                    solara.Text(
                        f"Base: {base}",
                        style="font-size: 0.78rem; color: var(--color-fg-muted);",
                    )
                    if created_at:
                        solara.Text(
                            f"{created_at} UTC",
                            style="font-size: 0.75rem; color: var(--color-fg-muted);",
                        )
            solara.Button(
                "🗑",
                text=True,
                on_click=delete,
                style=(
                    "color: var(--color-danger-fg, #d03b3b); "
                    "min-width: 0; padding: 2px 4px; flex-shrink: 0;"
                ),
            )


# ---------------------------------------------------------------------------
# Diff view
# ---------------------------------------------------------------------------

@solara.component
def _DiffView(
    project_id: str,
    proposal_data: dict,
    live_data,
    start_field: str,
    end_field: str,
    estimate_field: str,
):
    base = proposal_data.get("base", "current")
    p_items, p_fields = _snap_to_items_and_fields(proposal_data)
    base_result = _load_base(project_id, base, live_data)

    if base_result is None:
        msg = (
            "Live data not loaded. Visit the Roadmap page first."
            if base == "current"
            else f"Base snapshot '{base}' not found."
        )
        solara.Text(msg, style="color: var(--color-fg-muted); font-style: italic;")
        return

    b_items, b_fields = base_result
    columns = [
        f for f in [start_field, end_field, estimate_field, ASSIGNEES_FIELD] if f
    ]
    rows = core_diff.issue_rows(p_items, p_fields, b_items, b_fields, columns)

    if not rows:
        solara.Text(
            "No differences — this proposal matches the base.",
            style="color: var(--color-fg-muted); font-style: italic; padding: 8px 0;",
        )
        return

    n = len(rows)
    field_change_count = sum(
        sum(1 for c in row.cells.values() if c.changed) for row in rows
    )
    solara.Text(
        f"{n} issue{'s' if n != 1 else ''} · {field_change_count} field change"
        f"{'s' if field_change_count != 1 else ''}",
        style="font-size: 0.85rem; color: var(--color-fg-muted); margin-bottom: 8px;",
    )

    _HDR = (
        "background: var(--color-canvas-subtle); padding: 6px 12px; "
        "border-radius: 6px 6px 0 0; border: 1px solid var(--color-border-default); "
        "font-size: 0.78rem; font-weight: 600; color: var(--color-fg-muted);"
    )
    _ROW = (
        "padding: 5px 12px; "
        "border-left: 1px solid var(--color-border-default); "
        "border-right: 1px solid var(--color-border-default); "
        "border-bottom: 1px solid var(--color-border-default); "
        "font-size: 0.82rem; align-items: center;"
    )
    _COL = "flex: 2; min-width: 110px;"
    _DANGER = "var(--color-danger-fg, #d03b3b)"

    def _esc(s: str) -> str:
        return (
            s.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    column_labels = {
        start_field: "Start Date",
        end_field: "End Date",
        estimate_field: "Estimate",
        ASSIGNEES_FIELD: "Assignee",
    }

    with solara.Column(gap="0px"):
        with solara.Row(style=_HDR):
            solara.HTML(
                tag="div",
                unsafe_innerHTML="Issue",
                style="flex: 3; min-width: 0;",
            )
            for col in columns:
                solara.HTML(
                    tag="div",
                    unsafe_innerHTML=_esc(column_labels.get(col, col)),
                    style=_COL,
                )

        for i, row in enumerate(rows):
            bg = (
                "var(--color-canvas-default)"
                if i % 2 == 0
                else "var(--color-canvas-subtle)"
            )
            br = "0 0 6px 6px" if i == n - 1 else "0"
            title = row.title[:50] + ("…" if len(row.title) > 50 else "")
            with solara.Row(style=f"background: {bg}; border-radius: {br}; {_ROW}"):
                solara.HTML(
                    tag="div",
                    unsafe_innerHTML=(
                        f"<a href='{_esc(row.url)}' target='_blank' "
                        f"style='color:var(--color-accent-fg);text-decoration:none;'>"
                        f"#{row.number}</a> {_esc(title)}"
                    ),
                    style=(
                        "flex: 3; min-width: 0; overflow: hidden; "
                        "white-space: nowrap; text-overflow: ellipsis;"
                    ),
                )
                for col in columns:
                    cell = row.cells.get(col) or core_diff.CellDisplay("—", False)
                    if cell.changed:
                        inner = (
                            f"{_esc(cell.before)}"
                            f" → "
                            f"<span style='color:{_DANGER};font-weight:600;'>"
                            f"{_esc(cell.after)}</span>"
                        )
                    else:
                        inner = (
                            f"<span style='color:var(--color-fg-default);'>"
                            f"{_esc(cell.text)}</span>"
                        )
                    solara.HTML(
                        tag="div",
                        unsafe_innerHTML=inner,
                        style=_COL,
                    )


# ---------------------------------------------------------------------------
# Edit view
# ---------------------------------------------------------------------------

@solara.component
def _EditView(
    project_id: str,
    label: str,
    proposal_data: dict,
    start_field: str,
    end_field: str,
    estimate_field: str,
    on_saved,
):
    p_items, p_fields = _snap_to_items_and_fields(proposal_data)
    edits, set_edits = solara.use_state({})  # {issue_id: {field: new_value}}

    def get_val(issue_id: str, field: str) -> str:
        if issue_id in edits and field in edits[issue_id]:
            return str(edits[issue_id][field])
        if field == ASSIGNEES_FIELD:
            assignees = (p_items.get(issue_id) or {}).get("assignees")
            return people.assignees_edit_value(assignees or [])
        fv = p_fields.get(issue_id, {})
        entry = fv.get(field, {})
        val = entry.get("value") if isinstance(entry, dict) else entry
        return str(val) if val is not None else ""

    def update(issue_id: str, field: str, value: str):
        set_edits(
            {**edits, issue_id: {**edits.get(issue_id, {}), field: value}}
        )

    def save(*_):
        new_items = dict(proposal_data.get("items", {}))
        for iid, field_edits in edits.items():
            if iid not in new_items:
                continue
            item = dict(new_items[iid])
            fields = dict(item.get("fields", {}))
            for fname, val in field_edits.items():
                if fname == ASSIGNEES_FIELD:
                    item["assignees"] = people.parse_assignee_input(val)
                    continue
                old = fields.get(fname, {})
                fields[fname] = {
                    **(old if isinstance(old, dict) else {}),
                    "value": val,
                    "updatedAt": store.now_iso(),
                }
            item["fields"] = fields
            new_items[iid] = item
        new_data = {**proposal_data, "items": new_items}
        store.write_proposal(project_id, label, new_data)
        on_saved(new_data)

    edit_fields = [f for f in [start_field, end_field, estimate_field] if f]
    edit_fields = [*edit_fields, ASSIGNEES_FIELD]
    sorted_items = sorted(
        (
            (iid, item)
            for iid, item in p_items.items()
            if proposals_mod.include_in_proposal_edit(
                item, p_fields.get(iid) or {}, end_field
            )
        ),
        key=lambda kv: kv[1].get("number", 0),
    )
    n = len(sorted_items)
    change_count = sum(len(v) for v in edits.values())

    _HDR = (
        "background: var(--color-canvas-subtle); padding: 6px 12px; "
        "border-radius: 6px 6px 0 0; border: 1px solid var(--color-border-default); "
        "font-size: 0.78rem; font-weight: 600; color: var(--color-fg-muted);"
    )
    _ROW = (
        "padding: 4px 12px; "
        "border-left: 1px solid var(--color-border-default); "
        "border-right: 1px solid var(--color-border-default); "
        "border-bottom: 1px solid var(--color-border-default); "
        "align-items: center; gap: 8px;"
    )

    with solara.Column(gap="8px"):
        with solara.Row(gap="8px", style="align-items: center; margin-bottom: 4px;"):
            solara.Button("💾 Save", color="primary", on_click=save)
            solara.Button("Cancel", text=True, on_click=lambda *_: on_saved(None))
            if change_count:
                solara.Text(
                    f"{change_count} pending change{'s' if change_count != 1 else ''}",
                    style="font-size: 0.82rem; color: var(--color-fg-muted);",
                )

        solara.Text(
            "Edit field values (Assignees: comma-separated names or GitHub logins). "
            "Showing incomplete issues and completed issues with an end date of today "
            "or later. Press Tab or Enter to apply a change, then Save.",
            style="font-size: 0.8rem; color: var(--color-fg-muted); margin-bottom: 8px;",
        )

        with solara.Column(gap="0px"):
            with solara.Row(style=_HDR):
                solara.HTML(
                    tag="div",
                    unsafe_innerHTML="Issue",
                    style="flex: 3; min-width: 0;",
                )
                for fname in edit_fields:
                    solara.HTML(
                        tag="div",
                        unsafe_innerHTML=fname,
                        style="flex: 2; min-width: 120px;",
                    )

            for i, (issue_id, item) in enumerate(sorted_items):
                bg = (
                    "var(--color-canvas-default)"
                    if i % 2 == 0
                    else "var(--color-canvas-subtle)"
                )
                br = "0 0 6px 6px" if i == n - 1 else "0"
                with solara.Row(
                    style=f"background: {bg}; border-radius: {br}; {_ROW}",
                ):
                    solara.HTML(
                        tag="div",
                        unsafe_innerHTML=(
                            f"<a href='{item.get('url', '')}' target='_blank' "
                            f"style='color:var(--color-accent-fg);text-decoration:none;'>"
                            f"#{item.get('number', '')}</a> "
                            f"{item.get('title', '')[:45]}"
                            f"{'…' if len(item.get('title', '')) > 45 else ''}"
                        ),
                        style=(
                            "flex: 3; overflow: hidden; white-space: nowrap; "
                            "min-width: 0; font-size: 0.82rem;"
                        ),
                    )
                    for fname in edit_fields:
                        solara.InputText(
                            label="",
                            value=get_val(issue_id, fname),
                            on_value=lambda v, iid=issue_id, fn=fname: update(iid, fn, v),
                            continuous_update=False,
                            style="flex: 2; min-width: 120px;",
                        )


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

@solara.component
def Page():
    project = state.current_project.value
    router = solara.use_router()

    # Page state — all hooks before any early return (SH101).
    selected_label, set_selected_label = solara.use_state(None)  # noqa: SH101
    creating, set_creating = solara.use_state(False)  # noqa: SH101
    editing, set_editing = solara.use_state(False)  # noqa: SH101
    # Increment to force re-read of the proposals list after mutations.
    version, set_version = solara.use_state(0)  # noqa: SH101

    if not project:
        NoProjectSelected()
        return

    project_id = project.get("project_id", "")
    config = project.get("config") or {}
    estimate_field = config.get("estimate_field", "")
    start_field = config.get("start_field", "")
    end_field = config.get("end_field", "")
    live_data = state.project_data.value

    _ = version  # referenced so Solara tracks it as a dependency
    proposals = store.list_proposals(project_id)
    snapshot_labels = store.list_snapshots(project_id)

    # --- Callbacks ---

    def on_select(label: str):
        set_selected_label(label)
        set_editing(False)
        set_creating(False)

    def on_delete(label: str):
        store.delete_proposal(project_id, label)
        if selected_label == label:
            set_selected_label(None)
            set_editing(False)
        set_version(version + 1)

    def on_created(label):
        set_creating(False)
        if label:
            set_version(version + 1)
            set_selected_label(label)

    def on_saved(new_data):
        set_editing(False)
        if new_data is not None:
            set_version(version + 1)

    def view_in_roadmap(*_args):
        if not selected_label:
            return
        state.roadmap_view.value = selected_label
        state.selected_milestone.value = "all"
        router.push("/roadmaps")

    # --- Render ---

    with solara.Column(style="padding: 24px; width: 100%; min-width: 0;"):
        # Title + "New proposal" button
        with solara.Row(
            justify="space-between",
            style="align-items: center; margin-bottom: 16px;",
        ):
            solara.Markdown(f"## Proposals — {project.get('title', '')}")
            if not creating:
                solara.Button(
                    "New proposal",
                    outlined=True,
                    on_click=lambda *_: (
                        set_creating(True),
                        set_selected_label(None),
                        set_editing(False),
                    ),
                )

        # New-proposal form
        if creating:
            _NewProposalForm(project_id, live_data, snapshot_labels, on_created)

        # Empty state
        if not proposals and not creating:
            with solara.Column(
                style="align-items: center; padding: 48px 0; gap: 8px;",
            ):
                solara.Text(
                    "No proposals yet.",
                    style="font-size: 1rem; font-weight: 600; color: var(--color-fg-default);",
                )
                solara.Text(
                    "Create one from the current roadmap or a snapshot.",
                    style="font-size: 0.88rem; color: var(--color-fg-muted);",
                )

        # Proposal cards
        if proposals:
            with solara.Row(
                gap="12px",
                style="flex-wrap: wrap; margin-bottom: 20px; align-items: flex-start;",
            ):
                for lbl in proposals:
                    prop = store.read_proposal(project_id, lbl) or {"name": lbl}
                    _ProposalCard(
                        label=lbl,
                        prop=prop,
                        selected=lbl == selected_label,
                        on_select=on_select,
                        on_delete=on_delete,
                    )

        # Selected proposal — detail + diff
        if selected_label and not editing:
            proposal_data = store.read_proposal(project_id, selected_label)
            if proposal_data:
                pname = proposal_data.get("name", selected_label)
                pbase = proposal_data.get("base", "current")
                pcreated = proposal_data.get("created_at", "")[:16].replace("T", " ")

                with solara.Card(title=pname, style="margin-top: 8px;"):
                    solara.Text(
                        f"Base: {pbase}  ·  Created: {pcreated} UTC",
                        style="font-size: 0.82rem; color: var(--color-fg-muted);",
                    )
                    solara.HTML(tag="div", style="height: 12px;")

                    with solara.Row(gap="8px", style="margin-bottom: 16px;"):
                        if start_field and end_field:
                            solara.Button(
                                "🗺 View in Roadmap",
                                outlined=True,
                                on_click=view_in_roadmap,
                            )
                        solara.Button(
                            "✏ Edit fields",
                            outlined=True,
                            on_click=lambda *_: set_editing(True),
                        )

                    solara.Markdown("**Changes vs. base**")
                    _DiffView(
                        project_id,
                        proposal_data,
                        live_data,
                        start_field,
                        end_field,
                        estimate_field,
                    )

        # Edit view
        if selected_label and editing:
            proposal_data = store.read_proposal(project_id, selected_label)
            if proposal_data:
                _EditView(
                    project_id=project_id,
                    label=selected_label,
                    proposal_data=proposal_data,
                    start_field=start_field,
                    end_field=end_field,
                    estimate_field=estimate_field,
                    on_saved=on_saved,
                )
