from __future__ import annotations

from typing import Any

from .schema_validation import format_repair_hint, validate_json_schema


STRING_ARRAY_SCHEMA = {
    "type": "array",
    "items": {"type": "string"},
}

DIGEST_TEST_INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string"},
        "checks": STRING_ARRAY_SCHEMA,
    },
    "required": ["intent", "checks"],
}

MAINTENANCE_DIGEST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "digest_id": {"type": "string"},
        "revision": {"type": "integer"},
        "source_plan_id": {"type": "string"},
        "source_message_id": {"type": "string"},
        "updated_at": {"type": "string"},
        "mental_model": {"type": "string"},
        "module_map": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "module": {"type": "string"},
                    "responsibility": {"type": "string"},
                },
                "required": ["module", "responsibility"],
            },
        },
        "change_paths": {
            "type": "array",
            "minItems": 2,
            "items": {
                "type": "object",
                "properties": {
                    "scenario": {"type": "string"},
                    "start_at": {"type": "string"},
                    "notes": {"type": "string"},
                },
                "required": ["scenario", "start_at"],
            },
        },
        "extension_points": STRING_ARRAY_SCHEMA,
        "invariants": STRING_ARRAY_SCHEMA,
        "test_intent_map": {
            "type": "array",
            "items": DIGEST_TEST_INTENT_SCHEMA,
        },
        "handoff_notes": STRING_ARRAY_SCHEMA,
    },
    "required": [
        "mental_model",
        "module_map",
        "change_paths",
        "extension_points",
        "invariants",
        "handoff_notes",
    ],
}

PLAN_ARTIFACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "plan_id": {"type": "string"},
        "revision": {"type": "integer"},
        "source_message_id": {"type": "string"},
        "created_at": {"type": "string"},
        "confirmed_at": {"type": "string"},
        "goal": {"type": "string"},
        "summary": {"type": "string"},
        "planned_files": STRING_ARRAY_SCHEMA,
        "non_goals": STRING_ARRAY_SCHEMA,
        "constraints": STRING_ARRAY_SCHEMA,
        "slices": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "purpose": {"type": "string"},
                    "files": STRING_ARRAY_SCHEMA,
                    "check": {"type": "string"},
                },
                "required": ["id", "purpose", "files", "check"],
            },
        },
        "current_slice_id": {"type": "string"},
        "current_step": {"type": "string"},
        "verification": STRING_ARRAY_SCHEMA,
        "maintenance_digest": MAINTENANCE_DIGEST_SCHEMA,
        "MaintenanceDigestCandidate": MAINTENANCE_DIGEST_SCHEMA,
    },
    "required": ["goal", "summary", "planned_files"],
}


def validate_plan_artifact_payload(payload: dict[str, Any]) -> str:
    issues = validate_json_schema(PLAN_ARTIFACT_SCHEMA, payload)
    if not issues:
        return ""
    return format_repair_hint(issues, artifact_name="PlanArtifactCandidate")


def validate_maintenance_digest_payload(payload: dict[str, Any]) -> str:
    issues = validate_json_schema(MAINTENANCE_DIGEST_SCHEMA, payload)
    if not issues:
        return ""
    return format_repair_hint(issues, artifact_name="MaintenanceDigestCandidate")
