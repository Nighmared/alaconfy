"""Validated immutable intermediate representation for Alacritty defaults."""

from __future__ import annotations

from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

Platform: TypeAlias = Literal["linux", "macos", "windows"]
JsonValue: TypeAlias = Any


class TypeSpec(BaseModel):
    """A recursive, JSON-compatible representation of a documented type."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["scalar", "literal", "union", "object", "array", "reference", "unknown"]
    name: str | None = None
    value: JsonValue | None = None
    options: tuple[TypeSpec, ...] = ()
    fields: tuple[TypeField, ...] = ()
    item: TypeSpec | None = None
    source: str | None = None


class TypeField(BaseModel):
    """A field in an inline object or a list element schema."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    description: str = ""
    type: TypeSpec
    default: DefaultSpec | None = None


class ResolvedDefault(BaseModel):
    """One concrete or dynamic value after selecting a platform."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["concrete", "dynamic"]
    value: JsonValue | None = None
    expression: str | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> ResolvedDefault:
        if self.kind == "concrete" and self.value is None:
            raise ValueError("concrete defaults must contain a value")
        if self.kind == "dynamic" and not self.expression:
            raise ValueError("dynamic defaults must contain an expression")
        return self


class DefaultSpec(BaseModel):
    """A common default or a set of platform-specific defaults."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provenance: Literal["documented", "inferred"]
    common: ResolvedDefault | None = None
    platforms: dict[Platform, ResolvedDefault] | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> DefaultSpec:
        if self.common is None and not self.platforms:
            raise ValueError("a default must contain a common or platform value")
        if self.common is not None and self.platforms is not None:
            raise ValueError("a default cannot contain both common and platform values")
        return self


class Parameter(BaseModel):
    """A documented configuration parameter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    description: str = ""
    type: TypeSpec
    default: DefaultSpec | None = None


class Table(BaseModel):
    """A TOML table, recursively containing parameters and subtables."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    description: str = ""
    open: bool = False
    entries: tuple[Parameter, ...] = ()
    tables: tuple[Table, ...] = ()
    order: tuple[str, ...] = ()


class Document(BaseModel):
    """The complete intermediate representation emitted by the parser."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: int = Field(default=1, ge=1)
    tables: tuple[Table, ...]


def concrete(
    value: JsonValue, *, provenance: Literal["documented", "inferred"] = "documented"
) -> DefaultSpec:
    """Create a concrete default specification."""

    return DefaultSpec(
        provenance=provenance,
        common=ResolvedDefault(kind="concrete", value=value),
    )


def platform_defaults(
    values: dict[Platform, JsonValue | ResolvedDefault],
    *,
    provenance: Literal["documented", "inferred"] = "documented",
) -> DefaultSpec:
    """Create a platform-specific default specification."""

    resolved: dict[Platform, ResolvedDefault] = {}
    for platform, value in values.items():
        resolved[platform] = (
            value
            if isinstance(value, ResolvedDefault)
            else ResolvedDefault(kind="concrete", value=value)
        )
    return DefaultSpec(provenance=provenance, platforms=resolved)


def dynamic(expression: str) -> ResolvedDefault:
    """Create a dynamic default value."""

    return ResolvedDefault(kind="dynamic", expression=expression)


def resolve_default(default: DefaultSpec, platform: Platform) -> ResolvedDefault:
    """Resolve a default for one canonical platform."""

    if default.common is not None:
        return default.common
    assert default.platforms is not None
    try:
        return default.platforms[platform]
    except KeyError as exc:
        raise ValueError(f"no default is defined for platform {platform!r}") from exc


def json_value(value: object) -> JsonValue:
    """Validate and normalize an arbitrary parsed value as JSON-compatible data."""

    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [json_value(item) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("JSON object keys must be strings")
        return {key: json_value(item) for key, item in value.items()}
    raise TypeError(f"value is not JSON-compatible: {value!r}")


TypeSpec.model_rebuild()
TypeField.model_rebuild()
