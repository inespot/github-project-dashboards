"""Burn-up chart component.

Design choices (per dataviz skill):
  - Form: area chart, change over time, 2 categorical series (scope, completed).
  - Series 1 (slot 1, blue #2a78d6): total scope. Upper boundary line.
  - Series 2 (slot 2, orange #eb6834): completed. Filled area from zero.
  - Remaining = the gap between them (scope fill at 15% opacity, no legend entry).
  - Crosshair + unified tooltip, one series per legend entry.
  - No dual-axis.
"""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go
import solara

from app.theme import SERIES


@solara.component
def BurnupChart(
    rows: list[dict[str, Any]],
    title: str = "Burn-up",
    estimate_field: str = "Estimate",
    height: int = 380,
):
    """Render a burn-up chart.

    `rows` is the output of core.series.burnup():
      [{date, scope, completed, remaining, added, confidence}, ...]
    """
    if not rows:
        solara.Text("No data yet — run a data refresh.", style="color: var(--color-fg-muted);")
        return

    dates = [r["date"] for r in rows]
    scope = [r["scope"] for r in rows]
    completed = [r["completed"] for r in rows]
    s_light = SERIES["light"]

    scope_color = s_light[1]       # blue
    completed_color = s_light[2]   # orange
    remaining_fill = f"rgba(42,120,214,0.12)"  # slot-1 blue at 12%

    fig = go.Figure()

    # Scope line (top boundary)
    fig.add_trace(go.Scatter(
        x=dates, y=scope,
        name="Scope",
        mode="lines",
        line=dict(color=scope_color, width=2),
        hovertemplate="%{y:.1f}<extra>Scope</extra>",
    ))

    # Remaining fill (area between completed and scope — same color as scope, low opacity)
    fig.add_trace(go.Scatter(
        x=dates, y=scope,
        fill="tonexty",
        fillcolor=remaining_fill,
        mode="none",
        showlegend=False,
        hoverinfo="skip",
        name="_remaining_fill",
    ))

    # Completed filled area (from zero)
    fig.add_trace(go.Scatter(
        x=dates, y=completed,
        name="Completed",
        mode="lines",
        fill="tozeroy",
        fillcolor=f"rgba(235,104,52,0.25)",  # slot-2 orange at 25%
        line=dict(color=completed_color, width=2),
        hovertemplate="%{y:.1f}<extra>Completed</extra>",
    ))

    fig.update_layout(
        template="primer_light",
        title=dict(
            text=f"{title} ({estimate_field})",
            x=0,
            xanchor="left",
            font=dict(size=14),
        ),
        height=height,
        margin=dict(t=52, b=80, l=60, r=20),  # t clears the title; b gives room for legend
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
    )

    solara.FigurePlotly(fig)


@solara.component
def ProgressBreakdown(
    progress_data: dict[str, Any],
    estimate_field: str = "Estimate",
):
    """Progress bar + breakdown by parent task."""
    pct = progress_data.get("percent", 0.0)
    total = progress_data.get("total_estimate", 0.0)
    done = progress_data.get("done", 0.0)
    by_parent = progress_data.get("by_parent", [])

    with solara.Column(gap="8px", style="width: 100%; min-width: 0;"):
        # Explanation note
        solara.Markdown(
            "_When an issue is not yet closed, progress is derived from linked PRs: "
            "draft 40%, in review 70%, merged 100%, non-closing link 20%._",
            style="font-size: 0.82rem; color: var(--color-fg-muted); margin: 0;",
        )

        # Hero figure
        with solara.Row(gap="16px", style="align-items: center; width: 100%;"):
            solara.Text(f"{pct:.1f}%", style="font-size: 2.2rem; font-weight: 600;")
            with solara.Column(gap="2px", style="min-width: 0;"):
                solara.Text(
                    f"{done:.1f} / {total:.1f} {estimate_field} done",
                    style="font-size: 0.85rem; color: var(--color-fg-muted);",
                )

        # Progress bar — single div with CSS gradient to avoid children kwarg limitation
        bar_color = "#eb6834"  # slot-2 orange (var(--series-2) not resolved in inline gradient)
        pct_clamped = min(100.0, max(0.0, pct))
        solara.HTML(
            tag="div",
            style=(
                f"width: 100%; height: 8px; border-radius: 4px; "
                f"background: linear-gradient(to right, "
                f"{bar_color} {pct_clamped:.1f}%, "
                f"var(--color-border) {pct_clamped:.1f}%);"
            ),
        )

        if by_parent:
            solara.Text(
                "By parent task",
                style="font-size: 0.8rem; font-weight: 600; color: var(--color-fg-muted); "
                      "margin-top: 8px; text-transform: uppercase; letter-spacing: 0.05em;",
            )
            for parent in by_parent:
                _ParentRow(parent, estimate_field)


@solara.component
def _ParentRow(parent: dict[str, Any], estimate_field: str):
    pct = parent.get("percent", 0.0)
    title = parent.get("parent_title", "(no parent)")
    total = parent.get("total_estimate", 0.0)
    done = parent.get("done", 0.0)

    pct_clamped = min(100.0, max(0.0, pct))
    with solara.Column(gap="3px", style="margin-bottom: 6px; width: 100%; min-width: 0;"):
        with solara.Row(justify="space-between", style="width: 100%;"):
            solara.Text(title, style="font-size: 0.82rem; color: var(--color-fg-default);")
            solara.Text(
                f"{pct:.0f}% ({done:.1f}/{total:.1f})",
                style="font-size: 0.80rem; color: var(--color-fg-muted);",
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
