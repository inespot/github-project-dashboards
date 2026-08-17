"""Fetch and describe GitHub ProjectV2 configuration.

Given an org and project number, returns the project title and its full
field configuration. This drives the connect-a-project field pickers.
"""

from __future__ import annotations

from typing import Any

from core import github

_FIELDS_QUERY = """
query ProjectFields($org: String!, $number: Int!, $after: String) {
  rateLimit { remaining resetAt }
  organization(login: $org) {
    projectV2(number: $number) {
      id
      title
      number
      fields(first: 50, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          __typename
          ... on ProjectV2FieldCommon {
            id
            name
            dataType
          }
          ... on ProjectV2SingleSelectField {
            id
            name
            dataType
            options { id name }
          }
          ... on ProjectV2IterationField {
            id
            name
            dataType
          }
        }
      }
    }
  }
}
"""


def fetch_project(org: str, number: int) -> dict[str, Any]:
    """Return project metadata and all its fields.

    Returns a dict:
      id, title, number, org, fields: list[{id, name, dataType, options?}]
    """
    fields: list[dict[str, Any]] = []

    for node in github.paginate(
        _FIELDS_QUERY,
        {"org": org, "number": number},
        ["organization", "projectV2", "fields"],
    ):
        if not node:
            continue
        field: dict[str, Any] = {
            "id": node.get("id", ""),
            "name": node.get("name", ""),
            "dataType": node.get("dataType", ""),
        }
        if "options" in node:
            field["options"] = [o["name"] for o in node["options"]]
        fields.append(field)

    # We need the project id and title, which comes from the first query.
    data = github.query(_FIELDS_QUERY, {"org": org, "number": number, "after": None})
    proj = data["organization"]["projectV2"]

    return {
        "id": proj["id"],
        "title": proj["title"],
        "number": proj["number"],
        "org": org,
        "fields": fields,
    }


def project_id_slug(org: str, number: int) -> str:
    """Stable filesystem-safe ID for a project, e.g. 'elastic-2419'."""
    return f"{org}-{number}"


def date_fields(fields: list[dict[str, Any]]) -> list[str]:
    """Field names whose dataType is DATE."""
    return [f["name"] for f in fields if f.get("dataType") == "DATE"]


def number_fields(fields: list[dict[str, Any]]) -> list[str]:
    """Field names whose dataType is NUMBER."""
    return [f["name"] for f in fields if f.get("dataType") == "NUMBER"]
