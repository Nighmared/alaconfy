"""Tests for valid and complete generated TOML."""

import tomllib

from aconfgen.model import Document, Platform, resolve_default
from aconfgen.render import render


def _table(document: Document, name: str):
    return next(table for table in document.tables if table.name == name)


def _resolved(value):
    if value.kind == "dynamic":
        return None
    return value.value


def _assert_table_defaults(
    document: Document, parsed: dict, platform: Platform, output: str
) -> None:
    def visit(table, target):
        current = target
        for parameter in table.entries:
            resolved = resolve_default(parameter.default, platform)
            if resolved.kind == "concrete":
                assert parameter.name in current, f"missing {table.name}.{parameter.name}"
                assert current[parameter.name] == resolved.value
            else:
                assert f'# {parameter.name} = "$SHELL"' in output
        for child in table.tables:
            assert child.name in current
            visit(child, current[child.name])

    for table in document.tables:
        assert table.name in parsed
        visit(table, parsed[table.name])


def test_generated_linux_configuration_is_complete(document: Document) -> None:
    output = render(document, "linux")
    parsed = tomllib.loads(output)
    _assert_table_defaults(document, parsed, "linux", output)
    assert len(parsed["keyboard"]["bindings"]) == 96
    assert len(parsed["mouse"]["bindings"]) == 3
    assert len(parsed["hints"]["enabled"]) == 1
    assert "# Directory the shell is started in." in output


def test_generated_platform_configurations(document: Document) -> None:
    expected: dict[Platform, tuple[int, str, str | dict[str, object]]] = {
        "macos": (118, "Menlo", "open"),
        "windows": (97, "Consolas", {"program": "cmd", "args": ["/c", "start", ""]}),
    }
    for platform, (binding_count, family, hint_command) in expected.items():
        output = render(document, platform)
        parsed = tomllib.loads(output)
        _assert_table_defaults(document, parsed, platform, output)
        assert len(parsed["keyboard"]["bindings"]) == binding_count
        assert parsed["font"]["normal"]["family"] == family
        assert parsed["hints"]["enabled"][0]["command"] == hint_command


def test_empty_open_environment_table_is_emitted(document: Document) -> None:
    parsed = tomllib.loads(render(document, "linux"))
    assert parsed["env"] == {}
