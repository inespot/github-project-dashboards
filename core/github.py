"""GitHub GraphQL client.

Reads GITHUB_TOKEN from the environment (loaded from .env).
"""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Iterator

import httpx

_ENDPOINT = "https://api.github.com/graphql"
_REQUIRED_SCOPES = {"read:project", "repo", "read:org"}
_RATE_LIMIT_LOCK = threading.Lock()
_MIN_REMAINING_BEFORE_WAIT = 30


class RateLimitError(RuntimeError):
    """Raised when the GitHub GraphQL rate limit is exhausted."""

    def __init__(self, remaining: int, reset_at: str = ""):
        self.remaining = remaining
        self.reset_at = reset_at
        when = reset_at or "the next reset"
        super().__init__(
            f"GitHub API rate limit exhausted ({remaining} remaining). "
            f"Try again after {when}."
        )


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


def rate_limit_status() -> dict[str, Any]:
    """Return ``{remaining, limit, resetAt}`` (uses 1 API point)."""
    data = query("{ rateLimit { remaining limit resetAt } }")
    return data.get("rateLimit") or {"remaining": 0, "limit": 0, "resetAt": ""}


def has_budget(minimum: int = 100) -> bool:
    """True if GraphQL remaining quota is at least ``minimum``.

    Returns False if the status check itself fails (e.g. already exhausted).
    """
    try:
        rl = rate_limit_status()
        return int(rl.get("remaining") or 0) >= minimum
    except Exception:
        return False


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

    if resp.status_code in (403, 429):
        reset_at = resp.headers.get("x-ratelimit-reset", "")
        remaining = resp.headers.get("x-ratelimit-remaining", "0")
        try:
            remaining_i = int(remaining)
        except ValueError:
            remaining_i = 0
        reset_iso = ""
        if reset_at.isdigit():
            reset_iso = datetime.fromtimestamp(int(reset_at), tz=timezone.utc).isoformat()
        raise RateLimitError(remaining_i, reset_iso)

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
            if "rate limit" in msg.lower():
                rl = (body.get("data") or {}).get("rateLimit") or {}
                raise RateLimitError(
                    int(rl.get("remaining") or 0),
                    str(rl.get("resetAt") or ""),
                )
        messages = "; ".join(e.get("message", str(e)) for e in errors)
        raise RuntimeError(f"GraphQL errors: {_scrub(messages)}")

    _maybe_backoff(body)
    return body.get("data", {})


def _maybe_backoff(body: dict[str, Any]) -> None:
    """If quota is low, wait once (under a lock) until near reset — never pile up sleeps."""
    try:
        rl = body["data"]["rateLimit"]
    except (KeyError, TypeError):
        return
    if not rl:
        return

    remaining = int(rl.get("remaining") or 0)
    reset_at = str(rl.get("resetAt") or "")

    if remaining <= 0:
        raise RateLimitError(remaining, reset_at)

    if remaining >= _MIN_REMAINING_BEFORE_WAIT:
        return

    with _RATE_LIMIT_LOCK:
        # Re-check after acquiring lock — another thread may have waited already.
        wait_s = _seconds_until_reset(reset_at)
        if wait_s <= 0:
            return
        # Cap wait; caller can retry. Prefer failing fast over multi-minute hangs.
        wait_s = min(wait_s, 15)
        print(
            f"Rate limit low ({remaining} remaining). "
            f"Pausing {wait_s:.0f}s… (resets {reset_at})"
        )
        time.sleep(wait_s)


def _seconds_until_reset(reset_at: str) -> float:
    if not reset_at:
        return 5.0
    try:
        # GitHub returns ISO-8601 UTC, e.g. 2026-08-20T01:34:31Z
        reset_dt = datetime.fromisoformat(reset_at.replace("Z", "+00:00"))
        return max(0.0, (reset_dt - datetime.now(timezone.utc)).total_seconds())
    except ValueError:
        return 5.0


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
