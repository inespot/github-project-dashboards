"""Overview page — burn-up chart, weighted progress, and activity lists."""

from __future__ import annotations

import threading
from datetime import date, timedelta
from typing import Any

import solara

from app import state
from app.components.charts import BurnupChart, ProgressBreakdown
from app.components.empty_state import NoProjectSelected
from app.components.selectors import MilestoneSelect, ActivityWindowSelect, ContributorsSelect
from core import activity as activity_mod, progress as progress_mod, reconstruct, series as series_mod, store
from core.time import utc_today, utc_today_iso


_EMPTY_PROGRESS = {
    "total_estimate": 0.0,
    "weighted_done": 0.0,
    "percent": 0.0,
    "by_parent": [],
}

_OVERVIEW_CACHE_VERSION = "utc_v1"


def _cached(key: tuple[object, ...], factory):
    return state.overview_cache_get_or_set(key, factory)


@solara.component
def Page():
    project = state.current_project.value
    contributors = state.contributors_count.value

    # Derive these before any early return so hooks are unconditional.
    config = (project or {}).get("config") or {}
    project_id = (project or {}).get("project_id", "")
    org = (project or {}).get("org", "")
    number = (project or {}).get("number", 0)
    estimate_field = config.get("estimate_field", "")

    def load_data():
        if not project_id or state.project_data.value is not None or state.loading.value:
            return
        state.loading.value = True
        state.error.value = None

        def run():
            try:
                from core import timeline as tl
                result = tl.load(project_id, org, number)
                state.project_data.value = result
            except Exception as e:
                state.error.value = str(e)
            finally:
                state.loading.value = False

        threading.Thread(target=run, daemon=True).start()

    solara.use_effect(load_data, [project_id])  # noqa: SH101

    data = state.project_data.value
    loading = state.loading.value
    error = state.error.value
    items = data["items"] if data else {}
    timelines = data["timelines"] if data else {}
    field_values = data["field_values"] if data else {}
    milestone = state.selected_milestone.value
    progress_data = (
        _cached(
            (_OVERVIEW_CACHE_VERSION, "progress", project_id, milestone, estimate_field),
            lambda: progress_mod.weighted_progress_for_milestone(
                milestone, items, estimate_field, field_values
            ),
        )
        if data is not None
        else _EMPTY_PROGRESS
    )

    if not project:
        NoProjectSelected()
        return

    with solara.Column(style="padding: 24px; width: 100%; min-width: 0;"):
        with solara.Row(justify="space-between", style="align-items: center;"):
            solara.Markdown(f"## Overview — {project.get('title', '')}")
            solara.Button(
                "↻ Refresh",
                on_click=lambda: _refresh(project_id, org, number),
                disabled=loading,
                outlined=True,
            )

        if loading:
            solara.ProgressLinear(True)
            solara.Text("Fetching issues and timelines…", style="color: var(--color-fg-muted);")
            return

        if error:
            solara.Text(f"Error: {error}", style="color: var(--color-critical, #d03b3b);")
            return

        if data is None:
            return

        with solara.Row(gap="12px", style="align-items: flex-end; margin-bottom: 16px;"):
            MilestoneSelect(items)
            ActivityWindowSelect()
            ContributorsSelect(contributors, lambda value: setattr(state.contributors_count, "value", value))

        with solara.Row(
            gap="24px",
            style="align-items: flex-start; width: 100%; flex-wrap: wrap;",
        ):
            with solara.Column(
                style=(
                    "flex: 0 0 calc(55% - 12px); width: calc(55% - 12px); "
                    "max-width: calc(55% - 12px); min-width: 420px;"
                )
            ):
                _ActivitySection(project_id, milestone, items, timelines, field_values, estimate_field)
                solara.HTML(tag="div", style="margin: 24px 0;")
                _BurnupSection(project_id, milestone, estimate_field, items, timelines, field_values)

            with solara.Column(
                style=(
                    "flex: 0 0 calc(45% - 12px); width: calc(45% - 12px); "
                    "max-width: calc(45% - 12px); min-width: 320px; align-self: stretch;"
                )
            ):
                _MilestoneSummary(project_id, milestone, estimate_field, items, timelines, field_values, progress_data, contributors)
                solara.HTML(tag="div", style="margin: 12px 0;")
                solara.Text(
                    "PROGRESS",
                    style="font-size: 0.75rem; font-weight: 600; color: var(--color-fg-muted); "
                          "letter-spacing: 0.06em; margin-bottom: 12px;",
                )
                ProgressBreakdown(progress_data, estimate_field)


@solara.component
def _BurnupSection(project_id, milestone, estimate_field, items, timelines, field_values):
    dates = _cached(
        (_OVERVIEW_CACHE_VERSION, "burnup_dates", project_id),
        lambda: [
            item.get("createdAt", "")[:10]
            for item in items.values()
            if item.get("createdAt")
        ],
    )

    start, end = (
        (
            date.fromisoformat(min(dates)),
            utc_today(),
        )
        if dates
        else (utc_today(), utc_today())
    )

    snapshots = _cached(
        (_OVERVIEW_CACHE_VERSION, "burnup_snapshots", project_id),
        lambda: {
            label: store.read_snapshot(project_id, label)
            for label in store.list_snapshots(project_id)
        },
    )

    rows = _cached(
        (_OVERVIEW_CACHE_VERSION, "burnup_rows", project_id, milestone, estimate_field),
        lambda: series_mod.burnup(
            project_id=project_id,
            milestone=milestone,
            estimate_field=estimate_field,
            items=items,
            timelines=timelines,
            live_field_values=field_values,
            start=start,
            end=end,
            snapshots=snapshots,
        ) if estimate_field and dates else [],
    )

    if not estimate_field:
        solara.Text("No estimate field configured.", style="color: var(--color-fg-muted);")
        return
    if not dates:
        solara.Text("No issues found.", style="color: var(--color-fg-muted);")
        return

    milestone_label = "All milestones" if milestone == "all" else milestone
    BurnupChart(rows, title=f"Burn-up — {milestone_label}", estimate_field=estimate_field, height=620)


@solara.component
def _ActivitySection(project_id, milestone, items, timelines, field_values, estimate_field):
    days = state.activity_window_days.value
    since = activity_mod.since_date(days)

    added = _cached(
        (_OVERVIEW_CACHE_VERSION, "activity_added", project_id, milestone, since),
        lambda: activity_mod.added_to_milestone(milestone, since, items, timelines),
    )
    completed = _cached(
        (_OVERVIEW_CACHE_VERSION, "activity_completed", project_id, milestone, since),
        lambda: activity_mod.completed_in_window(milestone, since, items, timelines),
    )
    added_estimate = _cached(
        (_OVERVIEW_CACHE_VERSION, "activity_added_estimate", project_id, milestone, since, estimate_field),
        lambda: _sum_estimates(added, estimate_field, field_values),
    )

    with solara.Column(gap="0px"):
        solara.Text(
            "RECENT ACTIVITY",
            style="font-size: 0.75rem; font-weight: 600; color: var(--color-fg-muted); "
                  "letter-spacing: 0.06em; margin-bottom: 12px;",
        )

        solara.Text(
            f"Added to milestone ({added_estimate:.1f} days, {len(added)} issues) 🚧",
            style="font-weight: 600; margin-bottom: 4px;",
        )
        if added:
            for issue in added[:10]:
                _IssueRow(issue)
            if len(added) > 10:
                solara.Text(f"…and {len(added) - 10} more", style="color: var(--color-fg-muted); font-size: 0.82rem;")
        else:
            solara.Text("None in this window.", style="color: var(--color-fg-muted); font-size: 0.85rem;")

        solara.HTML(tag="div", style="margin: 12px 0;")

        solara.Text(
            f"Completed ({len(completed)}) 🎉",
            style="font-weight: 600; margin-bottom: 4px;",
        )
        if completed:
            for issue in completed[:10]:
                _IssueRow(issue)
            if len(completed) > 10:
                solara.Text(f"…and {len(completed) - 10} more", style="color: var(--color-fg-muted); font-size: 0.82rem;")
        else:
            solara.Text("None in this window.", style="color: var(--color-fg-muted); font-size: 0.85rem;")


@solara.component
def _IssueRow(issue: dict[str, Any]):
    url = issue.get("url", "")
    number = issue.get("number", "")
    title = issue.get("title", "")
    at = (issue.get("at") or "")[:10]
    number_label = f"#{number}" if number is not None and number != "" else "Item"

    with solara.Row(
        gap="8px",
        style="align-items: center; padding: 3px 0; border-bottom: 1px solid var(--color-border);",
    ):
        if url:
            solara.HTML(
                tag="a",
                unsafe_innerHTML=number_label,
                attributes={
                    "href": url,
                    "target": "_blank",
                    "style": "color: #0969da; text-decoration: none;",
                },
            )
        else:
            solara.Text(number_label, style="font-size: 0.85rem; color: var(--color-fg-muted);")
        solara.Text(
            title,
            style=(
                "font-size: 0.85rem; flex: 0 1 70%; min-width: 0; "
                "white-space: nowrap; overflow: hidden; text-overflow: ellipsis;"
            ),
        )
        solara.Text(
            at,
            style=(
                "font-size: 0.78rem; color: var(--color-fg-muted); "
                "white-space: nowrap; width: 88px; text-align: left;"
            ),
        )


@solara.component
def _MilestoneSummary(project_id, milestone, estimate_field, items, timelines, field_values, progress_data, contributors):
    milestone_meta = (
        _cached(
            (_OVERVIEW_CACHE_VERSION, "milestone_meta", project_id, milestone),
            lambda: _milestone_metadata(milestone, items),
        )
        if milestone not in (None, "all")
        else None
    )
    open_estimated_days = (
        _cached(
            (_OVERVIEW_CACHE_VERSION, "open_estimated_days", project_id, milestone, estimate_field),
            lambda: _open_estimated_days(milestone, estimate_field, items, timelines, field_values),
        )
        if milestone not in (None, "all")
        else 0.0
    )

    if milestone in (None, "all"):
        return
    if milestone_meta is None:
        return

    due_on = milestone_meta.get("dueOn")
    workdays_left = _workdays_until(due_on[:10] if due_on else None)
    estimated_days_left = max(0.0, progress_data.get("total_estimate", 0.0) - progress_data.get("done", 0.0))
    contributors_count = int(contributors)
    fifty_precent_rule_days = estimated_days_left * 2
    days_per_participant = fifty_precent_rule_days / contributors_count if contributors_count else 0.0
    days_per_participant_color = _days_per_participant_color(days_per_participant, workdays_left)

    with solara.Column(gap="12px", style="width: 100%;"):
        with solara.Row(gap="12px", style="width: 100%; align-items: stretch; flex-wrap: wrap;"):
            with solara.Column(
                style=(
                    "flex: 1 1 220px; padding: 12px 14px; border: 1px solid var(--color-border); "
                    "border-radius: 8px; background: var(--color-canvas-subtle);"
                ),
            ):
                solara.Text(
                    "Workdays to target",
                    style="font-size: 0.78rem; font-weight: 600; color: var(--color-fg-muted);",
                )
                solara.Text(
                    "—" if workdays_left is None else str(workdays_left),
                    style="font-size: 1.5rem; font-weight: 600;",
                )
                if due_on:
                    solara.HTML(
                        tag="div",
                        unsafe_innerHTML=(
                            "<span style='color: var(--color-fg-muted);'>Due </span>"
                            f"<span style='font-weight: 600;'>{due_on[:10]}</span>"
                        ),
                        style="font-size: 0.82rem;",
                    )

            with solara.Column(
                style=(
                    "flex: 1 1 220px; padding: 12px 14px; border: 1px solid var(--color-border); "
                    "border-radius: 8px; background: var(--color-canvas-subtle);"
                ),
            ):
                solara.Text(
                    "Estimated days left",
                    style="font-size: 0.78rem; font-weight: 600; color: var(--color-fg-muted);",
                )
                solara.Text(f"{estimated_days_left:.1f}", style="font-size: 1.5rem; font-weight: 600;")
                solara.Text(
                    f"{open_estimated_days:.1f} open estimate days",
                    style="font-size: 0.82rem; color: var(--color-fg-muted);",
                )
                solara.Text(
                    f"{estimated_days_left:.1f} estimate days left (with progress derived from issue state)",
                    style="font-size: 0.82rem; color: var(--color-fg-muted);",
                )
                solara.Text(
                    f"{fifty_precent_rule_days:.1f} estimate days with the 50% rule",
                    style="font-size: 0.82rem; color: var(--color-fg-muted);",
                )
                solara.HTML(
                    tag="div",
                    unsafe_innerHTML=(
                        f"<span style='color: {days_per_participant_color}; font-weight: 600;'>"
                        f"{days_per_participant:.1f}</span> "
                        f"<span style='color: var(--color-fg-muted);'>estimate days per contributor</span>"
                    ),
                    style="font-size: 0.82rem;",
                )


def _milestone_metadata(milestone: str, items: dict[str, Any]) -> dict[str, Any] | None:
    for item in items.values():
        milestone_meta = item.get("milestone")
        if milestone_meta and milestone_meta.get("title") == milestone:
            return milestone_meta
    return None


def _sum_estimates(issues: list[dict[str, Any]], estimate_field: str, field_values: dict[str, Any]) -> float:
    total = 0.0
    for issue in issues:
        issue_id = issue.get("id")
        if not issue_id:
            continue
        entry = (field_values.get(issue_id) or {}).get(estimate_field)
        value = entry.get("value") if entry else None
        if value is not None:
            total += float(value)
    return total


def _open_estimated_days(milestone: str, estimate_field: str, items: dict[str, Any], timelines: dict[str, Any], field_values: dict[str, Any]) -> float:
    total = 0.0
    at = utc_today_iso() + "T23:59:59Z"
    for issue_id, item in items.items():
        item_milestone = (item.get("milestone") or {}).get("title")
        if item_milestone != milestone:
            continue
        state = reconstruct.state_at(item, timelines.get(issue_id, []), at)
        if reconstruct.is_completed(state):
            continue
        entry = (field_values.get(issue_id) or {}).get(estimate_field)
        value = entry.get("value") if entry else None
        if value is not None:
            total += float(value)
    return total


def _workdays_until(due_date: str | None) -> int | None:
    if not due_date:
        return None

    target = date.fromisoformat(due_date)
    today = utc_today()
    if target < today:
        return 0

    workdays = 0
    current = today
    while current <= target:
        if current.weekday() < 5:
            workdays += 1
        current += timedelta(days=1)
    return workdays


def _days_per_participant_color(days_per_participant: float, workdays_left: int | None) -> str:
    if workdays_left is None:
        return "var(--color-fg-default)"
    if days_per_participant <= workdays_left:
        return "#0ca30c"
    if days_per_participant <= workdays_left + 4:
        return "#fab219"
    return "#d03b3b"


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def _refresh(project_id, org, number):
    state.project_data.value = None
    state.loading.value = True
    state.error.value = None
    state.clear_overview_cache()

    def run():
        try:
            from core import timeline as tl
            result = tl.load(project_id, org, number, force=True)
            state.project_data.value = result
        except Exception as e:
            state.error.value = str(e)
        finally:
            state.loading.value = False

    threading.Thread(target=run, daemon=True).start()


def _take_snapshot(project_id, org, number, items, field_values):
    """Write today's snapshot (idempotent)."""
    label = store.today_label()
    snapshot_items = {}
    for issue_id, item in items.items():
        fv = field_values.get(issue_id) or {}
        snapshot_items[issue_id] = {
            "number": item["number"],
            "title": item["title"],
            "url": item["url"],
            "state": item["state"],
            "stateReason": item.get("stateReason"),
            "fields": {
                fname: {"value": entry["value"], "updatedAt": entry.get("updatedAt", "")}
                for fname, entry in fv.items()
            },
        }
    store.write_snapshot(project_id, label, {
        "captured_at": utc_today_iso() + "T00:00:00Z",
        "items": snapshot_items,
    })
