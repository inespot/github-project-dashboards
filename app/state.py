"""Application-level reactive state.

Kept module-level to avoid Solara hook ordering issues.
All values that need to survive navigation live here.
"""

from __future__ import annotations

from typing import Any, Callable, Hashable

import solara

# The project the user is currently viewing.
# {project_id, title, org, number, config}
current_project: solara.Reactive[dict[str, Any] | None] = solara.reactive(None)

# Cached data for the current project, loaded once per session (or on refresh).
# {items, timelines, field_values}
project_data: solara.Reactive[dict[str, Any] | None] = solara.reactive(None)

# Loading / error state
loading: solara.Reactive[bool] = solara.reactive(False)
error: solara.Reactive[str | None] = solara.reactive(None)
# Soft notice when showing disk/cached data because a live fetch was skipped.
warning: solara.Reactive[str | None] = solara.reactive(None)

# Bumps when background PR prefetch for Overview finishes (forces re-render).
overview_prs_ready: solara.Reactive[int] = solara.reactive(0)
# Bumps when background review-awards fetch finishes.
overview_reviews_ready: solara.Reactive[int] = solara.reactive(0)

# Overview filters
selected_milestone: solara.Reactive[str] = solara.reactive("all")
activity_window_days: solara.Reactive[int] = solara.reactive(7)
contributors_count: solara.Reactive[str] = solara.reactive("1")

# Cached expensive overview derivations so route switches do not rebuild them.
overview_cache: dict[tuple[Hashable, ...], Any] = {}

# Navigation signal: set to a path string to trigger a router.push from the
# component rendering context (not from a background thread, which won't work).
pending_route: solara.Reactive[str] = solara.reactive("")

# Which roadmap view is shown: "current" or a snapshot label ("YYYY-MM-DD").
roadmap_view: solara.Reactive[str] = solara.reactive("current")


def clear_overview_cache() -> None:
    overview_cache.clear()
    overview_prs_ready.value = 0
    overview_reviews_ready.value = 0


def overview_cache_get_or_set(key: tuple[Hashable, ...], factory: Callable[[], Any]) -> Any:
    if key not in overview_cache:
        overview_cache[key] = factory()
    return overview_cache[key]


def clear_project() -> None:
    current_project.value = None
    project_data.value = None
    error.value = None
    warning.value = None
    selected_milestone.value = "all"
    contributors_count.value = "1"
    clear_overview_cache()
