"""Tests for core.people display-name helpers."""

from core.people import display_name, format_assignees


def test_known_logins_map_to_display_names():
    assert display_name("inespot") == "Ines"
    assert display_name("burqen") == "Anton"
    assert display_name("samxbr") == "Sam"
    assert display_name("PeteGillinElastic") == "Pete"
    assert display_name("DaveCTurner") == "David"
    assert display_name("DiannaHohensee") == "Dianna"
    assert display_name("surya-estc") == "Surya"
    assert display_name("ywangd") == "Yang"
    assert display_name("nicktindall") == "Nick"
    assert display_name("lkts") == "Sasha"


def test_unknown_login_passthrough():
    assert display_name("someone_else") == "someone_else"


def test_format_assignees():
    assert format_assignees(["inespot", "samxbr"]) == "Ines, Sam"
    assert format_assignees([]) == "—"
    assert format_assignees(None) == "—"
