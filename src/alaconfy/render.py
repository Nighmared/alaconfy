"""Render the validated intermediate representation as documented TOML."""

from __future__ import annotations

import json
import textwrap
from collections.abc import Iterable

from .model import Document, JsonValue, Parameter, Platform, ResolvedDefault, Table, resolve_default


def _toml_value(value: JsonValue) -> str:
    if value is None:
        return '"None"'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=True)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, list):
        if not value:
            return "[]"
        if any(isinstance(item, dict) for item in value):
            items = [f"  {_toml_value(item)}" for item in value]
            return "[\n" + ",\n".join(items) + "\n]"
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return (
            "{ " + ", ".join(f"{key} = {_toml_value(item)}" for key, item in value.items()) + " }"
        )
    raise TypeError(f"unsupported JSON value {value!r}")


def _comment_lines(text: str) -> Iterable[str]:
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            yield "#"
            continue
        for line in textwrap.wrap(paragraph.strip(), width=96, break_long_words=False):
            yield f"# {line}"


def _default_comment(parameter: Parameter, resolved: ResolvedDefault) -> list[str]:
    expression = resolved.expression or "dynamic default"
    return [
        f'# {parameter.name} = "$SHELL"',
        f"# Default is resolved by Alacritty: {expression}.",
    ]


def _render_entry(parameter: Parameter, platform: Platform) -> list[str]:
    lines: list[str] = []
    if parameter.description:
        lines.extend(_comment_lines(parameter.description))
    if parameter.default is None:
        lines.append(f"# {parameter.name} has no documented default")
        return lines
    resolved = resolve_default(parameter.default, platform)
    if resolved.kind == "dynamic":
        lines.extend(_default_comment(parameter, resolved))
    else:
        assert resolved.value is not None
        lines.append(f"{parameter.name} = {_toml_value(resolved.value)}")
    return lines


def _render_table(table: Table, platform: Platform, prefix: str = "") -> list[str]:
    path = f"{prefix}.{table.name}" if prefix else table.name
    lines = [f"# {path}", f"[{path}]"]
    for parameter in table.entries:
        lines.extend(_render_entry(parameter, platform))
        lines.append("")
    if lines[-1] == "":
        lines.pop()
    for child in table.tables:
        lines.extend(["", *_render_table(child, platform, path)])
    return lines


def render(document: Document, platform: Platform) -> str:
    """Render a complete documented configuration for one canonical platform."""

    sections: list[str] = []
    for table in document.tables:
        sections.append("\n".join(_render_table(table, platform)))
    return "\n\n".join(sections).rstrip() + "\n"
