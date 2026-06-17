from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SchemaIssue:
    path: str
    message: str


def validate_json_schema(schema: dict[str, Any], value: Any, *, path: str = "$") -> list[SchemaIssue]:
    issues: list[SchemaIssue] = []
    _validate(schema, value, path, issues)
    return issues


def format_schema_issues(issues: list[SchemaIssue]) -> str:
    return "; ".join(f"{issue.path}: {issue.message}" for issue in issues)


def format_repair_hint(issues: list[SchemaIssue], *, artifact_name: str) -> str:
    lines = [
        f"{artifact_name} schema validation failed.",
        "Repair the JSON and try again. Keep the object shape stable and fix these fields:",
    ]
    for issue in issues:
        lines.append(f"- {issue.path}: {issue.message}")
    return "\n".join(lines)


def _validate(schema: dict[str, Any], value: Any, path: str, issues: list[SchemaIssue]) -> None:
    if "enum" in schema and value not in schema["enum"]:
        choices = ", ".join(repr(item) for item in schema["enum"])
        issues.append(SchemaIssue(path, f"must be one of: {choices}"))
        return

    expected = schema.get("type")
    if expected and not _matches_type(value, expected):
        issues.append(SchemaIssue(path, f"must be {_format_type(expected)}"))
        return

    if expected == "object" or (expected is None and isinstance(value, dict)):
        if not isinstance(value, dict):
            return
        properties = schema.get("properties") or {}
        for key in schema.get("required", []):
            if key not in value:
                issues.append(SchemaIssue(f"{path}.{key}", "required"))
        additional = schema.get("additionalProperties", True)
        for key, item in value.items():
            child_schema = properties.get(key)
            if child_schema is None:
                if additional is False:
                    issues.append(SchemaIssue(f"{path}.{key}", "unknown field"))
                continue
            if isinstance(child_schema, dict):
                _validate(child_schema, item, f"{path}.{key}", issues)
        return

    if expected == "array" or (expected is None and isinstance(value, list)):
        if not isinstance(value, list):
            return
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(value) < min_items:
            issues.append(SchemaIssue(path, f"must contain at least {min_items} item(s)"))
        items_schema = schema.get("items")
        if isinstance(items_schema, dict):
            for index, item in enumerate(value):
                _validate(items_schema, item, f"{path}[{index}]", issues)


def _matches_type(value: Any, expected: Any) -> bool:
    if isinstance(expected, list):
        return any(_matches_type(value, item) for item in expected)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "null":
        return value is None
    return True


def _format_type(expected: Any) -> str:
    if isinstance(expected, list):
        return " or ".join(str(item) for item in expected)
    return str(expected)
