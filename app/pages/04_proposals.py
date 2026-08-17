"""Proposals page — placeholder while the feature is being built."""

from __future__ import annotations

from pathlib import Path

import solara

from app import state
from app.components.empty_state import NoProjectSelected

_CONFUSED_STICKMAN = (
    Path(__file__).parent.parent.parent / "images" / "confused-stickman.png"
)


@solara.component
def Page():
    project = state.current_project.value

    if not project:
        NoProjectSelected()
        return

    with solara.Column(
        style=(
            "align-items: center; justify-content: center; "
            "min-height: 60vh; gap: 16px; text-align: center;"
        ),
    ):
        solara.Image(_CONFUSED_STICKMAN, width="220px")
        solara.Text(
            "Not yet supported.",
            style="font-size: 1.1rem; font-weight: 600; color: var(--color-fg-default);",
        )
        solara.Text(
            "Proposal mode is coming soon.",
            style=(
                "font-size: 0.95rem; color: var(--color-fg-muted); "
                "max-width: 340px; line-height: 1.5;"
            ),
        )
