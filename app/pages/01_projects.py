"""Projects page — project picker and connect-a-project flow."""

from __future__ import annotations

from pathlib import Path

import threading
from typing import Any

import solara
import solara.lab

from app import state
from core import projects as proj_mod, store

_HAPPY_STICKMAN = Path(__file__).parent.parent.parent / "images" / "happy-stickman.png"


@solara.component
def Page():
    # Connect-new-project form state (local)
    projects_version, set_projects_version = solara.use_state(0)
    org_input, set_org_input = solara.use_state("elastic")
    number_input, set_number_input = solara.use_state("")
    connecting, set_connecting = solara.use_state(False)
    connect_error, set_connect_error = solara.use_state("")
    connect_fields, set_connect_fields = solara.use_state(None)
    estimate_field, set_estimate_field = solara.use_state("")
    start_field, set_start_field = solara.use_state("")
    end_field, set_end_field = solara.use_state("")

    saved_projects = store.list_projects()

    # Center the page vertically and horizontally.
    with solara.Column(
        style=(
            "min-height: 10vh; align-items: center; justify-content: center; "
            "padding: 32px 24px;"
        ),
    ):
        solara.Text(
            "Welcome to the GitHub project dashboards app!",
             style="color: var(--color-fg-muted); text-align: center; white-space: pre-line;",
        )
        solara.Image(_HAPPY_STICKMAN, width="160px")
        with solara.Column(style="width: 100%; max-width: 640px; gap: 0px;"):
            solara.Text(
                "Select a project to open, or connect a new one.",
                style="color: var(--color-fg-muted); margin-bottom: 24px; text-align: center;",
            )

            # --- Existing projects ---
            if saved_projects:
                solara.Markdown("#### Your Projects")
                solara.Markdown("<div style='height: 10px;'></div>")
                for p in saved_projects:
                    _ProjectCard(p, lambda: set_projects_version(lambda v: v + 1))
                solara.HTML(tag="hr", style="margin: 24px 0; border-color: var(--color-border);")

            # --- Connect a new project ---
            solara.Markdown("#### Connect a new project")
            solara.Markdown("<div style='height: 20px;'></div>")
            with solara.Row(gap="12px", style="align-items: flex-end;"):
                solara.InputText(
                    label="GitHub org",
                    value=org_input,
                    on_value=set_org_input,
                )
                solara.InputText(
                    label="Project number",
                    value=number_input,
                    on_value=set_number_input,
                )
                solara.Button(
                    "Discover fields",
                    disabled=connecting or not number_input.strip(),
                    on_click=lambda: _discover_fields(
                        org_input.strip(), number_input.strip(),
                        set_connecting, set_connect_error, set_connect_fields,
                        set_estimate_field, set_start_field, set_end_field,
                    ),
                )

            if connecting:
                solara.ProgressLinear(True)

            if connect_error:
                solara.Text(connect_error, style="color: var(--color-critical, #d03b3b);")

            if connect_fields is not None:
                _FieldMapping(
                    org=org_input.strip(),
                    number=int(number_input.strip()),
                    fields=connect_fields,
                    estimate_field=estimate_field,
                    start_field=start_field,
                    end_field=end_field,
                    set_estimate_field=set_estimate_field,
                    set_start_field=set_start_field,
                    set_end_field=set_end_field,
                    on_saved=lambda: set_connect_fields(None),
                )


@solara.component
def _ProjectCard(p: dict[str, Any], on_deleted):
    router = solara.use_router()
    current = state.current_project.value
    is_selected = current is not None and current.get("project_id") == p["id"]
    deleting, set_deleting = solara.use_state(False)
    delete_error, set_delete_error = solara.use_state("")

    def open_project(*_):  # v.Btn calls handler(widget, event, data) — accept and ignore
        config = store.read_config(p["id"]) or {}
        state.current_project.value = {
            "project_id": p["id"],
            "title": p.get("title", p["id"]),
            "org": p.get("org"),
            "number": p.get("number"),
            "config": config,
        }
        state.project_data.value = None
        state.error.value = None
        state.selected_milestone.value = "all"
        state.contributors_count.value = "1"
        state.clear_overview_cache()
        router.push("/overview")

    def delete_project(*_):
        set_deleting(True)
        set_delete_error("")
        try:
            if is_selected:
                state.clear_project()
            store.delete_project(p["id"])
            on_deleted()
        except Exception as e:
            set_delete_error(f"Failed to delete project: {e}")
        finally:
            set_deleting(False)

    if is_selected:
        card_style = (
            "margin-bottom: 8px; "
            "border-left: 3px solid rgba(99,108,118,0.55) !important; "
            "background: rgba(99,108,118,0.12);"
        )
    else:
        card_style = "margin-bottom: 8px;"

    title_style = (
        "font-weight: 600; color: var(--color-fg-default);"
        if is_selected
        else "font-weight: 600;"
    )

    with solara.v.Card(style_=card_style, outlined=True, elevation=0):
        with solara.Row(
            justify="space-between",
            style="align-items: center; width: 100%; padding: 6px 8px 6px 0;",
        ):
            with solara.Button(
                label="",
                on_click=open_project,
                text=True,
                style=(
                    "text-transform: none; justify-content: flex-start; "
                    "padding: 12px 16px; height: auto; width: 100%; flex: 1;"
                ),
            ):
                with solara.Row(
                    justify="space-between",
                    style="align-items: center; width: 100%; flex: 1;",
                ):
                    solara.Text(p.get("title", p["id"]), style=title_style)
                    solara.Text(
                        f"{p.get('org')}/projects/{p.get('number')}",
                        style="font-size: 0.82rem; color: var(--color-fg-muted);",
                    )
            solara.Button(
                label="",
                icon_name="mdi-delete-outline",
                on_click=delete_project,
                disabled=deleting,
                text=True,
                style="min-width: 36px; width: 36px; padding: 0 8px;",
            )
        if delete_error:
            solara.Text(
                delete_error,
                style="color: var(--color-critical, #d03b3b); padding: 0 16px 12px 16px;",
            )


@solara.component
def _FieldMapping(
    org, number, fields,
    estimate_field, start_field, end_field,
    set_estimate_field, set_start_field, set_end_field,
    on_saved,
):
    from core.projects import date_fields, number_fields

    all_names = [f["name"] for f in fields]
    num_names = number_fields(fields) or all_names
    date_names = date_fields(fields) or all_names

    saving, set_saving = solara.use_state(False)
    save_error, set_save_error = solara.use_state("")

    with solara.Column(
        style=(
            "border: 1px solid var(--color-border); border-radius: 6px; "
            "padding: 16px; background: var(--color-canvas-subtle); margin-top: 8px;"
        ),
        gap="12px",
    ):
        solara.Text("Map project fields", style="font-weight: 600;")

        solara.Select(
            label="Estimate field (Number)",
            value=estimate_field or (num_names[0] if num_names else ""),
            values=num_names,
            on_value=set_estimate_field,
        )
        solara.Select(
            label="Start date field",
            value=start_field or (date_names[0] if date_names else ""),
            values=date_names,
            on_value=set_start_field,
        )
        solara.Select(
            label="End / target date field",
            value=end_field or (date_names[0] if date_names else ""),
            values=date_names,
            on_value=set_end_field,
        )

        if save_error:
            solara.Text(save_error, style="color: var(--color-critical, #d03b3b);")

        solara.Button(
            "Save and open",
            disabled=saving or not estimate_field or not start_field or not end_field,
            on_click=lambda: _save_and_open(
                org, number, fields,
                estimate_field, start_field, end_field,
                set_saving, set_save_error, on_saved,
            ),
            color="primary",
        )


# ---------------------------------------------------------------------------
# Async actions (run in threads to avoid blocking the UI)
# ---------------------------------------------------------------------------

def _discover_fields(org, number_str, set_connecting, set_error, set_fields,
                     set_est, set_start, set_end):
    set_connecting(True)
    set_error("")
    set_fields(None)

    def run():
        try:
            number = int(number_str)
            proj = proj_mod.fetch_project(org, number)
            fields = proj["fields"]
            date_f = proj_mod.date_fields(fields)
            num_f = proj_mod.number_fields(fields)
            set_est(num_f[0] if num_f else "")
            set_start(date_f[0] if date_f else "")
            set_end(date_f[1] if len(date_f) > 1 else (date_f[0] if date_f else ""))
            set_fields(fields)
        except (ValueError, TypeError):
            set_error(f"'{number_str}' is not a valid project number.")
        except PermissionError as e:
            set_error(str(e))
        except Exception as e:
            set_error(f"Failed to fetch project: {e}")
        finally:
            set_connecting(False)

    threading.Thread(target=run, daemon=True).start()


def _save_and_open(org, number, fields, est_field, start_field, end_field,
                   set_saving, set_error, on_saved):
    set_saving(True)
    set_error("")

    def run():
        try:
            proj = proj_mod.fetch_project(org, number)
            project_id = proj_mod.project_id_slug(org, number)

            config = {
                "org": org,
                "number": number,
                "title": proj["title"],
                "estimate_field": est_field,
                "start_field": start_field,
                "end_field": end_field,
                "fields": fields,
            }
            store.write_config(project_id, config)
            store.save_project({
                "id": project_id,
                "org": org,
                "number": number,
                "title": proj["title"],
            })

            state.current_project.value = {
                "project_id": project_id,
                "title": proj["title"],
                "org": org,
                "number": number,
                "config": config,
            }
            state.project_data.value = None
            state.error.value = None
            state.selected_milestone.value = "all"
            state.contributors_count.value = "1"
            state.clear_overview_cache()
            on_saved()
            # Signal navigation — router.push must run in the render context,
            # not from a background thread.
            state.pending_route.value = "/overview"
        except Exception as e:
            set_error(f"Failed to save: {e}")
        finally:
            set_saving(False)

    threading.Thread(target=run, daemon=True).start()
