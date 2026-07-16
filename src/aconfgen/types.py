"""Parser for the small recursive type language embedded in the manpage."""

from __future__ import annotations

import re
from collections.abc import Sequence

from .errors import ParseError
from .model import TypeField, TypeSpec, json_value
from .scdoc import logical_type_text, parse_toml_value, strip_markup


def _split_top_level(text: str, separator: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    escaped = False
    for index, char in enumerate(text):
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
        elif char in "[{(":
            depth += 1
        elif char in "]})":
            depth -= 1
        elif char == separator and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
    parts.append(text[start:].strip())
    return [part for part in parts if part]


def _split_assignment(text: str) -> tuple[str, str] | None:
    parts = _split_top_level(text, "=")
    if len(parts) != 2:
        return None
    return parts[0].strip(), parts[1].strip()


def _parse_literal(text: str, *, source: str, line: int) -> object:
    return parse_toml_value(text, source=source, line=line)


def parse_type(text: str, *, source: str, line: int) -> TypeSpec:
    """Parse one type expression from the manpage."""

    cleaned = strip_markup(text).strip()
    if not cleaned:
        return TypeSpec(kind="unknown", source=text)

    union = _split_top_level(cleaned, "|")
    if len(union) > 1:
        if set(union) == {"true", "false"}:
            return TypeSpec(kind="scalar", name="boolean", source=text)
        return TypeSpec(
            kind="union",
            options=tuple(parse_type(part, source=source, line=line) for part in union),
            source=text,
        )

    if cleaned.startswith('"') or cleaned.startswith("'"):
        value = _parse_literal(cleaned, source=source, line=line)
        return TypeSpec(kind="literal", value=json_value(value), source=text)

    scalar_names = {"<string>": "string", "<integer>": "integer", "<float>": "float"}
    if cleaned in scalar_names:
        return TypeSpec(kind="scalar", name=scalar_names[cleaned], source=text)
    if cleaned in {"true", "false"}:
        return TypeSpec(kind="scalar", name="boolean", source=text)

    if cleaned.startswith("<") and cleaned.endswith(">"):
        name = cleaned[1:-1].strip()
        return TypeSpec(kind="reference", name=name, source=text)

    if cleaned.startswith("{") and cleaned.endswith("}"):
        inner = cleaned[1:-1].strip()
        fields: list[TypeField] = []
        for field in _split_top_level(inner, ","):
            assignment = _split_assignment(field)
            if assignment is None:
                field_name = field.strip().strip("*").strip("<>").strip()
                if not field_name:
                    continue
                fields.append(
                    TypeField(
                        name=field_name,
                        type=TypeSpec(kind="reference", name=field_name, source=field),
                    )
                )
                continue
            name, field_type = assignment
            fields.append(
                TypeField(
                    name=name.strip("* "),
                    type=parse_type(field_type, source=source, line=line),
                )
            )
        return TypeSpec(kind="object", fields=tuple(fields), source=text)

    if cleaned.startswith("[") and cleaned.endswith("]"):
        inner = cleaned[1:-1].strip().rstrip(",").strip()
        item = parse_type(inner, source=source, line=line) if inner else TypeSpec(kind="unknown")
        return TypeSpec(kind="array", item=item, source=text)

    return TypeSpec(kind="unknown", name=cleaned, source=text)


def merge_fields(spec: TypeSpec, fields: Sequence[TypeField]) -> TypeSpec:
    """Attach documented child schemas to an object or array-object type."""

    if not fields:
        return spec
    if spec.kind == "object":
        return spec.model_copy(update={"fields": tuple(fields)})
    if spec.kind == "array" and spec.item is not None and spec.item.kind == "object":
        return spec.model_copy(
            update={"item": spec.item.model_copy(update={"fields": tuple(fields)})}
        )
    return spec


def type_from_lines(lines: Sequence[str], *, source: str, line: int) -> TypeSpec:
    """Parse a type declaration that may span multiple source lines."""

    return parse_type(logical_type_text(lines), source=source, line=line)


def parse_binding_value(text: str, *, source: str, line: int) -> str:
    """Parse a quoted binding cell and return its string value."""

    value = parse_toml_value(text, source=source, line=line)
    if not isinstance(value, str):
        raise ParseError(f"binding cell is not a string: {text!r}", source=source, line=line)
    if re.fullmatch(r"\\u[0-9A-Fa-f]{4}", value):
        return chr(int(value[2:], 16))
    return value
