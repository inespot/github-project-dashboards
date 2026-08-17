"""Fetch and cache issue timeline events for a project.

The cache is keyed on issue.updatedAt so only changed issues are re-fetched
on subsequent runs. Timeline events are immutable, so this cannot go stale.

Normalised output: list of Event dicts with keys:
  issue_id, at, kind, from_, to

'kind' values map directly to GraphQL event type names (snake-cased), e.g.:
  milestoned, demilestoned, closed, reopened, assigned, unassigned,
  labeled, unlabeled, added_to_project_v2, removed_from_project_v2,
  project_v2_item_status_changed, parent_issue_added, parent_issue_removed,
  sub_issue_added, sub_issue_removed
"""

from __future__ import annotations

import json
from typing import Any

from core import github, store

# ---------------------------------------------------------------------------
# GraphQL
# ---------------------------------------------------------------------------

_ITEMS_QUERY = """
query ProjectItems($org: String!, $number: Int!, $after: String) {
  rateLimit { remaining resetAt }
  organization(login: $org) {
    projectV2(number: $number) {
      items(first: 50, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          type
          createdAt
          updatedAt
          content {
            __typename
            ... on Issue {
              id
              number
              title
              url
              state
              stateReason
              createdAt
              closedAt
              milestone { title number dueOn }
              assignees(first: 20) { nodes { login } }
              labels(first: 30) { nodes { name } }
              parent {
                id
                number
                title
                milestone { title number dueOn }
              }
            }
            ... on DraftIssue {
              id
              title
              createdAt
              updatedAt
              assignees(first: 20) { nodes { login } }
            }
          }
          fieldValues(first: 30) {
            nodes {
              __typename
              ... on ProjectV2ItemFieldDateValue {
                field { ... on ProjectV2FieldCommon { name } }
                date
                updatedAt
              }
              ... on ProjectV2ItemFieldNumberValue {
                field { ... on ProjectV2FieldCommon { name } }
                number
                updatedAt
              }
              ... on ProjectV2ItemFieldSingleSelectValue {
                field { ... on ProjectV2FieldCommon { name } }
                name
                updatedAt
              }
              ... on ProjectV2ItemFieldMilestoneValue {
                field { ... on ProjectV2FieldCommon { name } }
                milestone { title number dueOn }
              }
              ... on ProjectV2ItemFieldTextValue {
                field { ... on ProjectV2FieldCommon { name } }
                text
                updatedAt
              }
            }
          }
        }
      }
    }
  }
}
"""

_TIMELINE_QUERY = """
query IssueTimeline($id: ID!, $after: String) {
  rateLimit { remaining resetAt }
  node(id: $id) {
    ... on Issue {
      timelineItems(first: 100, after: $after, itemTypes: [
        MILESTONED_EVENT, DEMILESTONED_EVENT,
        CLOSED_EVENT, REOPENED_EVENT,
        ASSIGNED_EVENT, UNASSIGNED_EVENT,
        LABELED_EVENT, UNLABELED_EVENT,
        ADDED_TO_PROJECT_V2_EVENT, REMOVED_FROM_PROJECT_V2_EVENT,
        PROJECT_V2_ITEM_STATUS_CHANGED_EVENT,
        PARENT_ISSUE_ADDED_EVENT, PARENT_ISSUE_REMOVED_EVENT,
        SUB_ISSUE_ADDED_EVENT, SUB_ISSUE_REMOVED_EVENT
      ]) {
        pageInfo { hasNextPage endCursor }
        nodes {
          __typename
          ... on MilestonedEvent { createdAt milestoneTitle }
          ... on DemilestonedEvent { createdAt milestoneTitle }
          ... on ClosedEvent { createdAt stateReason }
          ... on ReopenedEvent { createdAt }
          ... on AssignedEvent { createdAt assignee { ... on User { login } } }
          ... on UnassignedEvent { createdAt assignee { ... on User { login } } }
          ... on LabeledEvent { createdAt label { name } }
          ... on UnlabeledEvent { createdAt label { name } }
          ... on AddedToProjectV2Event { createdAt project { number } }
          ... on RemovedFromProjectV2Event { createdAt project { number } }
          ... on ProjectV2ItemStatusChangedEvent {
            createdAt previousStatus status
          }
          ... on ParentIssueAddedEvent {
            createdAt parent { number title }
          }
          ... on ParentIssueRemovedEvent {
            createdAt parent { number title }
          }
          ... on SubIssueAddedEvent {
            createdAt subIssue { number title }
          }
          ... on SubIssueRemovedEvent {
            createdAt subIssue { number title }
          }
        }
      }
    }
  }
}
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load(project_id: str, org: str, number: int, force: bool = False) -> dict[str, Any]:
    """Fetch or update the project item and timeline cache.

    Returns a dict:
      items: {issue_node_id: item_dict}
      timelines: {issue_node_id: [event_dict, ...]}
      field_values: {issue_node_id: {field_name: {value, updatedAt}}}
    """
    cached_items: dict[str, Any] = store.read_cache(project_id, "items") or {}
    cached_timelines: dict[str, Any] = store.read_cache(project_id, "timelines") or {}

    items: dict[str, Any] = {}
    field_values: dict[str, dict[str, Any]] = {}

    for node in github.paginate(
        _ITEMS_QUERY,
        {"org": org, "number": number},
        ["organization", "projectV2", "items"],
    ):
        if not node:
            continue

        item_id, item, fv, fetch_timeline = _normalise_project_item(node)
        if item_id is None or item is None:
            continue

        field_values[item_id] = fv
        items[item_id] = item

        # Re-fetch timelines only if the issue changed or we are forcing.
        if fetch_timeline:
            cached_updated = (cached_items.get(item_id) or {}).get("updatedAt", "")
            if force or item["updatedAt"] != cached_updated or item_id not in cached_timelines:
                cached_timelines[item_id] = _fetch_timeline(item_id)
        elif item_id not in cached_timelines or force:
            cached_timelines[item_id] = []

    timelines = {
        item_id: cached_timelines.get(item_id, [])
        for item_id in items
    }

    store.write_cache(project_id, "items", items)
    store.write_cache(project_id, "timelines", timelines)

    return {
        "items": items,
        "timelines": timelines,
        "field_values": field_values,
    }


def _normalise_project_item(
    node: dict[str, Any],
) -> tuple[str | None, dict[str, Any] | None, dict[str, Any], bool]:
    """Return `(item_id, item, field_values, fetch_timeline)` for a project item."""
    content = node.get("content") or {}
    content_type = content.get("__typename")
    updated_at = node.get("updatedAt", "")
    fv = _parse_field_values((node.get("fieldValues") or {}).get("nodes", []))
    milestone = content.get("milestone") or _milestone_from_field_values(fv)

    if content_type == "Issue":
        issue_id = content.get("id")
        if not issue_id:
            return None, None, fv, False
        return issue_id, {
            "id": issue_id,
            "kind": "issue",
            "number": content.get("number"),
            "title": content.get("title"),
            "url": content.get("url"),
            "state": content.get("state"),
            "stateReason": content.get("stateReason"),
            "createdAt": content.get("createdAt"),
            "closedAt": content.get("closedAt"),
            "milestone": milestone,
            "project_status": _status_from_field_values(fv),
            "assignees": [a["login"] for a in (content.get("assignees") or {}).get("nodes", [])],
            "labels": [l["name"] for l in (content.get("labels") or {}).get("nodes", [])],
            "parent": content.get("parent"),
            "updatedAt": updated_at,
        }, fv, True

    if content_type == "DraftIssue":
        draft_id = content.get("id")
        if not draft_id:
            return None, None, fv, False
        return draft_id, {
            "id": draft_id,
            "kind": "draft_issue",
            "number": None,
            "title": content.get("title"),
            "url": "",
            "state": "OPEN",
            "stateReason": None,
            "createdAt": content.get("createdAt"),
            "closedAt": None,
            "milestone": milestone,
            "project_status": _status_from_field_values(fv),
            "assignees": [a["login"] for a in (content.get("assignees") or {}).get("nodes", [])],
            "labels": [],
            "parent": None,
            "updatedAt": content.get("updatedAt") or updated_at,
        }, fv, False

    if node.get("type") == "ISSUE":
        item_id = node.get("id")
        if not item_id:
            return None, None, fv, False
        return item_id, {
            "id": item_id,
            "kind": "project_item_issue",
            "number": None,
            "title": _title_from_field_values(fv) or f"Project item {item_id[-6:]}",
            "url": "",
            "state": "OPEN",
            "stateReason": None,
            "createdAt": node.get("createdAt"),
            "closedAt": None,
            "milestone": milestone,
            "project_status": _status_from_field_values(fv),
            "assignees": _assignees_from_field_values(fv),
            "labels": [],
            "parent": None,
            "updatedAt": updated_at,
        }, fv, False

    return None, None, fv, False


def _parse_field_values(field_nodes: list[dict[str, Any]]) -> dict[str, Any]:
    fv: dict[str, Any] = {}
    for fv_node in field_nodes:
        if not fv_node or not fv_node.get("__typename"):
            continue
        field_name = (fv_node.get("field") or {}).get("name")
        if not field_name:
            continue

        typename = fv_node["__typename"]
        extra: dict[str, Any] = {}
        if typename == "ProjectV2ItemFieldDateValue":
            value = fv_node.get("date")
        elif typename == "ProjectV2ItemFieldNumberValue":
            value = fv_node.get("number")
        elif typename == "ProjectV2ItemFieldSingleSelectValue":
            value = fv_node.get("name")
        elif typename == "ProjectV2ItemFieldTextValue":
            value = fv_node.get("text")
        elif typename == "ProjectV2ItemFieldMilestoneValue":
            milestone = fv_node.get("milestone") or {}
            value = milestone.get("title")
            if value:
                extra["milestone"] = {
                    "title": milestone.get("title"),
                    "number": milestone.get("number"),
                    "dueOn": milestone.get("dueOn"),
                }
        else:
            continue

        fv[field_name] = {
            "value": value,
            "updatedAt": fv_node.get("updatedAt", ""),
            **extra,
        }
    return fv


def _milestone_from_field_values(fv: dict[str, Any]) -> dict[str, Any] | None:
    for entry in fv.values():
        milestone = entry.get("milestone")
        if milestone:
            return milestone
    return None


def _title_from_field_values(fv: dict[str, Any]) -> str | None:
    for field_name, entry in fv.items():
        if field_name.lower() == "title" and entry.get("value"):
            return entry["value"]
    return None


def _assignees_from_field_values(fv: dict[str, Any]) -> list[str]:
    assignees: list[str] = []
    for field_name, entry in fv.items():
        if field_name.lower() != "assignees":
            continue
        value = entry.get("value")
        if isinstance(value, list):
            assignees.extend(str(v) for v in value if v)
    return assignees


def _status_from_field_values(fv: dict[str, Any]) -> str | None:
    for field_name, entry in fv.items():
        if field_name.lower() == "status" and entry.get("value"):
            return str(entry["value"])
    return None


def _fetch_timeline(issue_id: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for node in github.paginate(
        _TIMELINE_QUERY,
        {"id": issue_id},
        ["node", "timelineItems"],
    ):
        event = _normalise(node)
        if event:
            events.append(event)
    return events


def _normalise(node: dict[str, Any]) -> dict[str, Any] | None:
    if not node:
        return None
    typename = node.get("__typename", "")
    at = node.get("createdAt", "")

    kind_map = {
        "MilestonedEvent": "milestoned",
        "DemilestonedEvent": "demilestoned",
        "ClosedEvent": "closed",
        "ReopenedEvent": "reopened",
        "AssignedEvent": "assigned",
        "UnassignedEvent": "unassigned",
        "LabeledEvent": "labeled",
        "UnlabeledEvent": "unlabeled",
        "AddedToProjectV2Event": "added_to_project_v2",
        "RemovedFromProjectV2Event": "removed_from_project_v2",
        "ProjectV2ItemStatusChangedEvent": "project_v2_status_changed",
        "ParentIssueAddedEvent": "parent_issue_added",
        "ParentIssueRemovedEvent": "parent_issue_removed",
        "SubIssueAddedEvent": "sub_issue_added",
        "SubIssueRemovedEvent": "sub_issue_removed",
    }
    kind = kind_map.get(typename)
    if not kind:
        return None

    from_: Any = None
    to: Any = None

    if typename in ("MilestonedEvent", "DemilestonedEvent"):
        to = node.get("milestoneTitle")
    elif typename == "ClosedEvent":
        to = node.get("stateReason")
    elif typename in ("AssignedEvent", "UnassignedEvent"):
        to = (node.get("assignee") or {}).get("login")
    elif typename in ("LabeledEvent", "UnlabeledEvent"):
        to = (node.get("label") or {}).get("name")
    elif typename == "ProjectV2ItemStatusChangedEvent":
        from_ = node.get("previousStatus")
        to = node.get("status")
    elif typename in ("AddedToProjectV2Event", "RemovedFromProjectV2Event"):
        to = (node.get("project") or {}).get("number")
    elif typename == "ParentIssueAddedEvent":
        to = (node.get("parent") or {}).get("number")
    elif typename == "ParentIssueRemovedEvent":
        from_ = (node.get("parent") or {}).get("number")
    elif typename == "SubIssueAddedEvent":
        to = (node.get("subIssue") or {}).get("number")
    elif typename == "SubIssueRemovedEvent":
        from_ = (node.get("subIssue") or {}).get("number")

    return {"kind": kind, "at": at, "from_": from_, "to": to}
