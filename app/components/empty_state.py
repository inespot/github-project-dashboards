"""Shared empty-state components."""

from __future__ import annotations

from pathlib import Path

import solara

_CONFUSED_STICKMAN = Path(__file__).parent.parent.parent / "images" / "confused-stickman.png"


@solara.component
def NoProjectSelected():
    """Centered illustration + message shown when no project has been selected."""
    with solara.Column(
        style=(
            "align-items: center; justify-content: center; "
            "min-height: 60vh; gap: 16px; text-align: center;"
        ),
    ):
        solara.Image(_CONFUSED_STICKMAN, width="220px")
        solara.Text(
            "No project selected.\nReturn to the Projects tab and select one.",
            style=(
                "font-size: 1rem; color: var(--color-fg-muted); "
                "max-width: 340px; line-height: 1.5; white-space: pre-line;"
            ),
        )
