"""Local data store.

Manages the data/ directory. Structure:

    data/
      projects.json
      <org>-<number>/
        config.json
        cache/
          timelines.json
          items.json
        snapshots/
          YYYY-MM-DD.json
        proposals/
          <label>.json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.time import utc_today_iso

_ROOT = Path("data")


def _projects_file() -> Path:
    _ROOT.mkdir(exist_ok=True)
    return _ROOT / "projects.json"


def list_projects() -> list[dict[str, Any]]:
    f = _projects_file()
    if not f.exists():
        return []
    return json.loads(f.read_text())


def save_project(project: dict[str, Any]) -> None:
    """Upsert a project into the registry by its id."""
    projects = list_projects()
    existing = {p["id"]: p for p in projects}
    existing[project["id"]] = project
    _projects_file().write_text(json.dumps(list(existing.values()), indent=2))


def project_dir(project_id: str) -> Path:
    d = _ROOT / project_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def read_config(project_id: str) -> dict[str, Any] | None:
    f = project_dir(project_id) / "config.json"
    if not f.exists():
        return None
    return json.loads(f.read_text())


def write_config(project_id: str, config: dict[str, Any]) -> None:
    f = project_dir(project_id) / "config.json"
    f.write_text(json.dumps(config, indent=2))


def cache_dir(project_id: str) -> Path:
    d = project_dir(project_id) / "cache"
    d.mkdir(exist_ok=True)
    return d


def read_cache(project_id: str, name: str) -> Any | None:
    f = cache_dir(project_id) / f"{name}.json"
    if not f.exists():
        return None
    return json.loads(f.read_text())


def write_cache(project_id: str, name: str, data: Any) -> None:
    f = cache_dir(project_id) / f"{name}.json"
    f.write_text(json.dumps(data, indent=2))



def snapshots_dir(project_id: str) -> Path:
    d = project_dir(project_id) / "snapshots"
    d.mkdir(exist_ok=True)
    return d


def list_snapshots(project_id: str) -> list[str]:
    """Return snapshot labels sorted newest first. Labels are file stems."""
    d = snapshots_dir(project_id)
    return sorted((f.stem for f in d.glob("*.json")), reverse=True)


def read_snapshot(project_id: str, label: str) -> dict[str, Any] | None:
    f = snapshots_dir(project_id) / f"{label}.json"
    if not f.exists():
        return None
    return json.loads(f.read_text())


def write_snapshot(project_id: str, label: str, data: dict[str, Any]) -> None:
    """Write a snapshot. Same-day writes overwrite."""
    f = snapshots_dir(project_id) / f"{label}.json"
    f.write_text(json.dumps(data, indent=2))


def delete_snapshot(project_id: str, label: str) -> None:
    """Delete a snapshot. Does not allow deleting 'current' (reserved label)."""
    if label == "current":
        raise ValueError("The 'current' snapshot cannot be deleted.")
    f = snapshots_dir(project_id) / f"{label}.json"
    if f.exists():
        f.unlink()


def today_label() -> str:
    return utc_today_iso()


def proposals_dir(project_id: str) -> Path:
    d = project_dir(project_id) / "proposals"
    d.mkdir(exist_ok=True)
    return d


def list_proposals(project_id: str) -> list[str]:
    """Return proposal labels sorted newest first."""
    d = proposals_dir(project_id)
    return sorted((f.stem for f in d.glob("*.json")), reverse=True)


def read_proposal(project_id: str, label: str) -> dict[str, Any] | None:
    f = proposals_dir(project_id) / f"{label}.json"
    if not f.exists():
        return None
    return json.loads(f.read_text())


def write_proposal(project_id: str, label: str, data: dict[str, Any]) -> None:
    f = proposals_dir(project_id) / f"{label}.json"
    f.write_text(json.dumps(data, indent=2))


def delete_proposal(project_id: str, label: str) -> None:
    f = proposals_dir(project_id) / f"{label}.json"
    if f.exists():
        f.unlink()
