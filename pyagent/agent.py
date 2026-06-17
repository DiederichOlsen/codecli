from __future__ import annotations

import json
from typing import Any, Optional

from . import ui
from .config import Config
from .context import build_system_prompt
from .messages import (
    AgentState,
    assistant_message,
    context_boundary_message,
    new_id,
    system_message,
    user_message,
)
from .model import OpenAICompatibleModel
from .permissions import PermissionManager
from .storage import RuntimeTraceStore, TranscriptStore
from .tools.base import ToolContext, ToolResult
from .tools.executor import ToolExecutor
from .tools.registry import ToolRegistry
from .tools.scheduler import ToolScheduler


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
            read_only_tools=self.registry.read_only_names(),
        )
        self.model = OpenAICompatibleModel(
            api_key=config.api_key,
            base_url=config.base_url,
            model=config.model,
        )
        self.trace_store = RuntimeTraceStore(config.config_dir)
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
            print("\n" + ui.runtime_header(f"tool calls: {len(response.tool_calls)}"))
            for execution in self._tool_scheduler().run(response.tool_calls):
                print()
                for line in execution.user_display:
                    print(line)
                self._append(execution.message)
        warning = "Stopped: reached max agent turns."
        print(ui.warning(warning))
        return final_text + "\n" + warning

    def compact_now(self) -> bool:
        return self._compact_if_needed(force=True)

    def load_session(self, session_id: str) -> AgentState:
        self.store.save_state(self.state)
        self.state = self.store.load(session_id)
        if not self.state.messages:
            self._append(system_message(build_system_prompt(self.config.cwd, self.registry.names())))
        return self.state

    def run_local_tool(self, name: str, args: dict[str, Any]) -> ToolResult:
        return self._tool_executor().run_local_tool(name, args)

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

    def _tool_executor(self) -> ToolExecutor:
        return ToolExecutor(
            registry=self.registry,
            permissions=self.permissions,
            context=self._tool_context(),
            trace_store=self.trace_store,
        )

    def _tool_scheduler(self) -> ToolScheduler:
        return ToolScheduler(registry=self.registry, executor=self._tool_executor())

    def _compact_if_needed(self, *, force: bool = False) -> bool:
        # Local compaction is deterministic: no extra model call, and the
        # authoritative plan/digest state is re-injected after the summary.
        if not force and _rough_message_chars(self.state.messages) < 60000:
            return False
        if len(self.state.messages) <= 10:
            return False
        system = self.state.messages[0]
        # Preserve tool/tool_calls pairing: walk backward until we find a
        # non-tool message (i.e. an assistant with tool_calls or the start).
        # This prevents tool messages from being orphaned without a preceding
        # assistant(tool_calls) after compaction.
        split = max(1, len(self.state.messages) - 8)
        while split < len(self.state.messages) and self.state.messages[split].get("role") == "tool":
            split -= 1
        old = self.state.messages[1:split]
        recent = self.state.messages[split:]
        summary = _summarize_messages(old)
        preserved_ids = [str(message.get("id", "")) for message in recent if message.get("id")]
        boundary = _build_context_boundary(
            self.state,
            pre_compact_message_count=len(self.state.messages),
            preserved_message_ids=preserved_ids,
        )
        compact_msg = system_message(
            "Conversation summary from earlier turns:\n"
            + summary
            + _authoritative_state_context(self.state)
            + "\n\nContinue from this summary and the recent messages below."
        )
        boundary["summary_message_id"] = str(compact_msg.get("id", ""))
        boundary["post_compact_message_count"] = 2 + len(recent)
        boundary_msg = context_boundary_message(_format_context_boundary_notice(boundary), boundary)
        self.state.compact_epoch += 1
        self.state.context_boundaries.append(boundary)
        self.state.messages = [system, compact_msg, boundary_msg, *recent]
        self.store.append(self.state.session_id, compact_msg)
        self.store.append(self.state.session_id, boundary_msg)
        self.store.save_messages(self.state)
        self.store.save_state(self.state)
        self._append(system_message("Context compacted: older messages were summarized locally with planning state restored."))
        return True

    def _append(self, message: dict[str, Any]) -> None:
        self.state.messages.append(message)
        self.state.state_revision += 1
        if message.get("id"):
            self.state.last_source_message_id = str(message["id"])
        self.store.append(self.state.session_id, message)
        if self.store.has_message_snapshot(self.state.session_id):
            self.store.save_messages(self.state)


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


def _build_context_boundary(
    state: AgentState,
    *,
    pre_compact_message_count: int,
    preserved_message_ids: list[str],
) -> dict[str, Any]:
    locked_plan = state.locked_plan if isinstance(state.locked_plan, dict) else {}
    digest = state.maintenance_digest if isinstance(state.maintenance_digest, dict) else {}
    return {
        "boundary_id": new_id(),
        "compact_epoch": state.compact_epoch + 1,
        "pre_compact_message_count": pre_compact_message_count,
        "post_compact_message_count": 0,
        "summary_message_id": "",
        "preserved_message_ids": preserved_message_ids,
        "last_source_message_id": state.last_source_message_id,
        "plan_id": str(locked_plan.get("plan_id", "")),
        "plan_revision": int(locked_plan.get("revision", 0) or 0),
        "digest_id": str(digest.get("digest_id", "")),
        "digest_revision": int(digest.get("revision", 0) or 0),
        "planning_status": state.planning_status,
    }


def _authoritative_state_context(state: AgentState) -> str:
    parts: list[str] = []
    if state.locked_plan:
        parts.append(_compact_json_block("Current locked PlanArtifact", state.locked_plan))
    elif state.plan_artifact_candidate:
        parts.append(_compact_json_block("Current PlanArtifactCandidate", state.plan_artifact_candidate))
    if state.maintenance_digest:
        parts.append(_compact_json_block("Current MaintenanceDigest", state.maintenance_digest))
    elif state.maintenance_digest_candidate:
        parts.append(_compact_json_block("Current MaintenanceDigestCandidate", state.maintenance_digest_candidate))
    if not parts:
        return ""
    return "\n\nAuthoritative runtime state restored after compaction:\n" + "\n".join(parts)


def _compact_json_block(title: str, payload: dict[str, Any]) -> str:
    return f"{title}:\n```json\n{json.dumps(payload, ensure_ascii=False, sort_keys=True)}\n```"


def _format_context_boundary_notice(boundary: dict[str, Any]) -> str:
    plan = boundary.get("plan_id") or "none"
    digest = boundary.get("digest_id") or "none"
    return (
        "ContextBoundary: local compaction completed. "
        f"epoch={boundary.get('compact_epoch')} "
        f"plan={plan} "
        f"digest={digest}. "
        "Use the restored PlanArtifact and MaintenanceDigest as authoritative runtime state."
    )
