"""Display names for GitHub logins."""

from __future__ import annotations

DISPLAY_NAMES: dict[str, str] = {
    "inespot": "Ines",
    "burqen": "Anton",
    "samxbr": "Sam",
    "PeteGillinElastic": "Pete",
    "DaveCTurner": "David",
    "DiannaHohensee": "Dianna",
    "surya-estc": "Surya",
    "ywangd": "Yang",
    "nicktindall": "Nick",
}


def display_name(login: str | None) -> str:
    """Return a friendly display name for a GitHub login, or the login itself."""
    if not login:
        return ""
    return DISPLAY_NAMES.get(login, login)


def format_assignees(logins: list[str] | None) -> str:
    """Comma-separated display names for a list of logins."""
    if not logins:
        return "—"
    return ", ".join(display_name(login) for login in logins)
