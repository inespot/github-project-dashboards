"""Tests for core.people display-name helpers."""

from core.people import (
    assignees_edit_value,
    display_name,
    format_assignees,
    parse_assignee_input,
    resolve_person_token,
)


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


def test_parse_assignee_input_accepts_names_and_logins():
    assert parse_assignee_input("Ines, samxbr") == ["inespot", "samxbr"]
    assert parse_assignee_input("Sasha") == ["lkts"]
    assert parse_assignee_input("") == []
    assert parse_assignee_input("  Anton ; Pete ") == [
        "burqen",
        "PeteGillinElastic",
    ]


def test_resolve_and_edit_value_roundtrip():
    assert resolve_person_token("David") == "DaveCTurner"
    assert assignees_edit_value(["inespot", "lkts"]) == "Ines, Sasha"
    assert assignees_edit_value([]) == ""
