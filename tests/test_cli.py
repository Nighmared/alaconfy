"""Click-level tests for the public command-line interface."""

import json

from click.testing import CliRunner
from conftest import BINDINGS_MANPAGE, MAIN_MANPAGE

from alaconfy.cli import main


def test_default_command_generates_toml() -> None:
    result = CliRunner().invoke(
        main,
        [
            "--manpage",
            str(MAIN_MANPAGE),
            "--bindings-manpage",
            str(BINDINGS_MANPAGE),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "[keyboard]" in result.output
    assert 'chars = "\\f"' in result.output


def test_parse_command_emits_json() -> None:
    result = CliRunner().invoke(
        main,
        [
            "parse",
            "--manpage",
            str(MAIN_MANPAGE),
            "--bindings-manpage",
            str(BINDINGS_MANPAGE),
        ],
    )
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["format_version"] == 1
    assert parsed["tables"][-2]["name"] == "keyboard"


def test_platform_alias_and_output_file(tmp_path) -> None:
    output = tmp_path / "alacritty.toml"
    result = CliRunner().invoke(
        main,
        [
            "--manpage",
            str(MAIN_MANPAGE),
            "--bindings-manpage",
            str(BINDINGS_MANPAGE),
            "--platform",
            "bsd",
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    assert output.read_text(encoding="utf-8").startswith("# general\n[general]")
