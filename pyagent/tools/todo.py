from __future__ import annotations

import json
from typing import Any

from .base import ToolContext, ToolResult


class TodoWriteTool:
    name = "TodoWrite"
    description = "Replace the current task list with structured todos."
    read_only = False
    concurrency_safe = False
    parameters = {
        "type": "object",
        "properties": {
            "todos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]},
                    },
                    "required": ["content", "status"],
                },
            }
        },
        "required": ["todos"],
    }

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        ctx.state.todos = list(args["todos"])
        return ToolResult("Updated todos:\n" + json.dumps(ctx.state.todos, ensure_ascii=False, indent=2))
