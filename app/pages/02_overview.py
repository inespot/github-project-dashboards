"""Overview page — burn-up chart, weighted progress, and activity lists."""

from __future__ import annotations

import threading
from datetime import date, timedelta
from typing import Any

import solara

from app import state
from app.components.charts import BurnupChart, ProgressByParent, ProgressSummary
from app.components.empty_state import NoProjectSelected
from app.components.selectors import MilestoneSelect, ActivityWindowSelect, ContributorsSelect
from core import activity as activity_mod, people, progress as progress_mod, prs_in_review as prs_in_review_mod, reconstruct, reviews as reviews_mod, roadmap as roadmap_mod, series as series_mod, store
from core.time import utc_today


_EMPTY_PROGRESS = {
    "total_estimate": 0.0,
    "weighted_done": 0.0,
    "percent": 0.0,
    "by_parent": [],
}

_OVERVIEW_CACHE_VERSION = "utc_v23_prs_author_col"

_CARD_STYLE = (
    "padding: 12px 14px; border: 1px solid var(--color-border); "
    "border-radius: 8px; background: var(--color-canvas-subtle); "
    "width: 100%; height: 100%; box-sizing: border-box;"
)

_HALF_CARD = "flex: 1 1 calc(50% - 6px); min-width: 140px;"


def _cached(key: tuple[object, ...], factory):
    return state.overview_cache_get_or_set(key, factory)


def _review_awards_cache_key(project_id: str) -> tuple[object, ...]:
    return ("review_awards", _OVERVIEW_CACHE_VERSION, project_id)


def _review_awards_live_key(project_id: str) -> tuple[object, ...]:
    """Set once a live awards refresh is in-flight or finished for this cache gen."""
    return ("review_awards_live", _OVERVIEW_CACHE_VERSION, project_id)


def _resolve_review_awards(project_id: str) -> list[dict[str, Any]] | None:
    """Memory cache, then disk — so UI never sticks on Loading when reviews.json exists."""
    if not project_id:
        return None
    cache_key = _review_awards_cache_key(project_id)
    if cache_key in state.overview_cache:
        return state.overview_cache[cache_key]
    local = reviews_mod.read_local_awards(project_id)
    if local is not None:
        state.overview_cache[cache_key] = local
        return local
    return None


_RATE_LIMIT_CACHE_WARNING = (
    "GitHub rate limits reached. Using data from disk cache only."
)


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
    start_field = config.get("start_field", "")
    end_field = config.get("end_field", "")

    def load_data():
        if not project_id or state.project_data.value is not None or state.loading.value:
            return

        from core import timeline as tl

        # Show disk cache immediately (if complete), then refresh from GitHub.
        local = tl.read_local(project_id)
        if local is not None:
            state.project_data.value = local

        state.loading.value = True
        state.error.value = None
        state.warning.value = None

        def run():
            try:
                from core import github as gh
                from core import timeline as tl

                # If quota is gone, stay on disk cache instead of hanging/failing.
                if not gh.has_budget(30):
                    if local is None:
                        state.error.value = _RATE_LIMIT_CACHE_WARNING
                    else:
                        state.warning.value = _RATE_LIMIT_CACHE_WARNING
                    return
                result = tl.load(project_id, org, number)
                state.clear_overview_cache()
                state.project_data.value = result
                state.warning.value = None
            except Exception as e:
                if local is None:
                    state.error.value = str(e)
                else:
                    state.warning.value = _RATE_LIMIT_CACHE_WARNING
            finally:
                state.loading.value = False

        threading.Thread(target=run, daemon=True).start()

    solara.use_effect(load_data, [project_id])  # noqa: SH101

    data = state.project_data.value
    loading = state.loading.value
    error = state.error.value
    warning = state.warning.value
    items = data["items"] if data else {}
    timelines = data["timelines"] if data else {}
    field_values = data["field_values"] if data else {}
    milestone = state.selected_milestone.value
    prs_ready = state.overview_prs_ready.value
    pr_by_issue = state.overview_cache.get(("prs", project_id))

    def prefetch_overview_prs():
        if data is None or not project_id:
            return
        if ("prs", project_id) in state.overview_cache:
            return

        def run():
            from core import github as gh

            try:
                # PR progress is nice-to-have; stay on Status-only when quota is low.
                if not gh.has_budget(80):
                    state.overview_cache[("prs", project_id)] = {}
                    state.warning.value = _RATE_LIMIT_CACHE_WARNING
                else:
                    ids = progress_mod.open_issue_ids_needing_prs(items)
                    state.overview_cache[("prs", project_id)] = progress_mod.prefetch_prs(ids)
            except Exception:
                state.overview_cache[("prs", project_id)] = {}
                state.warning.value = _RATE_LIMIT_CACHE_WARNING
            state.overview_prs_ready.value = state.overview_prs_ready.value + 1

        threading.Thread(target=run, daemon=True).start()

    solara.use_effect(
        prefetch_overview_prs,
        [project_id, id(data) if data is not None else 0],
    )  # noqa: SH101

    def prefetch_review_awards():
        if data is None or not project_id:
            return
        cache_key = _review_awards_cache_key(project_id)
        live_key = _review_awards_live_key(project_id)

        # Paint from disk immediately so awards aren't blank while we refresh.
        if cache_key not in state.overview_cache:
            local_awards = reviews_mod.read_local_awards(project_id)
            if local_awards is not None:
                state.overview_cache[cache_key] = local_awards
                state.overview_reviews_ready.value = state.overview_reviews_ready.value + 1

        # Wait until timeline load/refresh finishes so we don't double-fetch
        # (startup local paint + post-load) and we use the latest items.
        if state.loading.value:
            return
        if live_key in state.overview_cache:
            return

        # Claim the live slot before starting the thread (effect may re-enter).
        state.overview_cache[live_key] = "pending"

        def run():
            from core import github as gh

            try:
                if not gh.has_budget(100):
                    # Keep disk/memory awards; skip network this round.
                    if cache_key not in state.overview_cache:
                        state.overview_cache[cache_key] = []
                    state.warning.value = _RATE_LIMIT_CACHE_WARNING
                    state.overview_cache[live_key] = False
                else:
                    awards = reviews_mod.review_awards(
                        items, project_id=project_id, force=True
                    )
                    state.overview_cache[cache_key] = awards
                    state.overview_cache[live_key] = True
            except Exception:
                local = reviews_mod.read_local_awards(project_id)
                if local is not None:
                    state.overview_cache[cache_key] = local
                elif cache_key not in state.overview_cache:
                    state.overview_cache[cache_key] = []
                    state.warning.value = _RATE_LIMIT_CACHE_WARNING
                state.overview_cache[live_key] = False
            state.overview_reviews_ready.value = state.overview_reviews_ready.value + 1

        threading.Thread(target=run, daemon=True).start()

    solara.use_effect(
        prefetch_review_awards,
        [project_id, id(data) if data is not None else 0, loading],
    )  # noqa: SH101

    def prefetch_prs_in_review():
        if data is None or not project_id:
            return
        cache_key = (
            "prs_in_review",
            _OVERVIEW_CACHE_VERSION,
            project_id,
            milestone,
        )
        live_key = (
            "prs_in_review_live",
            _OVERVIEW_CACHE_VERSION,
            project_id,
            milestone,
        )
        if state.loading.value:
            return
        if live_key in state.overview_cache:
            return

        state.overview_cache[live_key] = "pending"

        def run():
            from core import github as gh

            try:
                if not gh.has_budget(80):
                    state.overview_cache[cache_key] = []
                    state.warning.value = _RATE_LIMIT_CACHE_WARNING
                    state.overview_cache[live_key] = False
                else:
                    state.overview_cache[cache_key] = prs_in_review_mod.list_prs_in_review(
                        items, milestone
                    )
                    state.overview_cache[live_key] = True
            except Exception:
                if cache_key not in state.overview_cache:
                    state.overview_cache[cache_key] = []
                state.warning.value = _RATE_LIMIT_CACHE_WARNING
                state.overview_cache[live_key] = False
            state.overview_prs_in_review_ready.value = (
                state.overview_prs_in_review_ready.value + 1
            )

        threading.Thread(target=run, daemon=True).start()

    solara.use_effect(
        prefetch_prs_in_review,
        [project_id, id(data) if data is not None else 0, loading, milestone],
    )  # noqa: SH101

    progress_data = (
        _cached(
            (
                _OVERVIEW_CACHE_VERSION,
                "progress",
                project_id,
                milestone,
                estimate_field,
                prs_ready,
            ),
            lambda: progress_mod.weighted_progress_for_milestone(
                milestone,
                items,
                estimate_field,
                field_values,
                pr_by_issue=pr_by_issue,
                live_prs=False,
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
            if data is None:
                solara.Text("Fetching issues and timelines…", style="color: var(--color-fg-muted);")
                return
            solara.Text(
                "Refreshing issues and timelines…",
                style="color: var(--color-fg-muted); margin-bottom: 8px;",
            )
        elif data is not None and pr_by_issue is None:
            solara.ProgressLinear(True)
            solara.Text(
                "Refresh in Progress…",
                style="color: var(--color-fg-muted); margin-bottom: 8px;",
            )

        if error and data is None:
            solara.Text(f"Error: {error}", style="color: var(--color-critical, #d03b3b);")
            return

        if data is None:
            return

        if error:
            solara.Text(
                error,
                style="color: var(--color-critical, #d03b3b); margin-bottom: 8px;",
            )
        if warning:
            solara.Text(
                warning,
                style="color: #9a6700; margin-bottom: 8px;",
            )
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
                _ActivitySection(
                    project_id,
                    milestone,
                    items,
                    timelines,
                    field_values,
                    estimate_field,
                    progress_data,
                    state.overview_cache.get(
                        ("prs_in_review", _OVERVIEW_CACHE_VERSION, project_id, milestone)
                    ),
                    state.overview_prs_in_review_ready.value,
                )

            with solara.Column(
                gap="12px",
                style=(
                    "flex: 0 0 calc(45% - 12px); width: calc(45% - 12px); "
                    "max-width: calc(45% - 12px); min-width: 320px; align-self: stretch;"
                ),
            ):
                with solara.Row(
                    gap="12px",
                    style="width: 100%; align-items: stretch; flex-wrap: wrap;",
                ):
                    with solara.Column(style=_HALF_CARD):
                        with solara.Column(style=_CARD_STYLE):
                            ProgressSummary(progress_data, estimate_field)
                    with solara.Column(style=_HALF_CARD):
                        _WorkdaysCard(project_id, milestone, items)

                with solara.Row(
                    gap="12px",
                    style="width: 100%; align-items: stretch; flex-wrap: wrap;",
                ):
                    with solara.Column(style=_HALF_CARD):
                        _RoadmapDeltaCard(
                            project_id,
                            milestone,
                            start_field,
                            end_field,
                            items,
                            field_values,
                            pr_by_issue,
                            prs_ready,
                        )
                    with solara.Column(style=_HALF_CARD):
                        _EstimatedDaysCard(
                            project_id,
                            milestone,
                            estimate_field,
                            items,
                            timelines,
                            field_values,
                            progress_data,
                            contributors,
                        )

                solara.HTML(tag="div", style="height: 16px;")
                _BurnupSection(
                    project_id,
                    milestone,
                    estimate_field,
                    items,
                    timelines,
                    field_values,
                    _resolve_review_awards(project_id),
                    state.overview_reviews_ready.value,
                )


@solara.component
def _BurnupSection(
    project_id,
    milestone,
    estimate_field,
    items,
    timelines,
    field_values,
    review_awards,
    reviews_ready,
):
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
    with solara.Column(gap="0px", style=_CARD_STYLE):
        solara.Text(
            f"Burn-up — {milestone_label}",
            style=(
                "font-size: 0.88rem; font-weight: 600; color: var(--color-fg-default); "
                "margin-bottom: 12px;"
            ),
        )
        BurnupChart(rows, height=420)
        solara.HTML(tag="div", style="height: 14px;")
        _ReviewAwards(review_awards, reviews_ready)


@solara.component
def _ReviewAwards(review_awards: list[dict[str, Any]] | None, reviews_ready: int):
    """Leaderboard of formal PR reviewers for this project."""
    del reviews_ready  # dependency for re-render when background fetch completes
    with solara.Column(gap="4px", style="margin-top: 0; width: 100%;"):
        solara.Text(
            "Project reviews awards 🏆",
            style=(
                "font-size: 0.85rem; font-weight: 600; color: var(--color-fg-muted);"
            ),
        )
        solara.HTML(tag="div", style="height: 6px;")
        if review_awards is None:
            solara.Text(
                "Loading…",
                style="font-size: 0.78rem; color: var(--color-fg-muted); font-style: italic;",
            )
            return
        if not review_awards:
            solara.Text(
                "No reviews yet.",
                style="font-size: 0.78rem; color: var(--color-fg-muted); font-style: italic;",
            )
            return
        for i in range(0, len(review_awards), 3):
            with solara.Row(
                gap="12px",
                style="width: 100%; align-items: baseline;",
            ):
                for row in review_awards[i : i + 3]:
                    with solara.Column(style="flex: 1 1 0; min-width: 0;"):
                        solara.Text(
                            f"{row['name']} · {row['count']}",
                            style="font-size: 0.78rem; color: var(--color-fg-default);",
                        )
                # Keep columns aligned when the last row has fewer than 3 people.
                for _ in range(3 - len(review_awards[i : i + 3])):
                    solara.HTML(tag="div", style="flex: 1 1 0; min-width: 0;")


@solara.component
def _ActivitySection(
    project_id,
    milestone,
    items,
    timelines,
    field_values,
    estimate_field,
    progress_data,
    prs_in_review,
    prs_in_review_ready,
):
    del prs_in_review_ready  # dependency for re-render when background fetch completes
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
    in_progress = _cached(
        (_OVERVIEW_CACHE_VERSION, "activity_in_progress", project_id, milestone),
        lambda: activity_mod.currently_in_progress(milestone, items, timelines),
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
                _IssueRow(issue, estimate_field=estimate_field, field_values=field_values)
            if len(added) > 10:
                solara.Text(f"…and {len(added) - 10} more", style="color: var(--color-fg-muted); font-size: 0.82rem;")
        else:
            solara.Text("None in this window.", style="color: var(--color-fg-muted); font-size: 0.85rem;")

        solara.HTML(tag="div", style="margin: 12px 0;")

        solara.Text(
            f"Completed Tasks ({len(completed)}) 🎉",
            style="font-weight: 600; margin-bottom: 4px;",
        )
        if completed:
            for issue in completed[:10]:
                _IssueRow(
                    issue,
                    estimate_field=estimate_field,
                    field_values=field_values,
                    show_assignee=True,
                )
            if len(completed) > 10:
                solara.Text(f"…and {len(completed) - 10} more", style="color: var(--color-fg-muted); font-size: 0.82rem;")
        else:
            solara.Text("None in this window.", style="color: var(--color-fg-muted); font-size: 0.85rem;")

        solara.HTML(tag="div", style="margin: 12px 0;")

        solara.Text(
            f"In Progress Tasks ({len(in_progress)})",
            style="font-weight: 600; margin-bottom: 4px;",
        )
        if in_progress:
            for issue in in_progress:
                _InProgressRow(issue)
        else:
            solara.Text("None.", style="color: var(--color-fg-muted); font-size: 0.85rem;")

        solara.HTML(tag="div", style="margin: 12px 0;")

        _PrsInReviewSection(prs_in_review)

        solara.HTML(tag="div", style="margin: 16px 0 8px 0;")
        ProgressByParent(progress_data, estimate_field)


@solara.component
def _PrsInReviewSection(prs_in_review: list[dict[str, Any]] | None):
    count = len(prs_in_review) if prs_in_review else 0

    def _esc(s: str) -> str:
        return (
            s.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    title_html = (
        f'<div style="font-weight:600;margin-bottom:4px;">'
        f"PRs in Review ({count})</div>"
    )

    if prs_in_review is None:
        body = (
            '<div style="color:var(--color-fg-muted);font-size:0.85rem;'
            'font-style:italic;">Loading…</div>'
        )
    elif not prs_in_review:
        body = (
            '<div style="color:var(--color-fg-muted);font-size:0.85rem;">None.</div>'
        )
    else:
        rows_html: list[str] = []
        for pr in prs_in_review:
            url = pr.get("url", "") or "#"
            number = pr.get("number", "")
            title = pr.get("title", "")
            author_label = pr.get("author_label") or "—"
            reviewers_label = pr.get("reviewers_label") or "Needs reviewer"
            pending_on = pr.get("pending_on") or "Pending on reviewer"
            draft_suffix = " (draft)" if pr.get("is_draft") else ""
            number_label = f"#{number}" if number is not None and number != "" else "PR"
            title_label = f"{title}{draft_suffix}"
            rows_html.append(
                '<div style="display:flex;align-items:center;gap:8px;flex-wrap:nowrap;'
                "padding:3px 0;border-bottom:1px solid var(--color-border);"
                'width:100%;box-sizing:border-box;">'
                f'<a href="{_esc(url)}" target="_blank" '
                f'style="color:#0969da;text-decoration:none;flex:0 0 auto;">'
                f"{_esc(number_label)}</a>"
                f'<span style="font-size:0.85rem;flex:1 1 auto;min-width:0;'
                f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'
                f"{_esc(title_label)}</span>"
                f'<span style="font-size:0.78rem;color:var(--color-fg-muted);'
                f"width:100px;flex:0 0 100px;white-space:nowrap;overflow:hidden;"
                f'text-overflow:ellipsis;text-align:left;">'
                f"{_esc(author_label)}</span>"
                f'<span style="font-size:0.78rem;color:var(--color-fg-muted);'
                f"width:150px;flex:0 0 150px;white-space:nowrap;overflow:hidden;"
                f'text-overflow:ellipsis;text-align:left;">'
                f"{_esc(reviewers_label)}</span>"
                f'<span style="font-size:0.78rem;color:var(--color-fg-muted);'
                f"width:110px;flex:0 0 110px;white-space:nowrap;overflow:hidden;"
                f'text-overflow:ellipsis;text-align:left;">'
                f"{_esc(pending_on)}</span>"
                "</div>"
            )
        body = "".join(rows_html)

    # Title + body in one widget so Solara doesn't insert gap between them
    # (In Progress title/rows are adjacent Solara children with only 4px margin).
    solara.HTML(
        tag="div",
        unsafe_innerHTML=title_html + body,
        attributes={"style": "width:100%;min-height:0;"},
    )


@solara.component
def _IssueRow(
    issue: dict[str, Any],
    estimate_field: str = "",
    field_values: dict[str, Any] | None = None,
    show_assignee: bool = False,
):
    url = issue.get("url", "")
    number = issue.get("number", "")
    title = issue.get("title", "")
    at = (issue.get("at") or "")[:10]
    assignee_label = people.format_assignees(issue.get("assignees") or [])
    show_estimate = bool(estimate_field and field_values is not None)
    estimate_label = ""
    if show_estimate:
        issue_id = issue.get("id")
        if issue_id:
            entry = (field_values.get(issue_id) or {}).get(estimate_field)
            value = entry.get("value") if entry else None
            if value is not None:
                estimate_label = f"{float(value):.1f} days"
    number_label = f"#{number}" if number is not None and number != "" else "Item"
    meta_style = (
        "font-size: 0.78rem; color: var(--color-fg-muted); "
        "white-space: nowrap; text-align: left;"
    )

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
                "font-size: 0.85rem; flex: 1 1 auto; min-width: 0; "
                "white-space: nowrap; overflow: hidden; text-overflow: ellipsis;"
            ),
        )
        if show_assignee:
            solara.Text(assignee_label, style=f"{meta_style} width: 120px;")
        solara.Text(at, style=f"{meta_style} width: 88px;")
        if show_estimate:
            solara.Text(estimate_label, style=f"{meta_style} width: 72px;")


@solara.component
def _InProgressRow(issue: dict[str, Any]):
    url = issue.get("url", "")
    number = issue.get("number", "")
    title = issue.get("title", "")
    assignee_label = people.format_assignees(issue.get("assignees") or [])
    since = (issue.get("at") or "")[:10]
    since_label = f"since {since}" if since else "since —"
    number_label = f"#{number}" if number is not None and number != "" else "Item"
    meta_style = (
        "font-size: 0.78rem; color: var(--color-fg-muted); "
        "white-space: nowrap; text-align: left;"
    )

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
                "font-size: 0.85rem; flex: 1 1 auto; min-width: 0; "
                "white-space: nowrap; overflow: hidden; text-overflow: ellipsis;"
            ),
        )
        solara.Text(assignee_label, style=f"{meta_style} width: 120px;")
        solara.Text(since_label, style=f"{meta_style} width: 110px;")


@solara.component
def _RoadmapDeltaCard(
    project_id,
    milestone,
    start_field,
    end_field,
    items,
    field_values,
    pr_by_issue,
    prs_ready,
):
    roadmap_delta = None
    if milestone not in (None, "all"):
        roadmap_delta = _cached(
            (
                _OVERVIEW_CACHE_VERSION,
                "roadmap_delta",
                project_id,
                milestone,
                start_field,
                end_field,
                utc_today().isoformat(),
                prs_ready,
            ),
            lambda: roadmap_mod.roadmap_delta_days(
                milestone,
                items,
                field_values,
                start_field,
                end_field,
                utc_today(),
                pr_by_issue=pr_by_issue,
                live_prs=False,
            ),
        )
    roadmap_delta_label = _format_signed_days(roadmap_delta)
    roadmap_delta_color = _roadmap_delta_color(roadmap_delta)

    with solara.Column(gap="4px", style=_CARD_STYLE):
        solara.Text(
            "Roadmap delta (days)",
            style="font-size: 0.78rem; font-weight: 600; color: var(--color-fg-muted);",
        )
        solara.Markdown(
            "_Compares #workdays owed (issues with end < today) with "
            "#workdays earned (completed + progress on open overdue issues)_",
            style="font-size: 0.72rem; color: var(--color-fg-muted); margin: 0 0 2px 0; line-height: 1.35;",
        )
        solara.Text(
            roadmap_delta_label,
            style=f"font-size: 1.5rem; font-weight: 600; color: {roadmap_delta_color};",
        )
        if milestone in (None, "all"):
            solara.Text(
                "Select a milestone",
                style="font-size: 0.78rem; color: var(--color-fg-muted);",
            )


@solara.component
def _WorkdaysCard(project_id, milestone, items):
    workdays_left = None
    due_on = None
    if milestone not in (None, "all"):
        milestone_meta = _cached(
            (_OVERVIEW_CACHE_VERSION, "milestone_meta", project_id, milestone),
            lambda: _milestone_metadata(milestone, items),
        )
        if milestone_meta is not None:
            due_on = milestone_meta.get("dueOn")
            workdays_left = _workdays_until(due_on[:10] if due_on else None)

    with solara.Column(style=_CARD_STYLE):
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
                style="font-size: 0.78rem;",
            )
        else:
            solara.Text(
                "Select a milestone",
                style="font-size: 0.78rem; color: var(--color-fg-muted);",
            )


@solara.component
def _EstimatedDaysCard(
    project_id,
    milestone,
    estimate_field,
    items,
    timelines,
    field_values,
    progress_data,
    contributors,
):
    if milestone in (None, "all"):
        with solara.Column(style=_CARD_STYLE):
            solara.Text(
                "Estimated task days left",
                style="font-size: 0.78rem; font-weight: 600; color: var(--color-fg-muted);",
            )
            solara.Text("—", style="font-size: 1.5rem; font-weight: 600;")
            solara.Text(
                "Select a milestone",
                style="font-size: 0.78rem; color: var(--color-fg-muted);",
            )
        return

    open_estimated_days = _cached(
        (_OVERVIEW_CACHE_VERSION, "open_estimated_days", project_id, milestone, estimate_field),
        lambda: _open_estimated_days(milestone, estimate_field, items, timelines, field_values),
    )
    estimated_days_left = max(
        0.0, progress_data.get("total_estimate", 0.0) - progress_data.get("done", 0.0)
    )
    contributors_count = int(contributors) if contributors else 0
    fifty_precent_rule_days = estimated_days_left * 2
    days_per_participant = (
        fifty_precent_rule_days / contributors_count if contributors_count else 0.0
    )

    milestone_meta = _cached(
        (_OVERVIEW_CACHE_VERSION, "milestone_meta", project_id, milestone),
        lambda: _milestone_metadata(milestone, items),
    )
    due_on = (milestone_meta or {}).get("dueOn")
    workdays_left = _workdays_until(due_on[:10] if due_on else None)
    days_per_participant_color = _days_per_participant_color(days_per_participant, workdays_left)

    with solara.Column(style=_CARD_STYLE):
        solara.Text(
            "Estimated task days left",
            style="font-size: 0.78rem; font-weight: 600; color: var(--color-fg-muted);",
        )
        solara.Text(f"{estimated_days_left:.1f}", style="font-size: 1.5rem; font-weight: 600;")
        solara.Text(
            f"{open_estimated_days:.1f} open · {fifty_precent_rule_days:.1f} with 50% rule",
            style="font-size: 0.78rem; color: var(--color-fg-muted);",
        )
        solara.HTML(
            tag="div",
            unsafe_innerHTML=(
                f"<span style='color: {days_per_participant_color}; font-weight: 600;'>"
                f"{days_per_participant:.1f}</span> "
                f"<span style='color: var(--color-fg-muted);'>per contributor</span>"
            ),
            style="font-size: 0.78rem;",
        )


def _milestone_metadata(milestone: str, items: dict[str, Any]) -> dict[str, Any] | None:
    for item in items.values():
        milestone_meta = item.get("milestone")
        if milestone_meta and milestone_meta.get("title") == milestone:
            return milestone_meta
    return None


def _issue_estimate(
    issue: dict[str, Any],
    estimate_field: str,
    field_values: dict[str, Any],
) -> float | None:
    if not estimate_field:
        return None
    issue_id = issue.get("id")
    if not issue_id:
        return None
    entry = (field_values.get(issue_id) or {}).get(estimate_field)
    value = entry.get("value") if entry else None
    if value is None:
        return None
    return float(value)


def _sum_estimates(issues: list[dict[str, Any]], estimate_field: str, field_values: dict[str, Any]) -> float:
    total = 0.0
    for issue in issues:
        value = _issue_estimate(issue, estimate_field, field_values)
        if value is not None:
            total += value
    return total


def _open_estimated_days(milestone: str, estimate_field: str, items: dict[str, Any], timelines: dict[str, Any], field_values: dict[str, Any]) -> float:
    total = 0.0
    at = utc_today().isoformat() + "T23:59:59Z"
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


def _format_signed_days(value: int | None) -> str:
    if value is None:
        return "—"
    if value > 0:
        return f"+{value}"
    return str(value)


def _roadmap_delta_color(value: int | None) -> str:
    if value is None:
        return "var(--color-fg-default)"
    if value >= 0:
        return "#0ca30c"  # green — on track / ahead
    if value >= -5:
        return "#fab219"  # orange — mild delay
    return "#d03b3b"  # red — more than 5 days behind


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def _refresh(project_id, org, number):
    # Keep showing the current data while refresh runs.
    state.loading.value = True
    state.error.value = None
    state.warning.value = None

    def run():
        try:
            from core import github as gh
            from core import timeline as tl

            # Hard refresh (force=True) refetches every timeline and will blow
            # through the quota. Use incremental refresh; skip entirely if
            # nearly exhausted so the UI keeps working from cache.
            if not gh.has_budget(50):
                state.warning.value = _RATE_LIMIT_CACHE_WARNING
                return

            result = tl.load(project_id, org, number, force=False)
            state.clear_overview_cache()
            state.project_data.value = result
            state.warning.value = None
        except Exception:
            state.warning.value = _RATE_LIMIT_CACHE_WARNING
        finally:
            state.loading.value = False

    threading.Thread(target=run, daemon=True).start()
