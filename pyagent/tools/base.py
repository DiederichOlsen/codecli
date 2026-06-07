from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class ToolResult:
    content: str
    success: bool = True
    # 给本地 CLI 看的短摘要，不回避完整 content；LLM 仍然收到完整工具结果。
    display_summary: str = ""


class Tool(Protocol):
    name: str
    description: str
    parameters: dict[str, Any]
    read_only: bool
    concurrency_safe: bool

    def run(self, args: dict[str, Any], ctx: "ToolContext") -> ToolResult:
        ...


@dataclass
class ToolContext:
    cwd: Any
    state: Any
    max_output_chars: int
    command_timeout: int
    # 是否处于可交互终端。Edit 等高风险工具需要它来展示预览并等待确认。
    interactive: bool
    # 当前权限模式。accept_edits/bypass 下可跳过 Edit 的二次 diff 确认。
    permission_mode: str


def tool_schema(tool: Tool) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


def truncate_output(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n[truncated: output exceeded {limit} characters]"


def json_tool_result(result: Any, *, limit: int) -> ToolResult:
    return ToolResult(truncate_output(json.dumps(result, ensure_ascii=False, indent=2), limit))
