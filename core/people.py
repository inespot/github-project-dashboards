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
    "lkts": "Sasha",
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


def assignees_edit_value(logins: list[str] | None) -> str:
    """Comma-separated display names for an editable text field (empty if none)."""
    if not logins:
        return ""
    return ", ".join(display_name(login) for login in logins)


def resolve_person_token(token: str) -> str:
    """Map a typed login or display name to a canonical GitHub login."""
    raw = token.strip()
    if not raw:
        return ""
    if raw in DISPLAY_NAMES:
        return raw
    lower = raw.lower()
    for login in DISPLAY_NAMES:
        if login.lower() == lower:
            return login
    for login, name in DISPLAY_NAMES.items():
        if name.lower() == lower:
            return login
    return raw


def parse_assignee_input(text: str) -> list[str]:
    """Parse a comma/semicolon-separated assignee field into GitHub logins."""
    if not text or not str(text).strip():
        return []
    tokens = [
        t.strip()
        for t in str(text).replace(";", ",").split(",")
        if t.strip()
    ]
    resolved = [resolve_person_token(t) for t in tokens]
    return [login for login in resolved if login]
