from __future__ import annotations

import json
from typing import Any, Optional

from .config import Config
from .context import build_system_prompt
from .messages import AgentState, assistant_message, system_message, tool_message, user_message
from .model import OpenAICompatibleModel
from .permissions import PermissionManager
from .storage import TranscriptStore
from .tools.base import ToolContext, ToolResult
from .tools.registry import ToolRegistry


class Agent:
    def __init__(
        self,
        *,
        config: Config,
        state: Optional[AgentState] = None,
        interactive: bool = True,
    ) -> None:
        self.config = config
        self.interactive = interactive
        self.registry = ToolRegistry()
        self.state = state or AgentState()
        self.store = TranscriptStore(config.config_dir)
        self.permissions = PermissionManager(
            cwd=config.cwd,
            config_dir=config.config_dir,
            mode=config.permission_mode,
            interactive=interactive,
        )
        self.model = OpenAICompatibleModel(
            api_key=config.api_key,
            base_url=config.base_url,
            model=config.model,
        )
        if not self.state.messages:
            self._append(system_message(build_system_prompt(config.cwd, self.registry.names())))

    def ask(self, prompt: str) -> str:
        self._append(user_message(prompt))
        final_text = ""
        for _ in range(self.config.max_agent_turns):
            self._compact_if_needed()
            response = self._complete_with_streaming()
            msg = assistant_message(response.content, response.tool_calls)
            self._append(msg)
            if response.content:
                final_text += response.content
            if not response.tool_calls:
                return final_text
            for call in response.tool_calls:
                result_msg = self._execute_tool_call(call)
                self._append(result_msg)
        warning = "Stopped: reached max agent turns."
        print(warning)
        return final_text + "\n" + warning

    def compact_now(self) -> bool:
        return self._compact_if_needed(force=True)

    def run_local_tool(self, name: str, args: dict[str, Any]) -> ToolResult:
        tool = self.registry.get(name)
        if tool is None:
            return ToolResult(f"Unknown tool: {name}", success=False)
        decision = self.permissions.decide(tool.name, args)
        if not decision.allowed:
            return ToolResult(f"Permission denied: {decision.reason}", success=False)
        return tool.run(args, self._tool_context())

    def _execute_tool_call(self, call: dict[str, Any]) -> dict[str, Any]:
        call_id = str(call.get("id") or "")
        func = call.get("function") or {}
        name = str(func.get("name") or "")
        raw_args = func.get("arguments") or "{}"
        print(f"\n[tool] {name}({raw_args})")
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
        except json.JSONDecodeError as exc:
            return tool_message(call_id, name, f"InputValidationError: invalid JSON arguments: {exc}")

        tool = self.registry.get(name)
        if tool is None:
            return tool_message(call_id, name, f"Error: no such tool: {name}")

        decision = self.permissions.decide(tool.name, args)
        if not decision.allowed:
            content = f"Permission denied: {decision.reason}"
            print(f"[tool denied] {content}")
            return tool_message(call_id, name, content)

        try:
            result = tool.run(args, self._tool_context())
        except Exception as exc:
            result = ToolResult(f"Error calling tool {name}: {exc}", success=False)

        status = "ok" if result.success else "error"
        print(f"[tool {status}] {name}")
        return tool_message(call_id, name, result.content)

    def _complete_with_streaming(self):
        response = None
        printed_text = False
        for event in self.model.stream_complete(self.state.messages, self.registry.schemas()):
            if event.type == "text":
                print(event.delta, end="", flush=True)
                printed_text = True
            elif event.type == "done":
                response = event.response
        if printed_text:
            print()
        if response is None:
            raise RuntimeError("Model stream ended without a final response.")
        return response

    def _tool_context(self) -> ToolContext:
        return ToolContext(
            cwd=self.config.cwd,
            state=self.state,
            max_output_chars=self.config.max_tool_output_chars,
            command_timeout=self.config.command_timeout,
            interactive=self.interactive,
            permission_mode=self.config.permission_mode,
        )

    def _compact_if_needed(self, *, force: bool = False) -> bool:
        # 简化版上下文压缩：不额外调用模型，先用可预测的本地摘要把旧消息折叠掉。
        # 这样原型即使在网络不稳定时也不会因为 compact 本身失败而卡住。
        if not force and _rough_message_chars(self.state.messages) < 60000:
            return False
        if len(self.state.messages) <= 10:
            return False
        system = self.state.messages[0]
        old = self.state.messages[1:-8]
        recent = self.state.messages[-8:]
        summary = _summarize_messages(old)
        compact_msg = system_message(
            "Conversation summary from earlier turns:\n"
            + summary
            + "\n\nContinue from this summary and the recent messages below."
        )
        self.state.messages = [system, compact_msg, *recent]
        self.store.append(self.state.session_id, compact_msg)
        self._append(system_message("Context compacted: older messages were summarized locally."))
        return True

    def _append(self, message: dict[str, Any]) -> None:
        self.state.messages.append(message)
        self.store.append(self.state.session_id, message)


def _rough_message_chars(messages: list[dict[str, Any]]) -> int:
    return sum(len(str(m.get("content", ""))) + len(str(m.get("tool_calls", ""))) for m in messages)


def _summarize_messages(messages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = str(msg.get("content", "")).replace("\n", " ").strip()
        if not content and msg.get("tool_calls"):
            content = f"tool calls: {msg.get('tool_calls')}"
        if not content:
            continue
        lines.append(f"- {role}: {content[:500]}")
    if not lines:
        return "- No substantial prior content."
    return "\n".join(lines[-80:])
