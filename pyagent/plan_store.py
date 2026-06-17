from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class PlanStore:
    """Stores user-visible plan snapshots outside the transcript history."""

    def __init__(self, config_dir: Path) -> None:
        self.root = config_dir / "plans"

    def json_path_for(self, plan_id: str) -> Path:
        return self.root / f"{_safe_slug(plan_id)}.json"

    def markdown_path_for(self, plan_id: str) -> Path:
        return self.root / f"{_safe_slug(plan_id)}.md"

    def save(
        self,
        *,
        session_id: str,
        artifact: dict[str, Any],
        maintenance_digest: dict[str, Any] | None,
        markdown: str,
    ) -> dict[str, Path]:
        self.root.mkdir(parents=True, exist_ok=True)
        plan_id = str(artifact.get("plan_id") or "current")
        saved_at = datetime.now(timezone.utc).isoformat()
        markdown_path = self.markdown_path_for(plan_id)
        json_path = self.json_path_for(plan_id)
        snapshot: dict[str, Any] = {
            "schema_version": 1,
            "plan_id": plan_id,
            "revision": artifact.get("revision"),
            "session_id": session_id,
            "saved_at": saved_at,
            "artifact": artifact,
            "markdown_path": str(markdown_path),
        }
        if maintenance_digest:
            snapshot["maintenance_digest"] = maintenance_digest
        markdown_path.write_text(markdown.rstrip() + "\n", encoding="utf-8")
        json_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"json": json_path, "markdown": markdown_path}


def _safe_slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-")
    return cleaned or "current"
