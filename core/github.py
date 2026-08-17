"""GitHub GraphQL client.

Reads GITHUB_TOKEN from the environment (loaded from .env).
"""

from __future__ import annotations

import os
import time
from typing import Any, Iterator

import httpx

_ENDPOINT = "https://api.github.com/graphql"
_REQUIRED_SCOPES = {"read:project", "repo", "read:org"}


def _token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise EnvironmentError(
            "GITHUB_TOKEN is not set. "
            "Copy .env.example to .env and set your PAT there.\n"
            "Required scopes: read:project, repo, read:org"
        )
    return token


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_token()}",
        "Content-Type": "application/json",
        "X-Github-Next-Global-ID": "1",  # opt in to new global node IDs
    }


def _scrub(text: str) -> str:
    """Remove the token from text so it never appears in tracebacks."""
    try:
        tok = _token()
    except EnvironmentError:
        return text
    return text.replace(tok, "***")


def query(q: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run a single GraphQL query and return the 'data' dict.

    Raises RuntimeError on GraphQL errors, with the token scrubbed from the message.
    """
    payload: dict[str, Any] = {"query": q}
    if variables:
        payload["variables"] = variables

    try:
        resp = httpx.post(_ENDPOINT, json=payload, headers=_headers(), timeout=30)
    except httpx.RequestError as exc:
        raise RuntimeError(f"GitHub request failed: {_scrub(str(exc))}") from exc

    if resp.status_code != 200:
        raise RuntimeError(
            f"GitHub returned HTTP {resp.status_code}: {_scrub(resp.text[:400])}"
        )

    body = resp.json()

    errors = body.get("errors", [])
    if errors:
        for err in errors:
            if err.get("type") == "INSUFFICIENT_SCOPES":
                raise PermissionError(
                    "Your GITHUB_TOKEN is missing required scopes.\n"
                    "Required: read:project, repo, read:org\n"
                    "Run: gh auth refresh -s read:project\n"
                    f"API message: {err.get('message', '')}"
                )
            msg = err.get("message", "")
            if "accessible by personal access token" in msg or "SAML" in msg:
                raise PermissionError(
                    "Your GITHUB_TOKEN cannot access this organization's resources.\n"
                    "If the org uses SAML SSO (e.g. Elastic), you must authorize the token:\n"
                    "  1. Go to https://github.com/settings/tokens\n"
                    "  2. Find your token → 'Configure SSO' → 'Authorize' next to the org\n"
                    "Also confirm the token has scopes: read:project, repo, read:org\n"
                    f"API message: {msg}"
                )
        messages = "; ".join(e.get("message", str(e)) for e in errors)
        raise RuntimeError(f"GraphQL errors: {_scrub(messages)}")

    _maybe_backoff(body)
    return body.get("data", {})


def _maybe_backoff(body: dict[str, Any]) -> None:
    """Slow down if we are near the rate limit."""
    try:
        rl = body["data"]["rateLimit"]
        if rl and rl.get("remaining", 9999) < 50:
            reset_at = rl.get("resetAt", "")
            print(f"Rate limit low ({rl['remaining']} remaining). Sleeping 60s… (resets {reset_at})")
            time.sleep(60)
    except (KeyError, TypeError):
        pass


# ---------------------------------------------------------------------------
# Pagination helpers
# ---------------------------------------------------------------------------

def paginate(
    q: str,
    variables: dict[str, Any],
    path: list[str],
) -> Iterator[Any]:
    """Yield every node from a paginated connection.

    `path` is a list of keys from `data` to the connection object, e.g.
    ["organization", "projectV2", "items"]. The connection must have a
    `pageInfo { hasNextPage endCursor }` and a `nodes` field.
    """
    cursor: str | None = None

    while True:
        vars_with_cursor = {**variables, "after": cursor}
        data = query(q, vars_with_cursor)

        conn = data
        for key in path:
            conn = conn[key]

        yield from conn["nodes"]

        page_info = conn["pageInfo"]
        if not page_info["hasNextPage"]:
            break
        cursor = page_info["endCursor"]
