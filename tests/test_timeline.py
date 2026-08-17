"""Tests for core.timeline item normalisation helpers."""

from core.timeline import _normalise_project_item


def test_issue_item_uses_project_milestone_field_when_issue_milestone_missing():
    node = {
        "updatedAt": "2026-08-16T10:00:00Z",
        "content": {
            "__typename": "Issue",
            "id": "I_123",
            "number": 123,
            "title": "Investigate recovery throttling",
            "url": "https://example.test/issues/123",
            "state": "OPEN",
            "stateReason": None,
            "createdAt": "2026-08-01T00:00:00Z",
            "closedAt": None,
            "milestone": None,
            "assignees": {"nodes": [{"login": "alice"}]},
            "labels": {"nodes": [{"name": "team:distributed"}]},
            "parent": None,
        },
        "fieldValues": {
            "nodes": [
                {
                    "__typename": "ProjectV2ItemFieldMilestoneValue",
                    "field": {"name": "Milestone"},
                    "milestone": {"title": "9.3", "number": 3, "dueOn": None},
                },
            ],
        },
    }

    item_id, item, field_values, fetch_timeline = _normalise_project_item(node)

    assert item_id == "I_123"
    assert item is not None
    assert item["milestone"] == {"title": "9.3", "number": 3, "dueOn": None}
    assert field_values["Milestone"]["value"] == "9.3"
    assert fetch_timeline is True


def test_draft_issue_is_kept_as_project_item_without_timeline_fetch():
    node = {
        "updatedAt": "2026-08-16T10:00:00Z",
        "content": {
            "__typename": "DraftIssue",
            "id": "DI_456",
            "title": "Document rollout plan",
            "createdAt": "2026-08-10T00:00:00Z",
            "updatedAt": "2026-08-15T00:00:00Z",
            "assignees": {"nodes": [{"login": "bob"}]},
        },
        "fieldValues": {"nodes": []},
    }

    item_id, item, field_values, fetch_timeline = _normalise_project_item(node)

    assert item_id == "DI_456"
    assert item is not None
    assert item["kind"] == "draft_issue"
    assert item["state"] == "OPEN"
    assert item["title"] == "Document rollout plan"
    assert item["number"] is None
    assert field_values == {}
    assert fetch_timeline is False
