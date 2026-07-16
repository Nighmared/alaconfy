"""Parse Alacritty's configuration and default-binding manpages."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .errors import ParseError
from .model import (
    DefaultSpec,
    Document,
    JsonValue,
    Parameter,
    Platform,
    ResolvedDefault,
    Table,
    TypeField,
    TypeSpec,
    concrete,
    dynamic,
    platform_defaults,
)
from .scdoc import parse_regex_value, parse_toml_value, plain_text, strip_markup
from .types import merge_fields, parse_binding_value, type_from_lines

_ENTRY_RE: Final = re.compile(r"^(?P<indent>\t*)\*(?P<name>[^*]+)\*\s*=\s*(?P<type>.*)$")
_BARE_RE: Final = re.compile(r"^(?P<indent>\t*)\*(?P<name>[^*]+)\*\s*$")
_TABLE_RE: Final = re.compile(r"^(?P<indent>\t*)\*(?P<name>[^*]+)\*\s*$")
_DEFAULT_RE: Final = re.compile(r"^(?P<indent>\t*)Default:\s*(?P<value>.*)$")
_SECTION_RE: Final = re.compile(r"^# (?P<name>[A-Z][A-Z ]*)$")
_PLATFORM_RE: Final = re.compile(
    r"^(?P<label>Linux/BSD(?:/macOS)?|Windows|macOS):\s*(?P<value>.*)$"
)

_TABLE_HEADINGS: Final[dict[str, str]] = {
    "GENERAL": "general",
    "ENV": "env",
    "WINDOW": "window",
    "SCROLLING": "scrolling",
    "FONT": "font",
    "COLORS": "colors",
    "BELL": "bell",
    "SELECTION": "selection",
    "CURSOR": "cursor",
    "TERMINAL": "terminal",
    "MOUSE": "mouse",
    "HINTS": "hints",
    "KEYBOARD": "keyboard",
    "DEBUG": "debug",
}
_SUBTABLES: Final[dict[str, tuple[str, ...]]] = {
    "colors": ("primary", "search", "hints", "normal", "bright", "dim"),
}
_PLATFORM_LABELS: Final[dict[str, tuple[Platform, ...]]] = {
    "Linux/BSD": ("linux",),
    "Linux/BSD/macOS": ("linux", "macos"),
    "Windows": ("windows",),
    "macOS": ("macos",),
}
_MOUSE_MODE_NAMES: Final[frozenset[str]] = frozenset(
    {"AppCursor", "AppKeypad", "Search", "Alt", "Vi"}
)


@dataclass(frozen=True)
class _RawEntry:
    name: str
    indent: int
    start: int
    header_end: int
    end: int
    type_lines: tuple[str, ...]
    body: tuple[str, ...]
    children: tuple[_RawEntry, ...] = ()


@dataclass(frozen=True)
class _BindingRow:
    kind: str
    scope: str
    values: dict[str, JsonValue]


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip("\t"))


def _entry_header(line: str, *, indent: int | None = None) -> re.Match[str] | None:
    match = _ENTRY_RE.match(line)
    if match is not None and (indent is None or len(match.group("indent")) == indent):
        return match
    return None


def _default_header(line: str) -> re.Match[str] | None:
    return _DEFAULT_RE.match(line)


def _is_table_marker(line: str, *, table: str, indent: int) -> str | None:
    match = _TABLE_RE.match(line)
    if match is None or len(match.group("indent")) != indent:
        return None
    name = strip_markup(match.group("name")).strip()
    if name in _SUBTABLES.get(table, ()):
        return name
    return None


def _next_structural(lines: list[str], start: int, end: int, indent: int) -> int:
    for index in range(start, end):
        line = lines[index]
        if _entry_header(line, indent=indent) is not None:
            return index
        if _default_header(line) is not None and _indent(line) <= indent:
            return index
        if line.startswith("# ") and _SECTION_RE.match(line):
            return index
    return end


def _header_end(lines: list[str], start: int, end: int) -> tuple[int, tuple[str, ...]]:
    first = _entry_header(lines[start])
    if first is None:
        raise AssertionError("_header_end called for a non-entry")
    type_lines = [first.group("type")]
    index = start + 1
    while index < end and lines[index].lstrip().startswith(r"\|"):
        type_lines.append(lines[index].strip())
        index += 1
    return index, tuple(type_lines)


def _child_end(lines: list[str], start: int, end: int, indent: int) -> int:
    for index in range(start, end):
        if _entry_header(lines[index], indent=indent) is not None:
            return index
        default = _default_header(lines[index])
        if default is not None and len(default.group("indent")) <= indent:
            return index
    return end


def _inline_children(
    lines: list[str], *, parent_indent: int, start: int, end: int
) -> tuple[_RawEntry, ...]:
    children: list[_RawEntry] = []
    index = start
    child_indent = parent_indent + 1
    while index < end:
        match = _entry_header(lines[index], indent=child_indent)
        bare = _BARE_RE.match(lines[index])
        is_action = bare is not None and strip_markup(bare.group("name")).strip() == "action"
        if match is None and not is_action:
            index += 1
            continue
        if match is None:
            name = "action"
            header_end = index + 1
            type_lines: tuple[str, ...] = ()
        else:
            name = strip_markup(match.group("name")).strip()
            header_end, type_lines = _header_end(lines, index, end)
        child_end = _child_end(lines, header_end, end, child_indent)
        children.append(
            _RawEntry(
                name=name,
                indent=child_indent,
                start=index,
                header_end=header_end,
                end=child_end,
                type_lines=type_lines,
                body=tuple(lines[header_end:child_end]),
            )
        )
        index = child_end
    return tuple(children)


def _raw_entries(lines: list[str], start: int, end: int, *, indent: int) -> tuple[_RawEntry, ...]:
    entries: list[_RawEntry] = []
    index = start
    while index < end:
        match = _entry_header(lines[index], indent=indent)
        if match is None:
            index += 1
            continue
        header_end, type_lines = _header_end(lines, index, end)
        record_end = _next_structural(lines, header_end, end, indent)
        entries.append(
            _RawEntry(
                name=strip_markup(match.group("name")).strip(),
                indent=indent,
                start=index,
                header_end=header_end,
                end=record_end,
                type_lines=type_lines,
                body=tuple(lines[header_end:record_end]),
                children=_inline_children(
                    lines,
                    parent_indent=indent,
                    start=header_end,
                    end=record_end,
                ),
            )
        )
        index = record_end
    return tuple(entries)


def _description(raw: _RawEntry) -> str:
    child_ranges = {(child.start, child.end) for child in raw.children}
    lines: list[str] = []
    index = raw.header_end
    body = list(raw.body)
    while index < raw.end:
        if any(start <= index < end for start, end in child_ranges):
            index += 1
            continue
        line = body[index - raw.header_end]
        if line.lstrip().startswith("Default:") or line.lstrip().startswith("Example:"):
            break
        lines.append(line)
        index += 1
    return plain_text(lines)


def _default_block(raw: _RawEntry) -> tuple[int, list[str]] | None:
    body = list(raw.body)
    expected_indent = raw.indent + 1
    for offset, line in enumerate(body):
        match = _default_header(line)
        if match is None or len(match.group("indent")) != expected_indent:
            continue
        remainder = match.group("value").strip()
        block = ([] if not remainder else [remainder]) + body[offset + 1 :]
        for block_offset, block_line in enumerate(block):
            if block_line.lstrip().startswith("Example:"):
                block = block[:block_offset]
                break
        return raw.header_end + offset, block
    return None


def _parse_platform_block(block: list[str], *, source: str, line: int) -> DefaultSpec | None:
    variants: dict[Platform, ResolvedDefault] = {}
    for offset, raw_line in enumerate(block):
        value_line = strip_markup(raw_line).strip()
        if not value_line:
            continue
        match = _PLATFORM_RE.match(value_line)
        if match is None:
            continue
        label = match.group("label")
        value = match.group("value").strip()
        platforms = _PLATFORM_LABELS[label]
        if value.startswith("$SHELL"):
            resolved = dynamic(value)
        else:
            resolved = ResolvedDefault(
                kind="concrete",
                value=parse_toml_value(value, source=source, line=line + offset),
            )
        for platform in platforms:
            variants[platform] = resolved
    if variants:
        return DefaultSpec(provenance="documented", platforms=variants)
    return None


def _parse_hints_default(block: list[str], *, source: str, line: int) -> DefaultSpec | None:
    cleaned = [strip_markup(item).rstrip() for item in block]
    if not any("[[hints.enabled]]" in item for item in cleaned):
        return None

    common: dict[str, JsonValue] = {}
    platform_commands: dict[Platform, JsonValue] = {}
    pending_key: str | None = None
    for offset, item in enumerate(cleaned):
        stripped = item.strip()
        if not stripped or stripped == "[[hints.enabled]]":
            continue
        alternative = re.match(r"#\s*command\s*=\s*(.+?)\s+#\s*On\s+(macOS|Windows)", stripped)
        if alternative is not None:
            value = parse_toml_value(alternative.group(1), source=source, line=line + offset)
            platform_commands["macos" if alternative.group(2) == "macOS" else "windows"] = value
            continue
        if stripped.startswith("#"):
            continue
        if pending_key is not None:
            common[pending_key] = (
                parse_regex_value(stripped, source=source, line=line + offset, markup_stripped=True)
                if pending_key == "regex"
                else parse_toml_value(stripped, source=source, line=line + offset)
            )
            pending_key = None
            continue
        assignment = re.match(r"(?P<key>[A-Za-z_][\w.]*)\s*=\s*(?P<value>.*)$", stripped)
        if assignment is None:
            continue
        key = assignment.group("key")
        value = assignment.group("value").strip()
        if not value:
            pending_key = key
            continue
        parsed = (
            parse_regex_value(value, source=source, line=line + offset, markup_stripped=True)
            if key == "regex"
            else parse_toml_value(value, source=source, line=line + offset)
        )
        target: dict[str, JsonValue] = common
        if "." in key:
            head, tail = key.split(".", 1)
            nested = target.setdefault(head, {})
            if not isinstance(nested, dict):
                raise ParseError(
                    f"cannot nest default key {key!r}", source=source, line=line + offset
                )
            nested[tail] = parsed
        else:
            target[key] = parsed

    platform_values: dict[Platform, JsonValue] = {}
    for platform in ("linux", "macos", "windows"):
        value = dict(common)
        if platform in platform_commands:
            value["command"] = platform_commands[platform]
        platform_values[platform] = [value]
    return platform_defaults(platform_values)


def _parse_default(raw: _RawEntry, *, source: str, lines: list[str]) -> DefaultSpec | None:
    block_info = _default_block(raw)
    if block_info is None:
        return None
    default_line, block = block_info
    first = block[0].strip() if block else ""
    if not first or first.lower().startswith("see "):
        hints_default = _parse_hints_default(block, source=source, line=default_line + 1)
        if hints_default is not None:
            return hints_default
        platform_default = _parse_platform_block(block, source=source, line=default_line + 1)
        if platform_default is not None:
            return platform_default
        return None
    if _PLATFORM_RE.match(strip_markup(first)):
        platform_default = _parse_platform_block(block, source=source, line=default_line + 1)
        if platform_default is not None:
            return platform_default
    hints_default = _parse_hints_default(block, source=source, line=default_line + 1)
    if hints_default is not None:
        return hints_default
    if first:
        return concrete(parse_toml_value(first, source=source, line=default_line + 1))
    joined = " ".join(item.strip() for item in block if item.strip())
    return concrete(parse_toml_value(joined, source=source, line=default_line + 1))


def _type_field(raw: _RawEntry, *, source: str, lines: list[str]) -> TypeField:
    type_spec = (
        type_from_lines(raw.type_lines, source=source, line=raw.start + 1)
        if raw.type_lines
        else TypeSpec(kind="reference", name=raw.name, source=raw.name)
    )
    parameter = _parameter(raw, source=source, lines=lines)
    return TypeField(
        name=raw.name,
        description=parameter.description,
        type=type_spec,
        default=parameter.default,
    )


def _aggregate_child_default(
    children: tuple[_RawEntry, ...], *, source: str, lines: list[str]
) -> DefaultSpec | None:
    concrete_children: dict[str, JsonValue] = {}
    platform_children: dict[Platform, dict[str, JsonValue]] = {
        "linux": {},
        "macos": {},
        "windows": {},
    }
    has_platform = False
    for child in children:
        default = _parse_default(child, source=source, lines=lines)
        if default is None:
            continue
        if default.common is not None and default.common.kind == "concrete":
            assert default.common.value is not None
            concrete_children[child.name] = default.common.value
        elif default.platforms is not None:
            has_platform = True
            for platform in platform_children:
                resolved = default.platforms.get(platform)
                if resolved is not None and resolved.kind == "concrete":
                    assert resolved.value is not None
                    platform_children[platform][child.name] = resolved.value
    if has_platform:
        platform_values: dict[Platform, JsonValue] = {
            platform: value for platform, value in platform_children.items()
        }
        return platform_defaults(platform_values)
    if concrete_children:
        return concrete(concrete_children)
    return None


def _parameter(raw: _RawEntry, *, source: str, lines: list[str]) -> Parameter:
    type_spec = (
        type_from_lines(raw.type_lines, source=source, line=raw.start + 1)
        if raw.type_lines
        else TypeSpec(kind="reference", name=raw.name, source=raw.name)
    )
    fields = tuple(_type_field(child, source=source, lines=lines) for child in raw.children)
    type_spec = merge_fields(type_spec, fields)
    default = _parse_default(raw, source=source, lines=lines)
    if default is None and fields:
        default = _aggregate_child_default(raw.children, source=source, lines=lines)
    return Parameter(
        name=raw.name,
        description=_description(raw),
        type=type_spec,
        default=default,
    )


def _table_description(path: str, lines: list[str]) -> str:
    marker = f"[{path}]"
    for index, line in enumerate(lines):
        if marker in strip_markup(line):
            return plain_text(lines[index : index + 4])
    return ""


def _parse_table(
    table_name: str,
    lines: list[str],
    start: int,
    end: int,
    *,
    indent: int,
    source: str,
    root_lines: list[str],
) -> Table:
    marker_indices: list[tuple[int, str]] = []
    for index in range(start, end):
        marker = _is_table_marker(lines[index], table=table_name, indent=indent)
        if marker is not None:
            marker_indices.append((index, marker))

    direct_entries: list[_RawEntry] = []
    if marker_indices:
        direct_ranges = [
            (start, marker_indices[0][0]),
            *[
                (
                    marker_indices[position][0] + 1,
                    marker_indices[position + 1][0] if position + 1 < len(marker_indices) else end,
                )
                for position in range(len(marker_indices))
            ],
        ]
    else:
        direct_ranges = [(start, end)]
    for direct_start, direct_end in direct_ranges:
        direct_entries.extend(_raw_entries(lines, direct_start, direct_end, indent=indent))
    parameters = tuple(
        _parameter(raw, source=source, lines=root_lines)
        for raw in sorted(direct_entries, key=lambda item: item.start)
    )
    tables: list[Table] = []
    child_positions: dict[str, int] = {}
    for position, (marker_index, child_name) in enumerate(marker_indices):
        marker_end = marker_indices[position + 1][0] if position + 1 < len(marker_indices) else end
        child_positions[child_name] = marker_index
        child_path = f"{table_name}.{child_name}"
        child = _parse_table(
            child_path,
            lines,
            marker_index + 1,
            marker_end,
            indent=indent + 1,
            source=source,
            root_lines=root_lines,
        )
        tables.append(child)
    order = [
        item
        for _, item in sorted(
            [
                *((raw.start, f"entry:{raw.name}") for raw in direct_entries),
                *((position, f"table:{name}") for name, position in child_positions.items()),
            ],
            key=lambda value: value[0],
        )
    ]
    return Table(
        name=table_name.rsplit(".", 1)[-1],
        description=_table_description(table_name, root_lines),
        open=table_name == "env",
        entries=parameters,
        tables=tuple(tables),
        order=tuple(order),
    )


def _infer_parameter_default(table: str, parameter: Parameter) -> Parameter:
    if parameter.default is not None:
        return parameter
    inferred: dict[tuple[str, str], JsonValue] = {
        ("general", "import"): [],
        ("font", "glyph_offset"): {"x": 0, "y": 0},
        ("mouse", "bindings"): [],
        ("keyboard", "bindings"): [],
    }
    value = inferred.get((table, parameter.name))
    if value is None:
        return parameter
    return parameter.model_copy(update={"default": concrete(value, provenance="inferred")})


def _replace_table(
    table: Table, *, path: str, binding_defaults: dict[str, dict[Platform, JsonValue]]
) -> Table:
    entries: list[Parameter] = []
    for parameter in table.entries:
        updated = _infer_parameter_default(path, parameter)
        if path == "keyboard" and parameter.name == "bindings":
            updated = parameter.model_copy(
                update={"default": platform_defaults(binding_defaults["keyboard"])}
            )
        elif path == "mouse" and parameter.name == "bindings":
            updated = parameter.model_copy(
                update={"default": platform_defaults(binding_defaults["mouse"])}
            )
        entries.append(updated)
    children = tuple(
        _replace_table(child, path=f"{path}.{child.name}", binding_defaults=binding_defaults)
        for child in table.tables
    )
    return table.model_copy(update={"entries": tuple(entries), "tables": children})


def parse_bindings(path: Path) -> dict[str, dict[Platform, JsonValue]]:
    """Parse the default keyboard and mouse binding tables."""

    source = str(path)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ParseError(f"cannot read bindings manpage: {exc}", source=source) from exc

    rows: list[_BindingRow] = []
    section = "common"
    table_kind: str | None = None
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("## "):
            title = line[3:].strip()
            if title == "Vi Mode":
                section = "vi"
            elif title == "Search Mode":
                section = "search"
            elif title == "Windows, Linux, and BSD only":
                section = "unix_windows"
            elif title == "Windows only":
                section = "windows"
            elif title == "macOS only":
                section = "macos"
            else:
                raise ParseError(
                    f"unsupported binding section {title!r}", source=source, line=index + 1
                )
        if line.startswith("[[ *mouse*"):
            table_kind = "mouse"
        elif line.startswith("[[ *key*"):
            table_kind = "keyboard"
        elif line.startswith("|") and table_kind is not None:
            cells = [line]
            next_index = index + 1
            while next_index < len(lines) and lines[next_index].startswith(":"):
                cells.append(lines[next_index])
                next_index += 1
            expected = 3 if table_kind == "mouse" else 4
            if len(cells) != expected:
                raise ParseError(
                    f"expected {expected} cells for {table_kind} binding, found {len(cells)}",
                    source=source,
                    line=index + 1,
                )
            values = _parse_binding_row(cells, kind=table_kind, source=source, line=index + 1)
            rows.append(_BindingRow(kind=table_kind, scope=section, values=values))
            index = next_index - 1
        index += 1

    mouse_rows = [row.values for row in rows if row.kind == "mouse"]
    keyboard_rows = [row for row in rows if row.kind == "keyboard"]
    if len(mouse_rows) != 3:
        raise ParseError(f"expected 3 mouse bindings, found {len(mouse_rows)}", source=source)
    expected_scopes: dict[Platform, tuple[str, ...]] = {
        "linux": ("common", "vi", "search", "unix_windows"),
        "macos": ("common", "vi", "search", "macos"),
        "windows": ("common", "vi", "search", "unix_windows", "windows"),
    }
    resolved_keyboard: dict[Platform, JsonValue] = {}
    for platform, scopes in expected_scopes.items():
        resolved_keyboard[platform] = [row.values for row in keyboard_rows if row.scope in scopes]
    return {
        "mouse": {platform: mouse_rows for platform in expected_scopes},
        "keyboard": resolved_keyboard,
    }


def _parse_binding_row(
    cells: list[str], *, kind: str, source: str, line: int
) -> dict[str, JsonValue]:
    names = ("mouse", "mods", "action") if kind == "mouse" else ("key", "mods", "mode", "action")
    result: dict[str, JsonValue] = {}
    for position, cell in enumerate(cells):
        value = cell[1:].strip()
        if value in {"", "["}:
            continue
        cleaned = strip_markup(value).strip()
        if kind == "keyboard" and position == 3 and cleaned.startswith("chars:"):
            value_text = cleaned.split(":", 1)[1].strip()
            result["chars"] = parse_binding_value(value_text, source=source, line=line)
            continue
        parsed = parse_binding_value(value, source=source, line=line)
        if kind == "mouse" and position == 1 and _is_mouse_mode(parsed):
            result["mode"] = parsed
        else:
            result[names[position]] = parsed
    return result


def _is_mouse_mode(value: str) -> bool:
    """Identify the overloaded second mouse-binding column used by the source table."""

    components = {component.lstrip("~") for component in value.split("|")}
    return bool(components) and components <= _MOUSE_MODE_NAMES


def parse_document(main_path: Path, bindings_path: Path) -> Document:
    """Parse both manpages and return a complete validated IR."""

    source = str(main_path)
    try:
        lines = main_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ParseError(f"cannot read configuration manpage: {exc}", source=source) from exc

    ranges: list[tuple[str, int, int]] = []
    headings = [
        (index, match.group("name").strip())
        for index, line in enumerate(lines)
        if (match := _SECTION_RE.match(line))
    ]
    for position, (start, heading) in enumerate(headings):
        table_name = _TABLE_HEADINGS.get(heading)
        if table_name is None:
            continue
        end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        ranges.append((table_name, start + 1, end))

    if len(ranges) != len(_TABLE_HEADINGS):
        found = {name for name, _, _ in ranges}
        missing = sorted(set(_TABLE_HEADINGS.values()) - found)
        raise ParseError(f"missing configuration sections: {', '.join(missing)}", source=source)

    tables = tuple(
        _parse_table(
            table_name,
            lines,
            start,
            end,
            indent=0,
            source=source,
            root_lines=lines,
        )
        for table_name, start, end in ranges
    )
    binding_defaults = parse_bindings(bindings_path)
    complete_tables = tuple(
        _replace_table(table, path=table.name, binding_defaults=binding_defaults)
        for table in tables
    )
    return Document(tables=complete_tables)
