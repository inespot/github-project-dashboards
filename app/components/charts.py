"""Burn-up chart component.

Design choices (per dataviz skill):
  - Form: stacked area chart over time.
  - Stack (bottom → top): Done, In Progress, To Do — sums to scope.
  - Scope line (slot 1, blue #2a78d6): total scope upper boundary.
  - Done (slot 2, orange #eb6834): completed estimate.
  - In Progress (slot 3, aqua #1baf7a): project Status "In Progress".
  - To Do (slot 1 blue at low opacity): remaining not yet started.
  - Crosshair + unified tooltip, one series per legend entry.
  - No dual-axis. Blocked omitted for now.
"""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go
import solara

from app.theme import SERIES


@solara.component
def BurnupChart(
    rows: list[dict[str, Any]],
    height: int = 380,
):
    """Render a burn-up chart (title is rendered by the caller as a card heading).

    `rows` is the output of core.series.burnup():
      [{date, scope, completed, in_progress, todo, remaining, added, confidence}, ...]
    """
    if not rows:
        solara.Text("No data yet — run a data refresh.", style="color: var(--color-fg-muted);")
        return

    dates = [r["date"] for r in rows]
    scope = [r["scope"] for r in rows]
    completed = [r["completed"] for r in rows]
    in_progress = [r.get("in_progress", 0.0) for r in rows]
    todo = [r.get("todo", r["scope"] - r["completed"]) for r in rows]
    s_light = SERIES["light"]

    scope_color = s_light[1]       # blue
    completed_color = s_light[2]   # orange
    in_progress_color = s_light[3]  # aqua
    todo_fill = "rgba(42,120,214,0.18)"  # slot-1 blue at 18%

    fig = go.Figure()

    # Stacked status areas (bottom → top). stackgroup makes them sum to scope.
    fig.add_trace(go.Scatter(
        x=dates, y=completed,
        name="Done",
        mode="lines",
        stackgroup="status",
        line=dict(width=0.5, color=completed_color),
        fillcolor="rgba(235,104,52,0.35)",
        hovertemplate="%{y:.1f}<extra>Done</extra>",
    ))

    fig.add_trace(go.Scatter(
        x=dates, y=in_progress,
        name="In Progress",
        mode="lines",
        stackgroup="status",
        line=dict(width=0.5, color=in_progress_color),
        fillcolor="rgba(27,175,122,0.35)",
        hovertemplate="%{y:.1f}<extra>In Progress</extra>",
    ))

    fig.add_trace(go.Scatter(
        x=dates, y=todo,
        name="To Do",
        mode="lines",
        stackgroup="status",
        line=dict(width=0.5, color=scope_color),
        fillcolor=todo_fill,
        hovertemplate="%{y:.1f}<extra>To Do</extra>",
    ))

    # Scope line (top boundary — should align with top of stack)
    fig.add_trace(go.Scatter(
        x=dates, y=scope,
        name="Scope",
        mode="lines",
        line=dict(color=scope_color, width=2),
        hovertemplate="%{y:.1f}<extra>Scope</extra>",
    ))

    fig.update_layout(
        template="primer_light",
        title=None,
        height=height,
        margin=dict(t=16, b=80, l=48, r=16),  # b gives room for legend
        xaxis=dict(title="", type="date"),
        yaxis=dict(title=""),
        hovermode="x unified",
        legend=dict(
            orientation="h",        # horizontal row, avoids covering y-axis
            yanchor="top",
            y=-0.18,                # below the x-axis
            xanchor="left",
            x=0,
        ),
        showlegend=True,
    )

    solara.FigurePlotly(fig)


@solara.component
def ProgressSummary(
    progress_data: dict[str, Any],
    estimate_field: str = "Estimate",
):
    """Compact progress metric card (same layout as roadmap delta)."""
    pct = progress_data.get("percent", 0.0)
    total = progress_data.get("total_estimate", 0.0)
    done = progress_data.get("done", 0.0)

    with solara.Column(gap="4px", style="width: 100%; min-width: 0;"):
        solara.Text(
            "Progress",
            style="font-size: 0.78rem; font-weight: 600; color: var(--color-fg-muted);",
        )
        solara.Text(
            "In Progress 20% · draft 30% · review 70% · merged 100%",
            style="font-size: 0.72rem; color: var(--color-fg-muted); font-style: italic; margin-bottom: 4px;",
        )
        solara.Text(f"{pct:.1f}%", style="font-size: 1.5rem; font-weight: 600;")
        solara.Text(
            f"{done:.1f} / {total:.1f} {estimate_field} done",
            style="font-size: 0.78rem; color: var(--color-fg-muted);",
        )


@solara.component
def ProgressByParent(
    progress_data: dict[str, Any],
    estimate_field: str = "Estimate",
):
    """Breakdown of weighted progress by parent task."""
    by_parent = progress_data.get("by_parent", [])
    if not by_parent:
        return

    with solara.Column(gap="6px", style="width: 100%; min-width: 0;"):
        solara.Text(
            "Progress by parent task",
            style="font-weight: 600; margin-bottom: 4px;",
        )
        solara.Text(
            "Uses the same Status / PR progress weights as the Progress card.",
            style="font-size: 0.82rem; color: var(--color-fg-muted); font-style: italic; margin-bottom: 4px;",
        )
        for parent in by_parent:
            _ParentRow(parent, estimate_field)


@solara.component
def ProgressBreakdown(
    progress_data: dict[str, Any],
    estimate_field: str = "Estimate",
):
    """Legacy combined view: summary + by-parent breakdown."""
    ProgressSummary(progress_data, estimate_field)
    ProgressByParent(progress_data, estimate_field)


@solara.component
def _ParentRow(parent: dict[str, Any], estimate_field: str):
    pct = parent.get("percent", 0.0)
    title = parent.get("parent_title", "(no parent)")
    number = parent.get("parent_number")
    url = parent.get("parent_url") or ""
    total = parent.get("total_estimate", 0.0)
    done = parent.get("done", 0.0)
    number_label = f"#{number}" if number is not None and number != "" else ""

    pct_clamped = min(100.0, max(0.0, pct))
    with solara.Column(gap="3px", style="margin-bottom: 6px; width: 100%; min-width: 0;"):
        with solara.Row(gap="8px", style="width: 100%; align-items: center;"):
            if number_label and url:
                solara.HTML(
                    tag="a",
                    unsafe_innerHTML=number_label,
                    attributes={
                        "href": url,
                        "target": "_blank",
                        "style": "color: #0969da; text-decoration: none; font-size: 0.85rem;",
                    },
                )
            elif number_label:
                solara.Text(number_label, style="font-size: 0.85rem; color: var(--color-fg-muted);")
            solara.Text(
                title,
                style=(
                    "font-size: 0.85rem; flex: 1 1 auto; min-width: 0; "
                    "white-space: nowrap; overflow: hidden; text-overflow: ellipsis;"
                ),
            )
            solara.Text(
                f"{pct:.0f}% ({done:.1f}/{total:.1f})",
                style="font-size: 0.80rem; color: var(--color-fg-muted); white-space: nowrap;",
            )
        solara.HTML(
            tag="div",
            style=(
                f"width: 100%; height: 5px; border-radius: 3px; "
                f"background: linear-gradient(to right, "
                f"#eb6834 {pct_clamped:.1f}%, "
                f"var(--color-border) {pct_clamped:.1f}%);"
            ),
        )
