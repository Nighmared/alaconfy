"""Click command-line interface for aconfgen."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, cast

import click

from .errors import AconfgenError
from .model import Platform
from .parser import parse_document
from .render import render

CanonicalPlatform = Literal["linux", "macos", "windows"]


def _canonical_platform(value: str) -> CanonicalPlatform:
    if value == "bsd":
        return "linux"
    if value not in {"linux", "macos", "windows"}:
        raise ValueError(f"unsupported platform {value!r}")
    return cast(CanonicalPlatform, value)


def _default_source_paths() -> tuple[Path, Path]:
    cwd = Path.cwd()
    return cwd / "alacritty.5.scd.txt", cwd / "alacritty-bindings.5.scd.txt"


@click.group(invoke_without_command=True)
@click.option("--manpage", type=click.Path(path_type=Path, dir_okay=False), default=None)
@click.option("--bindings-manpage", type=click.Path(path_type=Path, dir_okay=False), default=None)
@click.option(
    "--platform",
    type=click.Choice(["linux", "macos", "windows", "bsd"], case_sensitive=False),
    default="linux",
    show_default=True,
)
@click.option("--output", type=click.Path(path_type=Path, dir_okay=False), default=None)
@click.pass_context
def main(
    context: click.Context,
    manpage: Path | None,
    bindings_manpage: Path | None,
    platform: str,
    output: Path | None,
) -> None:
    """Generate a complete default Alacritty configuration."""

    if context.invoked_subcommand is not None:
        return
    default_main, default_bindings = _default_source_paths()
    _generate(
        manpage or default_main,
        bindings_manpage or default_bindings,
        _canonical_platform(platform),
        output,
    )


@main.command()
@click.option("--manpage", type=click.Path(path_type=Path, dir_okay=False), default=None)
@click.option("--bindings-manpage", type=click.Path(path_type=Path, dir_okay=False), default=None)
@click.option(
    "--platform",
    type=click.Choice(["linux", "macos", "windows", "bsd"], case_sensitive=False),
    default="linux",
    show_default=True,
)
def parse(manpage: Path | None, bindings_manpage: Path | None, platform: str) -> None:
    """Parse both manpages and print the intermediate JSON representation."""

    del platform
    default_main, default_bindings = _default_source_paths()
    try:
        document = parse_document(manpage or default_main, bindings_manpage or default_bindings)
    except AconfgenError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(document.model_dump(mode="json"), indent=2, ensure_ascii=False))


def _generate(
    manpage: Path,
    bindings_manpage: Path,
    platform: Platform,
    output: Path | None,
) -> None:
    try:
        document = parse_document(manpage, bindings_manpage)
        configuration = render(document, platform)
        if output is None:
            click.echo(configuration, nl=False)
        else:
            output.write_text(configuration, encoding="utf-8")
    except (AconfgenError, OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
