"""Small helpers for the scdoc markup used by Alacritty's manpages."""

from __future__ import annotations

import re
import tomllib
from collections.abc import Iterable

from .errors import ParseError
from .model import JsonValue, json_value

_EMPHASIS = re.compile(r"(?<!\\)_([^\n_]+)_(?!\w)")
_STRONG = re.compile(r"\*([^*\n]+)\*")


def _escape_invalid_toml_escapes(text: str) -> str:
    """Preserve regex backslashes while leaving valid TOML escapes untouched."""

    result: list[str] = []
    quote = False
    index = 0
    valid_simple = set('btnfr"\\')
    while index < len(text):
        char = text[index]
        if char == '"':
            quote = not quote
            result.append(char)
            index += 1
            continue
        if quote and char == "\\" and index + 1 < len(text):
            following = text[index + 1]
            valid_unicode = (
                following == "u"
                and index + 5 < len(text)
                and all(item in "0123456789abcdefABCDEF" for item in text[index + 2 : index + 6])
            )
            if following not in valid_simple and not valid_unicode:
                result.append("\\\\")
                index += 1
                continue
            result.extend((char, following))
            index += 2
            continue
        result.append(char)
        index += 1
    return "".join(result)


def strip_markup(text: str) -> str:
    """Remove the emphasis syntax relevant to the source files."""

    result = text.replace("++", "")
    result = _EMPHASIS.sub(r"\1", result)
    result = _STRONG.sub(r"\1", result)
    result = result.replace("\\\\", "\\")
    return result.replace(r"\*", "*")


def plain_text(lines: Iterable[str]) -> str:
    """Normalize source prose into a single readable description."""

    normalized: list[str] = []
    for line in lines:
        value = strip_markup(line).strip()
        if not value or value.startswith("Default:") or value.startswith("Example:"):
            continue
        if value.startswith("++"):
            value = value[2:].strip()
        if value:
            normalized.append(value)
    return " ".join(normalized)


def parse_toml_value(text: str, *, source: str, line: int) -> JsonValue:
    """Parse one scalar, inline table, or array from a cleaned TOML fragment."""

    cleaned = _escape_invalid_toml_escapes(strip_markup(text).strip())
    return _parse_toml_fragment(cleaned, source=source, line=line)


def _parse_toml_fragment(cleaned: str, *, source: str, line: int) -> JsonValue:
    """Parse a TOML fragment after scdoc markup has already been handled."""

    try:
        parsed = tomllib.loads(f"__value = {cleaned}\n")["__value"]
    except (tomllib.TOMLDecodeError, TypeError) as exc:
        raise ParseError(
            f"invalid TOML value {cleaned!r}: {exc}", source=source, line=line
        ) from exc
    return json_value(parsed)


def parse_regex_value(text: str, *, source: str, line: int, markup_stripped: bool = False) -> str:
    """Parse a regex TOML string while retaining regex Unicode escapes.

    Alacritty's hint regex uses TOML escapes to carry regex escapes.  A normal
    TOML parse turns ``\\u0000`` into a NUL character, but Alacritty needs the
    regex engine to receive the six-character escape sequence instead.
    """

    cleaned = text.strip() if markup_stripped else strip_markup(text).strip()
    if len(cleaned) >= 2 and cleaned[0] == '"' and cleaned[-1] == '"':
        cleaned = re.sub(
            r"(?<!\\)\\u([0-9A-Fa-f]{4})",
            lambda match: "\\\\u" + match.group(1),
            cleaned,
        )
    parsed = _parse_toml_fragment(_escape_invalid_toml_escapes(cleaned), source=source, line=line)
    if not isinstance(parsed, str):
        raise ParseError(f"regex default is not a string: {text!r}", source=source, line=line)
    return parsed


def parse_toml_document(text: str, *, source: str, line: int) -> dict[str, JsonValue]:
    """Parse a cleaned TOML snippet used by a multiline default."""

    cleaned = strip_markup(text)
    try:
        parsed = tomllib.loads(cleaned)
    except tomllib.TOMLDecodeError as exc:
        raise ParseError(f"invalid TOML snippet: {exc}", source=source, line=line) from exc
    return {key: json_value(value) for key, value in parsed.items()}


def logical_type_text(lines: Iterable[str]) -> str:
    """Join a type declaration that uses scdoc's escaped continuation bars."""

    parts: list[str] = []
    for line in lines:
        value = line.strip()
        if value.startswith(r"\|"):
            value = "| " + value[2:]
        parts.append(value)
    return " ".join(parts)
