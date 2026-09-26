"""Minimal JSON Schema subset validator (no extra dependency).

Supports: type, enum, const, required, properties, additionalProperties, items, minItems,
uniqueItems, minimum, maximum, exclusiveMinimum, exclusiveMaximum, minLength.
"""

from __future__ import annotations

from typing import Any

_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
}


def validate(instance: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    errors: list[str] = []
    t = schema.get("type")
    if t is not None:
        types = t if isinstance(t, list) else [t]
        if not any(_TYPES[x](instance) for x in types):
            return [f"{path}: expected {'|'.join(types)}, got {type(instance).__name__}"]
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} not in {schema['enum']!r}")
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: must equal {schema['const']!r}")
    if isinstance(instance, dict):
        for r in schema.get("required", []):
            if r not in instance:
                errors.append(f"{path}: missing required property {r!r}")
        props = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for k, v in instance.items():
            if k in props:
                errors += validate(v, props[k], f"{path}.{k}")
            elif extra is False:
                errors.append(f"{path}: unexpected property {k!r}")
            elif isinstance(extra, dict):
                errors += validate(v, extra, f"{path}.{k}")
    if isinstance(instance, list):
        if len(instance) < schema.get("minItems", 0):
            errors.append(f"{path}: fewer than {schema['minItems']} items")
        if schema.get("uniqueItems") and len({repr(x) for x in instance}) != len(instance):
            errors.append(f"{path}: items are not unique")
        if "items" in schema:
            for i, v in enumerate(instance):
                errors += validate(v, schema["items"], f"{path}[{i}]")
    if _TYPES["number"](instance):
        for key, bad in (("minimum", lambda v, b: v < b), ("maximum", lambda v, b: v > b),
                         ("exclusiveMinimum", lambda v, b: v <= b), ("exclusiveMaximum", lambda v, b: v >= b)):
            if key in schema and bad(instance, schema[key]):
                errors.append(f"{path}: violates {key} {schema[key]}")
    if isinstance(instance, str) and len(instance) < schema.get("minLength", 0):
        errors.append(f"{path}: shorter than {schema['minLength']}")
    return errors
