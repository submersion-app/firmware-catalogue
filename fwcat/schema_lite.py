"""A small JSON Schema checker, standard library only.

It understands the keywords `schema/format-1.schema.json` uses and nothing
more: type, const, enum, required, properties, additionalProperties, items,
minItems, uniqueItems, minLength, maxLength, pattern, format (date,
date-time, uri) and local `$ref`s into `$defs`. A keyword it does not know
raises, so the schema cannot quietly grow a rule this checker ignores.

With `strict=True` every object that lists `properties` is closed: a key the
schema does not name is an error. The published format stays open (the app
ignores unknown keys), but the repository's own data is held to the names
the schema knows, which catches a misspelt key before it ships.
"""

import re
from datetime import date, datetime

KNOWN = {
    "$schema", "$id", "$defs", "$ref", "title", "description",
    "type", "const", "enum", "required", "properties", "additionalProperties",
    "items", "minItems", "uniqueItems", "minLength", "maxLength", "pattern",
    "format",
}

_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATE_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")


def _format_ok(kind: str, value: str) -> bool:
    if kind == "date":
        if not _DATE.match(value):
            return False
        try:
            date.fromisoformat(value)
        except ValueError:
            return False
        return True
    if kind == "date-time":
        if not _DATE_TIME.match(value):
            return False
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return False
        return True
    if kind == "uri":
        # The detailed URL rules live in validate.py; here a URI needs a
        # scheme and no whitespace.
        return bool(re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:\S+$", value))
    raise ValueError(f"unknown format: {kind}")


class SchemaChecker:
    def __init__(self, schema: dict):
        self.root = schema

    def check(self, value, *, strict: bool = False) -> list[str]:
        """Every error as `path: message`; an empty list means valid."""
        errors: list[str] = []
        self._check(value, self.root, "$", strict, errors)
        return errors

    def _resolve(self, ref: str) -> dict:
        if not ref.startswith("#/"):
            raise ValueError(f"only local refs are supported: {ref}")
        node = self.root
        for part in ref[2:].split("/"):
            node = node[part]
        return node

    def _check(self, value, schema: dict, path: str, strict: bool, errors: list[str]):
        unknown = set(schema) - KNOWN
        if unknown:
            raise ValueError(f"unsupported schema keywords at {path}: {sorted(unknown)}")
        if "$ref" in schema:
            self._check(value, self._resolve(schema["$ref"]), path, strict, errors)

        expected = schema.get("type")
        if expected is not None:
            kinds = expected if isinstance(expected, list) else [expected]
            if not any(_TYPES[kind](value) for kind in kinds):
                errors.append(f"{path}: expected {' or '.join(kinds)}, got {type(value).__name__}")
                return

        if "const" in schema and value != schema["const"]:
            errors.append(f"{path}: must be {schema['const']!r}")
        if "enum" in schema and value not in schema["enum"]:
            errors.append(f"{path}: {value!r} is not one of the allowed values")

        if isinstance(value, str):
            if "minLength" in schema and len(value) < schema["minLength"]:
                errors.append(f"{path}: shorter than {schema['minLength']}")
            if "maxLength" in schema and len(value) > schema["maxLength"]:
                errors.append(f"{path}: longer than {schema['maxLength']}")
            if "pattern" in schema and not re.search(schema["pattern"], value):
                errors.append(f"{path}: {value!r} does not match {schema['pattern']}")
            if "format" in schema and not _format_ok(schema["format"], value):
                errors.append(f"{path}: {value!r} is not a valid {schema['format']}")

        if isinstance(value, list):
            if "minItems" in schema and len(value) < schema["minItems"]:
                errors.append(f"{path}: needs at least {schema['minItems']} item(s)")
            if schema.get("uniqueItems"):
                seen = []
                for item in value:
                    if item in seen:
                        errors.append(f"{path}: {item!r} is listed twice")
                    else:
                        seen.append(item)
            if "items" in schema:
                for index, item in enumerate(value):
                    self._check(item, schema["items"], f"{path}[{index}]", strict, errors)

        if isinstance(value, dict):
            for key in schema.get("required", []):
                if key not in value:
                    errors.append(f"{path}: missing {key!r}")
            properties = schema.get("properties", {})
            for key, item in value.items():
                if key in properties:
                    self._check(item, properties[key], f"{path}.{key}", strict, errors)
                    continue
                extra = schema.get("additionalProperties", True)
                if strict and "properties" in schema:
                    errors.append(f"{path}: unknown key {key!r}")
                elif extra is False:
                    errors.append(f"{path}: unknown key {key!r}")
                elif isinstance(extra, dict):
                    self._check(item, extra, f"{path}.{key}", strict, errors)
