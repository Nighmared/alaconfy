"""Tests for manpage parsing and platform default resolution."""

import json

import pytest
from conftest import BINDINGS_MANPAGE, MAIN_MANPAGE

from aconfgen.errors import ParseError
from aconfgen.model import Document, resolve_default
from aconfgen.parser import parse_bindings


def _table(document: Document, name: str):
    return next(table for table in document.tables if table.name == name)


def _parameter(document: Document, table_name: str, parameter_name: str):
    table = _table(document, table_name)
    return next(parameter for parameter in table.entries if parameter.name == parameter_name)


def test_all_configuration_tables_and_entries_are_parsed(document: Document) -> None:
    assert [table.name for table in document.tables] == [
        "general",
        "env",
        "window",
        "scrolling",
        "font",
        "colors",
        "bell",
        "selection",
        "cursor",
        "terminal",
        "mouse",
        "hints",
        "keyboard",
        "debug",
    ]
    assert [table.name for table in _table(document, "colors").tables] == [
        "primary",
        "search",
        "hints",
        "normal",
        "bright",
        "dim",
    ]
    assert len(_table(document, "window").entries) == 15
    assert len(_table(document, "colors").entries) == 8
    assert len(_table(document, "keyboard").entries) == 1


def test_intermediate_representation_round_trips_as_json(document: Document) -> None:
    encoded = json.dumps(document.model_dump(mode="json"), ensure_ascii=False)
    restored = Document.model_validate(json.loads(encoded))
    assert restored == document
    assert _parameter(document, "window", "opacity").type.kind == "scalar"
    assert _parameter(document, "cursor", "style").type.kind == "object"


def test_platform_defaults(document: Document) -> None:
    normal = _parameter(document, "font", "normal")
    assert resolve_default(normal.default, "linux").value == {
        "family": "monospace",
        "style": "Regular",
    }
    assert resolve_default(normal.default, "macos").value == {"family": "Menlo", "style": "Regular"}
    assert resolve_default(normal.default, "windows").value == {
        "family": "Consolas",
        "style": "Regular",
    }

    shell = _parameter(document, "terminal", "shell")
    assert resolve_default(shell.default, "linux").kind == "dynamic"
    assert resolve_default(shell.default, "macos").kind == "dynamic"
    assert resolve_default(shell.default, "windows").value == "powershell"


def test_binding_defaults_have_expected_platform_counts() -> None:
    defaults = parse_bindings(BINDINGS_MANPAGE)
    assert len(defaults["mouse"]["linux"]) == 3
    assert len(defaults["mouse"]["macos"]) == 3
    assert len(defaults["mouse"]["windows"]) == 3
    assert len(defaults["keyboard"]["linux"]) == 96
    assert len(defaults["keyboard"]["macos"]) == 118
    assert len(defaults["keyboard"]["windows"]) == 97


def test_binding_values_preserve_duplicates_and_special_characters(document: Document) -> None:
    keyboard = _parameter(document, "keyboard", "bindings")
    linux = resolve_default(keyboard.default, "linux").value
    assert isinstance(linux, list)
    assert linux[4] == {
        "key": "L",
        "mods": "Control",
        "mode": "~Vi|~Search",
        "chars": "\f",
    }
    assert sum(1 for binding in linux if binding.get("key") == "Y") == 7


def test_mouse_mode_is_not_emitted_as_a_modifier(document: Document) -> None:
    mouse = _parameter(document, "mouse", "bindings")
    linux = resolve_default(mouse.default, "linux").value
    assert isinstance(linux, list)
    assert linux[-1] == {"mouse": "Middle", "mode": "~Vi", "action": "PasteSelection"}


def test_hint_regex_preserves_regex_escapes(document: Document) -> None:
    hints = _parameter(document, "hints", "enabled")
    macos = resolve_default(hints.default, "macos").value
    assert isinstance(macos, list)
    regex = macos[0]["regex"]
    assert isinstance(regex, str)
    assert r"\u0000" in regex
    assert r"\u001F" in regex
    assert r"\s" in regex
    assert "\x00" not in regex


def test_missing_binding_manpage_is_reported() -> None:
    with pytest.raises(ParseError):
        parse_bindings(MAIN_MANPAGE.with_name("missing-bindings.scd.txt"))
