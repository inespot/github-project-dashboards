"""Solara app package.

When Solara imports this module it looks for a `routes` attribute first.
We expose one by generating routes from the pages/ directory so Solara
does not try to recurse through components/, state.py, theme.py, etc.

The `Layout` component here is picked up by Solara and used to wrap every page.
"""

from __future__ import annotations
from pathlib import Path

import solara
import solara.lab

from app import state

# Tell Solara exactly where the pages live.
routes = solara.generate_routes_directory(Path(__file__).parent / "pages")


@solara.component
def Layout(children: list = []):
    project = state.current_project.value
    project_title = (project or {}).get("title", "")
    project_id = (project or {}).get("project_id", "")

    router = solara.use_router()

    def handle_pending_nav():
        route = state.pending_route.value
        if route:
            state.pending_route.value = ""
            router.push(route)

    solara.use_effect(handle_pending_nav, [state.pending_route.value])

    solara.Title("GitHub Projects Dashboard")
    with solara.AppBar():
        pass

    with solara.Sidebar():
        with solara.Column(gap="0px", style="padding: 8px 0;"):
            if project_title:
                solara.Text(
                    project_title,
                    style=(
                        "padding: 8px 16px 4px 16px; font-weight: 600; font-size: 0.83rem; "
                        "color: var(--color-fg-muted); word-break: break-word;"
                    ),
                )

            # Projects link
            with solara.Link("/"):
                solara.Button(
                    "Projects",
                    text=True,
                    style="width: 100%; justify-content: flex-start; padding: 6px 16px; font-size: 0.9rem;",
                )

            if project_id:
                # Overview
                with solara.Link("/overview"):
                    solara.Button(
                        "Overview",
                        text=True,
                        style="width: 100%; justify-content: flex-start; padding: 6px 16px; font-size: 0.9rem;",
                    )

                # Roadmaps section header
                solara.Text(
                    "Roadmaps",
                    style=(
                        "padding: 10px 16px 2px 16px; font-size: 0.72rem; font-weight: 600; "
                        "color: var(--color-fg-muted); text-transform: uppercase; letter-spacing: 0.06em;"
                    ),
                )

                # Current roadmap
                with solara.Link("/roadmaps"):
                    solara.Button(
                        "Current",
                        text=True,
                        style=(
                            "width: 100%; justify-content: flex-start; "
                            "padding: 4px 16px 4px 24px; font-size: 0.88rem;"
                        ),
                    )

                # V1: snapshot and proposal subtabs will be rendered here
                # by iterating store.list_snapshots(project_id) and
                # store.list_proposals(project_id).

    # Page content
    solara.Column(
        children=children,
        style="flex: 1 1 auto; width: 100%; min-width: 0; max-width: none; align-self: stretch;",
    )
