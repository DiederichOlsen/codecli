from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

from .base import ToolContext, ToolResult, truncate_output


class GlobTool:
    name = "Glob"
    description = "Find files by glob pattern in the current workspace."
    read_only = True
    concurrency_safe = True
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Glob pattern, for example **/*.py."}
        },
        "required": ["pattern"],
    }

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        pattern = str(args["pattern"])
        paths = []
        for path in ctx.cwd.rglob("*"):
            rel = path.relative_to(ctx.cwd).as_posix()
            if _skip(rel):
                continue
            if fnmatch.fnmatch(rel, pattern):
                paths.append(rel)
        return ToolResult(truncate_output("\n".join(paths) or "(no matches)", ctx.max_output_chars))


class GrepTool:
    name = "Grep"
    description = "Search text in workspace files."
    read_only = True
    concurrency_safe = True
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string"},
            "path": {"type": "string", "description": "Optional file or directory path."},
            "glob": {"type": "string", "description": "Optional glob filter, for example **/*.py."},
        },
        "required": ["pattern"],
    }

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        needle = str(args["pattern"])
        base = ctx.cwd / str(args.get("path") or ".")
        glob = str(args.get("glob") or "*")
        files = [base] if base.is_file() else [p for p in base.rglob("*") if p.is_file()]
        hits: list[str] = []
        for path in files:
            rel = path.relative_to(ctx.cwd).as_posix() if path.is_relative_to(ctx.cwd) else str(path)
            if _skip(rel) or not fnmatch.fnmatch(rel, glob):
                continue
            try:
                for idx, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                    if needle in line:
                        hits.append(f"{rel}:{idx}: {line}")
                        if len("\n".join(hits)) > ctx.max_output_chars:
                            return ToolResult(truncate_output("\n".join(hits), ctx.max_output_chars))
            except OSError:
                continue
        return ToolResult("\n".join(hits) or "(no matches)")


def _skip(rel: str) -> bool:
    parts = set(rel.split("/"))
    return bool(parts.intersection({".git", ".pyagent", "node_modules", "__pycache__"}))
