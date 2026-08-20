"""Tests for core.timeline item normalisation helpers."""

from unittest.mock import patch

from core.timeline import _fetch_timelines_parallel, _normalise_project_item, read_local


def test_read_local_requires_all_cache_files(tmp_path, monkeypatch):
    from core import store

    monkeypatch.setattr(store, "_ROOT", tmp_path)
    assert read_local("proj") is None

    store.write_cache("proj", "items", {"I_1": {"id": "I_1"}})
    assert read_local("proj") is None

    store.write_cache("proj", "timelines", {"I_1": []})
    assert read_local("proj") is None

    store.write_cache("proj", "field_values", {"I_1": {}})
    local = read_local("proj")
    assert local is not None
    assert set(local) == {"items", "timelines", "field_values"}
    assert local["items"]["I_1"]["id"] == "I_1"


def test_read_local_syncs_project_status_from_status_field(tmp_path, monkeypatch):
    from core import store

    monkeypatch.setattr(store, "_ROOT", tmp_path)
    store.write_cache(
        "proj",
        "items",
        {"I_1": {"id": "I_1", "project_status": "Todo"}},
    )
    store.write_cache("proj", "timelines", {"I_1": []})
    store.write_cache(
        "proj",
        "field_values",
        {"I_1": {"Status": {"value": "In Progress", "updatedAt": "2026-08-19T00:00:00Z"}}},
    )
    local = read_local("proj")
    assert local is not None
    assert local["items"]["I_1"]["project_status"] == "In Progress"


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


def test_fetch_timelines_parallel_returns_all_results():
    def fake_fetch(issue_id: str):
        return [{"kind": "closed", "at": "2026-01-01T00:00:00Z", "from_": None, "to": "COMPLETED", "issue_id": issue_id}]

    with patch("core.timeline._fetch_timeline", side_effect=fake_fetch):
        results = _fetch_timelines_parallel(["I_1", "I_2", "I_3", "I_4", "I_5"])

    assert set(results) == {"I_1", "I_2", "I_3", "I_4", "I_5"}
    assert all(results[i][0]["issue_id"] == i for i in results)


def test_fetch_timelines_parallel_single_id_skips_pool():
    with patch("core.timeline._fetch_timeline", return_value=[]) as mock_fetch:
        with patch("core.timeline.ThreadPoolExecutor") as mock_pool:
            results = _fetch_timelines_parallel(["I_only"])
    assert results == {"I_only": []}
    mock_fetch.assert_called_once_with("I_only")
    mock_pool.assert_not_called()


def test_fetch_timelines_parallel_caps_workers_at_four():
    from concurrent.futures import Future

    with patch("core.timeline._fetch_timeline", return_value=[]):
        with patch("core.timeline.ThreadPoolExecutor") as mock_pool:
            def submit(fn, iid):
                fut = Future()
                fut.set_result(fn(iid))
                return fut

            mock_pool.return_value.__enter__.return_value.submit = submit
            _fetch_timelines_parallel([f"I_{i}" for i in range(10)])
            mock_pool.assert_called_once_with(max_workers=4)
