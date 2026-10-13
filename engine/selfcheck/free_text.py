"""The free-text check: every API route that takes free text from the person is declared (design 6.5).

A request field is free text when it is a string with no fixed set of values and its name says words a person writes:
`note`, `notes`, `text`, `reason`, `comment`, `comments`, `reply`, `message`, `question`, `answer`, `pasted`, `summary`
or `description`, alone or after an underscore (`send_note`), at any depth of the request. A mapping whose values are
unconstrained (`dict[str, Any]`) also counts: whatever the person types can ride in it. A field the schema marks with
`choices` is a pick from a list, never free text.

Each such route must be declared in `api/free_text.py` as `to_assistant` or `local_only`, with a reason. The check fails
for a route that has free text and no declaration, a declaration with no reason or an unknown kind, and a declaration
for a route that no longer exists or no longer takes free text.
"""

from __future__ import annotations

import re
from typing import Any

from engine.selfcheck.scans import Finding

FREE_TEXT_NAME = re.compile(
    r"(?:^|_)(?:notes?|text|reason|comments?|reply|message|question|answer|pasted|summary|description)$"
)
KINDS = ("to_assistant", "local_only")
WHERE = "api/free_text.py"


def _resolve(schemas: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    ref = node.get("$ref")
    return _resolve(schemas, schemas[ref.rsplit("/", 1)[-1]]) if ref else node


def _fields(schemas: dict[str, Any], node: dict[str, Any], prefix: str = "", depth: int = 0) -> list[str]:
    """The free-text fields of a schema object, by their dotted names."""
    if depth > 6:
        return []
    found: list[str] = []
    for name, prop in (_resolve(schemas, node).get("properties") or {}).items():
        if "choices" in prop:
            continue
        for variant in prop.get("anyOf") or [prop]:
            shape = _resolve(schemas, variant)
            kind = shape.get("type")
            if kind == "string" and not shape.get("enum") and "const" not in shape and "format" not in shape:
                if FREE_TEXT_NAME.search(name):
                    found.append(prefix + name)
            elif kind == "object" and shape.get("properties"):
                found += _fields(schemas, shape, f"{prefix}{name}.", depth + 1)
            elif kind == "object" and shape.get("additionalProperties") is True:
                found.append(prefix + name)
            elif kind == "array":
                items = _resolve(schemas, shape.get("items") or {})
                if items.get("type") == "string" and not items.get("enum") and FREE_TEXT_NAME.search(name):
                    found.append(prefix + name)
                elif items.get("properties"):
                    found += _fields(schemas, items, f"{prefix}{name}[].", depth + 1)
    return found


def routes_with_free_text(schema: dict[str, Any]) -> dict[str, list[str]]:
    """Every route of an OpenAPI schema whose JSON request body has free text, as "METHOD /path" and the field names."""
    schemas = schema.get("components", {}).get("schemas", {})
    found: dict[str, list[str]] = {}
    for path, operations in schema.get("paths", {}).items():
        for method, operation in operations.items():
            if method.lower() in ("get", "head", "options"):
                continue
            body = ((operation.get("requestBody") or {}).get("content") or {}).get("application/json", {}).get("schema")
            variants = (body.get("anyOf") or [body]) if body else []
            fields = [name for variant in variants for name in _fields(schemas, variant)]
            if fields:
                found[f"{method.upper()} {path}"] = fields
    return found


def check_free_text(schema: dict[str, Any] | None = None, declared: dict[str, Any] | None = None) -> list[Finding]:
    """Findings for the API's routes (or those of `schema`) against the declarations (or `declared`)."""
    if schema is None:
        from api.openapi import build_schema

        schema = build_schema()
    if declared is None:
        from api.free_text import ROUTES

        declared = ROUTES
    found = routes_with_free_text(schema)
    paths = {
        f"{method.upper()} {path}" for path, operations in schema.get("paths", {}).items() for method in operations
    }
    findings: list[Finding] = []
    for route, fields in sorted(found.items()):
        if route not in declared:
            findings.append(
                Finding(
                    "free-text",
                    WHERE,
                    0,
                    f"{route} takes free text ({', '.join(fields)}) and is neither handed to the assistant nor "
                    "declared local-only",
                )
            )
    for route, entry in sorted(declared.items()):
        if route not in paths:
            findings.append(Finding("free-text", WHERE, 0, f"{route} is declared but there is no such route"))
        elif route not in found:
            findings.append(Finding("free-text", WHERE, 0, f"{route} is declared but takes no free text"))
        if entry.kind not in KINDS:
            findings.append(
                Finding("free-text", WHERE, 0, f"{route} is declared as {entry.kind!r}, not one of {KINDS}")
            )
        if not entry.reason.strip():
            findings.append(Finding("free-text", WHERE, 0, f"{route} is declared without a reason"))
    return findings
