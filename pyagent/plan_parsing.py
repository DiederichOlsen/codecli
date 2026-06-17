from __future__ import annotations

import json
import re
from typing import Any

from .plan_schemas import validate_maintenance_digest_payload, validate_plan_artifact_payload
from .task_planning import (
    DigestChangePath,
    DigestModule,
    DigestTestIntent,
    MaintenanceDigest,
    PlanArtifact,
    PlanArtifactSlice,
    build_maintenance_digest,
    build_plan_artifact,
)


def parse_plan_artifact_bundle(
    planning_request: str,
    raw_artifact: str,
    *,
    source_message_id: str = "",
) -> tuple[PlanArtifact, MaintenanceDigest | None]:
    artifact = parse_plan_artifact_input(
        planning_request,
        raw_artifact,
        source_message_id=source_message_id,
    )
    text = raw_artifact.strip()
    if not text.startswith("{"):
        return artifact, None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return artifact, None
    if not isinstance(payload, dict):
        return artifact, None
    digest_payload = payload.get("maintenance_digest") or payload.get("MaintenanceDigestCandidate")
    if not isinstance(digest_payload, dict):
        return artifact, None
    digest = parse_maintenance_digest(
        digest_payload,
        source_plan_id=artifact.plan_id,
        source_message_id=artifact.source_message_id or source_message_id,
    )
    return artifact, digest


def parse_plan_artifact_input(
    planning_request: str,
    raw_artifact: str,
    *,
    source_message_id: str = "",
) -> PlanArtifact:
    text = raw_artifact.strip()
    if not text:
        return build_plan_artifact(planning_request, source_message_id=source_message_id)
    if not text.startswith("{"):
        return build_plan_artifact(planning_request, summary=text, source_message_id=source_message_id)

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(str(exc)) from exc
    if not isinstance(payload, dict):
        raise ValueError("JSON artifact must be an object")
    schema_error = validate_plan_artifact_payload(payload)
    if schema_error:
        raise ValueError(schema_error)

    return build_plan_artifact(
        str(payload.get("goal", planning_request)).strip(),
        summary=str(payload.get("summary", "")).strip(),
        plan_id=str(payload.get("plan_id", "")).strip(),
        revision=int_value(payload.get("revision"), default=1),
        source_message_id=str(payload.get("source_message_id", "") or source_message_id).strip(),
        created_at=str(payload.get("created_at", "")).strip(),
        confirmed_at=str(payload.get("confirmed_at", "")).strip(),
        planned_files=string_list(payload, "planned_files"),
        non_goals=string_list(payload, "non_goals"),
        constraints=string_list(payload, "constraints"),
        slices=parse_artifact_slices(payload.get("slices")),
        current_slice_id=str(payload.get("current_slice_id", "")).strip(),
        current_step=str(payload.get("current_step", "")).strip(),
        verification=string_list(payload, "verification"),
    )


def parse_maintenance_digest(
    payload: dict[str, Any],
    *,
    source_plan_id: str = "",
    source_message_id: str = "",
) -> MaintenanceDigest:
    schema_error = validate_maintenance_digest_payload(payload)
    if schema_error:
        raise ValueError(schema_error)
    return build_maintenance_digest(
        digest_id=str(payload.get("digest_id", "")).strip(),
        revision=int_value(payload.get("revision"), default=1),
        source_plan_id=str(payload.get("source_plan_id", "") or source_plan_id).strip(),
        source_message_id=str(payload.get("source_message_id", "") or source_message_id).strip(),
        updated_at=str(payload.get("updated_at", "")).strip(),
        mental_model=str(payload.get("mental_model", "")).strip(),
        module_map=parse_digest_modules(payload.get("module_map")),
        change_paths=parse_digest_change_paths(payload.get("change_paths")),
        extension_points=string_list(payload, "extension_points"),
        invariants=string_list(payload, "invariants"),
        test_intent_map=parse_digest_test_intents(payload.get("test_intent_map")),
        handoff_notes=string_list(payload, "handoff_notes"),
    )


def plan_artifact_to_dict(artifact: PlanArtifact) -> dict[str, object]:
    return {
        "goal": artifact.goal,
        "summary": artifact.summary,
        "plan_id": artifact.plan_id,
        "revision": artifact.revision,
        "source_message_id": artifact.source_message_id,
        "created_at": artifact.created_at,
        "confirmed_at": artifact.confirmed_at,
        "planned_files": list(artifact.planned_files),
        "non_goals": list(artifact.non_goals),
        "constraints": list(artifact.constraints),
        "slices": [
            {
                "id": item.id,
                "purpose": item.purpose,
                "files": list(item.files),
                "check": item.check,
            }
            for item in artifact.slices
        ],
        "current_slice_id": artifact.current_slice_id,
        "current_step": artifact.current_step,
        "verification": list(artifact.verification),
    }


def maintenance_digest_to_dict(digest: MaintenanceDigest) -> dict[str, object]:
    return {
        "digest_id": digest.digest_id,
        "revision": digest.revision,
        "source_plan_id": digest.source_plan_id,
        "source_message_id": digest.source_message_id,
        "updated_at": digest.updated_at,
        "mental_model": digest.mental_model,
        "module_map": [
            {
                "module": item.module,
                "responsibility": item.responsibility,
            }
            for item in digest.module_map
        ],
        "change_paths": [
            {
                "scenario": item.scenario,
                "start_at": item.start_at,
                "notes": item.notes,
            }
            for item in digest.change_paths
        ],
        "extension_points": list(digest.extension_points),
        "invariants": list(digest.invariants),
        "test_intent_map": [
            {
                "intent": item.intent,
                "checks": list(item.checks),
            }
            for item in digest.test_intent_map
        ],
        "handoff_notes": list(digest.handoff_notes),
    }


def extract_plan_transition_decision(
    content: str,
    *,
    source_message_id: str = "",
) -> tuple[bool, PlanArtifact | None, MaintenanceDigest | None]:
    if "PlanTransitionDecision" not in content and '"confirm_execution"' not in content:
        return False, None, None
    for raw_json in candidate_json_objects(content):
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("action") != "confirm_execution":
            continue
        artifact_payload = payload.get("artifact")
        if isinstance(artifact_payload, dict):
            try:
                artifact, digest = parse_plan_artifact_bundle(
                    "",
                    json.dumps(artifact_payload, ensure_ascii=False),
                    source_message_id=source_message_id,
                )
                return True, artifact, digest
            except ValueError:
                continue
        return True, None, None
    return False, None, None


def candidate_json_objects(content: str) -> list[str]:
    blocks = re.findall(r"```json\s*(\{.*?\})\s*```", content, flags=re.DOTALL)
    if blocks:
        return blocks
    marker = content.find("PlanArtifactCandidate")
    if marker < 0:
        marker = content.find("PlanTransitionDecision")
    if marker < 0:
        return []
    tail = content[marker:]
    start = tail.find("{")
    if start < 0:
        return []
    depth = 0
    for index, char in enumerate(tail[start:], start=start):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return [tail[start : index + 1]]
    return []


def looks_like_digest_payload(payload: dict[str, Any]) -> bool:
    return "mental_model" in payload and ("module_map" in payload or "change_paths" in payload)


def string_list(payload: dict[str, object], key: str) -> tuple[str, ...]:
    if key not in payload:
        return ()
    value = payload.get(key, ())
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return tuple(str(item) for item in value)


def parse_artifact_slices(value: object) -> tuple[PlanArtifactSlice, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("slices must be a list")
    slices: list[PlanArtifactSlice] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"slices[{index}] must be an object")
        files_value = item.get("files", ())
        if files_value is None:
            files = ()
        elif isinstance(files_value, list):
            files = tuple(str(file_item) for file_item in files_value)
        else:
            raise ValueError(f"slices[{index}].files must be a list")
        slices.append(
            PlanArtifactSlice(
                id=str(item.get("id", "")).strip(),
                purpose=str(item.get("purpose", "")).strip(),
                files=files,
                check=str(item.get("check", "")).strip(),
            )
        )
    return tuple(slices)


def parse_digest_modules(value: object) -> tuple[DigestModule, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("module_map must be a list")
    result: list[DigestModule] = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, str):
            result.append(DigestModule(module=item.strip(), responsibility=""))
            continue
        if not isinstance(item, dict):
            raise ValueError(f"module_map[{index}] must be an object")
        result.append(
            DigestModule(
                module=str(item.get("module", "")).strip(),
                responsibility=str(item.get("responsibility", "") or item.get("owns", "")).strip(),
            )
        )
    return tuple(result)


def parse_digest_change_paths(value: object) -> tuple[DigestChangePath, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("change_paths must be a list")
    result: list[DigestChangePath] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"change_paths[{index}] must be an object")
        result.append(
            DigestChangePath(
                scenario=str(item.get("scenario", "")).strip(),
                start_at=str(item.get("start_at", "")).strip(),
                notes=str(item.get("notes", "")).strip(),
            )
        )
    return tuple(result)


def parse_digest_test_intents(value: object) -> tuple[DigestTestIntent, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("test_intent_map must be a list")
    result: list[DigestTestIntent] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"test_intent_map[{index}] must be an object")
        checks_value = item.get("checks", ())
        if checks_value is None:
            checks = ()
        elif isinstance(checks_value, list):
            checks = tuple(str(check) for check in checks_value)
        else:
            raise ValueError(f"test_intent_map[{index}].checks must be a list")
        result.append(
            DigestTestIntent(
                intent=str(item.get("intent", "")).strip(),
                checks=checks,
            )
        )
    return tuple(result)


def int_value(value: object, *, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("revision must be an integer") from exc
