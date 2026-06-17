from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import ToolContext, ToolResult, truncate_output


SKIP_DIRS = {".git", ".pyagent", ".claude", ".agents", ".codex", "node_modules", "__pycache__", "ccb"}


class ProjectTreeTool:
    name = "ProjectTree"
    description = "Show a compact workspace tree for orientation before planning or editing."
    read_only = True
    concurrency_safe = True
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Optional workspace-relative directory."},
            "max_depth": {"type": "integer", "description": "Maximum directory depth, default 3."},
            "max_entries": {"type": "integer", "description": "Maximum entries to print, default 200."},
        },
        "required": [],
        "additionalProperties": False,
    }

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        rel_path = str(args.get("path") or ".").strip() or "."
        root = _safe_dir(ctx.cwd, rel_path)
        if root is None:
            return ToolResult("ProjectTree error: path must be a directory inside workspace.", success=False)
        max_depth = max(0, int(args.get("max_depth") or 3))
        max_entries = max(1, int(args.get("max_entries") or 200))
        lines: list[str] = []
        count = 0

        def walk(path: Path, depth: int) -> None:
            nonlocal count
            if count >= max_entries:
                return
            if depth > max_depth:
                return
            try:
                children = sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
            except OSError:
                return
            for child in children:
                if count >= max_entries:
                    break
                if child.name in SKIP_DIRS:
                    continue
                rel = child.relative_to(ctx.cwd).as_posix()
                suffix = "/" if child.is_dir() else ""
                lines.append(f"{'  ' * depth}{rel}{suffix}")
                count += 1
                if child.is_dir():
                    walk(child, depth + 1)

        header = root.relative_to(ctx.cwd).as_posix() if root != ctx.cwd else "."
        lines.append(f"{header}/")
        walk(root, 1)
        if count >= max_entries:
            lines.append(f"... truncated after {max_entries} entries")
        return ToolResult(truncate_output("\n".join(lines), ctx.max_output_chars))


def _safe_dir(cwd: Path, path: str) -> Path | None:
    try:
        full = (cwd / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
        full.relative_to(cwd.resolve())
    except (OSError, ValueError):
        return None
    if not full.is_dir():
        return None
    return full
