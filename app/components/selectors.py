"""Reusable filter/selector components."""

from __future__ import annotations

from typing import Any

import solara

from app import state
from core.activity import WINDOW_OPTIONS


@solara.component
def MilestoneSelect(items: dict[str, Any]):
    """Dropdown to select a milestone or 'All'."""
    milestones: set[str] = set()
    for item in items.values():
        m = item.get("milestone")
        if m:
            milestones.add(m["title"])

    options = ["all"] + sorted(milestones)
    current_value = state.selected_milestone.value

    def normalize_selected_milestone():
        if current_value not in options:
            state.selected_milestone.value = "all"

    solara.use_effect(normalize_selected_milestone, [current_value, *options])  # noqa: SH101

    solara.Select(
        label="Milestone",
        value=current_value if current_value in options else "all",
        values=options,
        on_value=lambda v: setattr(state.selected_milestone, "value", v),
        style="min-width: 220px; max-width: 320px;",
    )


@solara.component
def ActivityWindowSelect():
    """Dropdown to select the activity window (1 week / 2 weeks / 1 month)."""
    options_labels = list(WINDOW_OPTIONS.keys())
    # current value is days; reverse-map to label
    current_days = state.activity_window_days.value
    current_label = next(
        (k for k, v in WINDOW_OPTIONS.items() if v == current_days),
        options_labels[0],
    )

    def on_change(label: str):
        state.activity_window_days.value = WINDOW_OPTIONS[label]

    solara.Select(
        label="Activity window",
        value=current_label,
        values=options_labels,
        on_value=on_change,
        style="min-width: 160px; max-width: 220px;",
    )


@solara.component
def ContributorsSelect(value: str, on_value):
    """Dropdown to select the number of contributors."""
    solara.Select(
        label="Contributors",
        value=value,
        values=[str(i) for i in range(1, 9)],
        on_value=on_value,
        style="min-width: 160px; max-width: 220px;",
    )
