"""Roadmaps page — milestone-focused issue timeline."""

from __future__ import annotations

import threading
from datetime import date as dt_date, timedelta
from typing import Any

import plotly.graph_objects as go
import solara

from app import state
from app.components.empty_state import NoProjectSelected
from app.components.selectors import MilestoneSelect
from app.theme import SERIES, CHROME
from core.time import utc_today_iso


@solara.component
def Page(name: str = "current"):
    """Dynamic page — `name` is the roadmap variant: 'current' or a snapshot label."""
    project = state.current_project.value
    project_id = (project or {}).get("project_id", "")
    org = (project or {}).get("org", "")
    number = (project or {}).get("number", 0)

    color_options = ["completed vs open", "assignee"]
    color_by, set_color_by = solara.use_state("completed vs open")  # noqa: SH101
    order_options = ["start date", "end date", "assignee"]
    order_by, set_order_by = solara.use_state("start date")  # noqa: SH101

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

    if not project:
        NoProjectSelected()
        return

    config = project.get("config") or {}
    estimate_field = config.get("estimate_field", "")
    start_field = config.get("start_field", "")
    end_field = config.get("end_field", "")
    data = state.project_data.value
    loading = state.loading.value
    error = state.error.value

    with solara.Column(style="padding: 24px; width: 100%; min-width: 0;"):
        with solara.Row(justify="space-between", style="align-items: center;"):
            solara.Markdown(f"## Roadmap — {project.get('title', '')}")

        if not start_field or not end_field:
            solara.Text(
                "Start and end date fields are not configured. "
                "Return to Projects tab and reconnect the project.",
                style="color: var(--color-fg-muted);",
            )
            return

        if loading:
            solara.ProgressLinear(True)
            solara.Text("Fetching issues and timelines...", style="color: var(--color-fg-muted);")
            return

        if error:
            solara.Text(f"Error: {error}", style="color: var(--color-critical, #d03b3b);")
            return

        if data is None:
            return

        items = data["items"]
        field_values = data["field_values"]
        milestone = state.selected_milestone.value

        with solara.Row(gap="12px", style="align-items: flex-end; margin-bottom: 16px;"):
            MilestoneSelect(items)
            solara.Select(
                label="Color by",
                value=color_by,
                values=color_options,
                on_value=set_color_by,
                style="min-width: 180px; max-width: 240px;",
            )
            solara.Select(
                label="Order by",
                value=order_by,
                values=order_options,
                on_value=set_order_by,
                style="min-width: 180px; max-width: 240px;",
            )

        _RoadmapTimeline(items, field_values, estimate_field, start_field, end_field, milestone, color_by, order_by)


@solara.component
def _RoadmapTimeline(
    items: dict[str, Any],
    field_values: dict[str, Any],
    estimate_field: str,
    start_field: str,
    end_field: str,
    milestone: str,
    color_by: str,
    order_by: str,
):
    s = SERIES["light"]
    c = CHROME["light"]

    rows = solara.use_memo(
        lambda: _build_rows(items, field_values, start_field, end_field, milestone, color_by, order_by),
        [items, field_values, start_field, end_field, milestone, color_by, order_by],
    )
    missing_dates = solara.use_memo(
        lambda: _issues_missing_dates(items, field_values, estimate_field, start_field, end_field, milestone),
        [items, field_values, estimate_field, start_field, end_field, milestone],
    )
    milestone_meta = solara.use_memo(
        lambda: _milestone_metadata(milestone, items),
        [milestone, items],
    )
    assignee_blocks = _assignee_blocks(rows) if order_by == "assignee" else []

    if missing_dates:
        with solara.Column(gap="4px", style="margin-bottom: 16px;"):
            solara.Text(
                f"Tasks missing roadmap dates ({len(missing_dates)})",
                style="font-weight: 600;",
            )
            for task in missing_dates[:12]:
                _MissingDateIssueRow(task)
            if len(missing_dates) > 12:
                solara.Text(
                    f"…and {len(missing_dates) - 12} more",
                    style="font-size: 0.82rem; color: var(--color-fg-muted);",
                )

    if not rows:
        if milestone == "all":
            message = f"No issues have both '{start_field}' and '{end_field}' set."
        else:
            message = (
                f"No issues in milestone '{milestone}' have both "
                f"'{start_field}' and '{end_field}' set."
            )
        solara.Text(message, style="color: var(--color-fg-muted);")
        return

    color_map = _color_map(rows, color_by, s)
    traces: dict[str, dict[str, Any]] = {}
    for row in rows:
        group = row["color_group"]
        traces.setdefault(group, {
            "x": [],
            "y": [],
            "customdata": [],
            "line_color": color_map[group],
        })
        trace = traces[group]
        trace["x"].extend([row["start"], row["end"], None])
        trace["y"].extend([row["label"], row["label"], None])
        customdata = [
            row["title"],
            row["start"],
            row["end"],
            row["milestone"] or "",
            row["assignee_display"],
            row["status_label"],
        ]
        trace["customdata"].extend([customdata, customdata, [None, None, None, None, None, None]])

    fig = go.Figure()
    for group, trace in traces.items():
        fig.add_trace(go.Scatter(
            name=group,
            x=trace["x"],
            y=trace["y"],
            mode="lines",
            line=dict(color=trace["line_color"], width=16),
            customdata=trace["customdata"],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Start: %{customdata[1]}<br>"
                "End: %{customdata[2]}<br>"
                "Milestone: %{customdata[3]}<br>"
                "Assignee: %{customdata[4]}<br>"
                "Status: %{customdata[5]}<extra>%{fullData.name}</extra>"
            ),
            connectgaps=False,
        ))

    today = utc_today_iso()
    fig.add_vline(
        x=today,
        line_color="#d03b3b",
        line_width=2,
        line_dash="dot",
        annotation_text="Today",
        annotation_position="top right",
        annotation_font=dict(size=10, color="#d03b3b"),
    )

    if milestone_meta and milestone_meta.get("dueOn"):
        due_date = milestone_meta["dueOn"][:10]
        fig.add_vline(
            x=due_date,
            line_color="#8250df",
            line_width=2,
            annotation_text=f"Target {due_date}",
            annotation_position="top left",
            annotation_font=dict(size=10, color="#8250df"),
        )

    labels = [row["label"] for row in rows]
    category_labels = list(reversed(labels))
    position_by_label = {label: index for index, label in enumerate(category_labels)}

    if assignee_blocks:
        for index, block in enumerate(assignee_blocks):
            first_pos = position_by_label.get(block["first_label"])
            last_pos = position_by_label.get(block["last_label"])
            if first_pos is None or last_pos is None:
                continue
            y0 = min(first_pos, last_pos) - 0.48
            y1 = max(first_pos, last_pos) + 0.48
            fig.add_hrect(
                y0=y0,
                y1=y1,
                fillcolor="rgba(99,108,118,0.14)" if index % 2 == 0 else "rgba(99,108,118,0.04)",
                line_width=0,
                layer="below",
            )
            fig.add_annotation(
                x=0.995,
                xref="paper",
                y=(y0 + y1) / 2,
                yref="y",
                text=block["assignee"],
                showarrow=False,
                xanchor="right",
                yanchor="middle",
                align="right",
                font=dict(size=12, color=c["text_muted"]),
                bgcolor="rgba(255,255,255,0.92)",
                bordercolor="rgba(0,0,0,0)",
            )
    height = max(440, 100 + len(labels) * 34)

    fig.update_layout(
        template="primer_light",
        height=height,
        autosize=True,
        margin=dict(
            l=44,
            r=20,
            t=96,
            b=40,
        ),
        xaxis=dict(
            type="date",
            title="",
            showgrid=True,
            gridcolor=c["gridline"],
        ),
        yaxis=dict(
            title="Issue",
            title_standoff=18,
            type="category",
            categoryorder="array",
            categoryarray=category_labels,
            tickfont=dict(size=11),
            automargin=True,
        ),
        legend=dict(
            title=dict(text="Color by"),
            orientation="h",
            yanchor="bottom",
            y=1.10,
            xanchor="left",
            x=0,
        ),
    )

    with solara.Column(
        style="width: 100%; min-width: 0; flex: 1 1 auto; align-self: stretch; overflow: hidden;",
    ):
        _ResponsiveFigureEmbed(fig, height)


def _build_rows(
    items: dict[str, Any],
    field_values: dict[str, Any],
    start_field: str,
    end_field: str,
    milestone: str,
    color_by: str,
    order_by: str,
) -> list[dict[str, Any]]:
    rows = []
    for issue_id, item in items.items():
        item_milestone = (item.get("milestone") or {}).get("title")
        if milestone != "all" and item_milestone != milestone:
            continue

        fv = field_values.get(issue_id) or {}
        start_entry = fv.get(start_field)
        end_entry = fv.get(end_field)
        if not start_entry or not end_entry:
            continue

        start_str = start_entry.get("value")
        end_str = end_entry.get("value")
        if not start_str or not end_str:
            continue

        try:
            start_d = dt_date.fromisoformat(start_str[:10])
            end_d = dt_date.fromisoformat(end_str[:10])
        except ValueError:
            continue

        if end_d <= start_d:
            end_d = start_d + timedelta(days=1)

        assignees = item.get("assignees") or []
        assignee = assignees[0] if assignees else "(unassigned)"
        status_label = "Completed" if _is_completed(item) else "Open"
        number = item.get("number")
        number_label = f"#{number}" if number is not None and number != "" else "Item"
        title = item.get("title", "")
        label = _issue_label(number_label, title)

        if color_by == "assignee":
            color_group = assignee
        else:
            color_group = status_label

        rows.append({
            "label": label,
            "title": title,
            "start": start_d.isoformat(),
            "end": end_d.isoformat(),
            "duration_days": (end_d - start_d).days,
            "duration_ms": (end_d - start_d).days * 24 * 60 * 60 * 1000,
            "milestone": item_milestone,
            "assignee_display": assignee,
            "assignee_sort": _assignee_sort_key(assignee),
            "status_label": status_label,
            "color_group": color_group,
        })

    if order_by == "end date":
        return sorted(rows, key=lambda row: (row["end"], row["start"], row["label"]))
    if order_by == "assignee":
        return sorted(rows, key=lambda row: (row["assignee_sort"], row["start"], row["end"], row["label"]))
    return sorted(rows, key=lambda row: (row["start"], row["end"], row["label"]))


def _issues_missing_dates(
    items: dict[str, Any],
    field_values: dict[str, Any],
    estimate_field: str,
    start_field: str,
    end_field: str,
    milestone: str,
) -> list[dict[str, Any]]:
    children_by_parent: dict[int, list[str]] = {}
    for child_id, child_item in items.items():
        parent_number = (child_item.get("parent") or {}).get("number")
        if parent_number is None:
            continue
        children_by_parent.setdefault(parent_number, []).append(child_id)

    results = []
    for issue_id, item in items.items():
        item_milestone = (item.get("milestone") or {}).get("title")
        if milestone != "all" and item_milestone != milestone:
            continue
        if _is_completed(item):
            continue

        fv = field_values.get(issue_id) or {}
        start_value = (fv.get(start_field) or {}).get("value")
        end_value = (fv.get(end_field) or {}).get("value")
        if start_value and end_value:
            continue

        item_number = item.get("number")
        child_ids = children_by_parent.get(item_number, []) if item_number is not None else []
        if child_ids and _all_children_have_dates(child_ids, field_values, start_field, end_field):
            continue

        estimate_value = (fv.get(estimate_field) or {}).get("value") if estimate_field else None

        number_label = f"#{item_number}" if item_number is not None and item_number != "" else "Item"
        results.append({
            "number_label": number_label,
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "estimate_label": f"{float(estimate_value):.1f} days" if estimate_value is not None else "",
        })

    return sorted(results, key=lambda issue: (issue["number_label"], issue["title"]))


def _all_children_have_dates(
    child_ids: list[str],
    field_values: dict[str, Any],
    start_field: str,
    end_field: str,
) -> bool:
    for child_id in child_ids:
        fv = field_values.get(child_id) or {}
        start_value = (fv.get(start_field) or {}).get("value")
        end_value = (fv.get(end_field) or {}).get("value")
        if not start_value or not end_value:
            return False
    return True


def _color_map(rows: list[dict[str, Any]], color_by: str, series: dict[int, str]) -> dict[str, str]:
    groups = [row["color_group"] for row in rows]
    unique_groups = list(dict.fromkeys(groups))

    if color_by == "completed vs open":
        return {
            "Completed": "#8250df",
            "Open": "#1a7f37",
        }

    color_map = {}
    next_index = 1
    for group in unique_groups:
        if group == "(unassigned)":
            color_map[group] = "#6e7781"
            continue
        color_map[group] = series.get(((next_index - 1) % 8) + 1, series[1])
        next_index += 1
    return color_map


def _assignee_blocks(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    current_assignee = None
    current_first = None
    current_last = None

    for row in rows:
        assignee = row["assignee_display"]
        label = row["label"]
        if assignee != current_assignee:
            if current_assignee is not None and current_first is not None and current_last is not None:
                blocks.append({
                    "assignee": current_assignee,
                    "first_label": current_first,
                    "last_label": current_last,
                })
            current_assignee = assignee
            current_first = label
            current_last = label
        else:
            current_last = label

    if current_assignee is not None and current_first is not None and current_last is not None:
        blocks.append({
            "assignee": current_assignee,
            "first_label": current_first,
            "last_label": current_last,
        })

    return blocks


def _assignee_sort_key(assignee: str) -> tuple[int, str]:
    if assignee == "(unassigned)":
        return (1, assignee.lower())
    return (0, assignee.lower())


def _milestone_metadata(milestone: str, items: dict[str, Any]) -> dict[str, Any] | None:
    if milestone == "all":
        return None
    for item in items.values():
        milestone_meta = item.get("milestone")
        if milestone_meta and milestone_meta.get("title") == milestone:
            return milestone_meta
    return None


def _is_completed(item: dict[str, Any]) -> bool:
    if item.get("state") != "OPEN":
        return True
    return item.get("stateReason") == "COMPLETED" or item.get("project_status") == "Done"


def _issue_label(number_label: str, title: str, max_title_chars: int = 42) -> str:
    clean_title = " ".join((title or "").split())
    if len(clean_title) > max_title_chars:
        clean_title = clean_title[: max_title_chars - 1].rstrip() + "…"
    return f"{number_label} {clean_title}".strip()


@solara.component
def _MissingDateIssueRow(issue: dict[str, str]):
    with solara.Row(gap="8px", style="align-items: baseline; width: 100%;"):
        if issue["url"]:
            solara.HTML(
                tag="a",
                unsafe_innerHTML=issue["number_label"],
                attributes={
                    "href": issue["url"],
                    "target": "_blank",
                    "style": "color: #0969da; text-decoration: none;",
                },
            )
        else:
            solara.Text(issue["number_label"], style="color: var(--color-fg-muted);")
        solara.Text(
            issue["title"],
            style=(
                "font-size: 0.9rem; flex: 0 1 40%; min-width: 0; "
                "white-space: nowrap; overflow: hidden; text-overflow: ellipsis;"
            ),
        )
        if issue["estimate_label"]:
            solara.Text(
                issue["estimate_label"],
                style="font-size: 0.82rem; font-weight: 600; width: 80px; text-align: left;",
            )


@solara.component
def _ResponsiveFigureEmbed(fig: go.Figure, height: int):
    chart_html = fig.to_html(
        full_html=True,
        include_plotlyjs="cdn",
        config={"responsive": True},
        default_width="100%",
        default_height=f"{height}px",
    )
    solara.HTML(
        tag="iframe",
        attributes={
            "srcdoc": chart_html,
            "style": f"width: 100%; height: {height}px; border: 0; display: block;",
        },
    )
