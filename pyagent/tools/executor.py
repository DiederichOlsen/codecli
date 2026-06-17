from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from typing import Any, Optional

from .. import ui
from ..messages import tool_message
from ..permissions import PermissionManager
from ..schema_validation import format_schema_issues, validate_json_schema
from ..task_planning import (
    has_goal_anchor,
    planning_status_blocks_tool,
    planning_status_reason,
    record_deviation,
    should_record_deviation,
)
from ..verification import VerificationPolicy
from .base import ToolContext, ToolResult
from .registry import ToolRegistry


@dataclass
class ToolExecution:
    message: dict[str, Any]
    tool_name: str
    success: bool
    user_display: list[str]


class ToolExecutor:
    """Runs one tool call through the local runtime pipeline.

    The executor is intentionally small and explicit:
    parse -> lookup -> schema validate -> permission -> run -> tool_result.
    Keeping this pipeline separate from Agent makes it easier to test and to
    port the same behavior to Rust later.
    """

    def __init__(
        self,
        *,
        registry: ToolRegistry,
        permissions: PermissionManager,
        context: ToolContext,
        trace_store: Optional[Any] = None,
    ) -> None:
        self.registry = registry
        self.permissions = permissions
        self.context = context
        self.verification = VerificationPolicy()
        self.trace_store = trace_store

    def execute_call(self, call: dict[str, Any]) -> ToolExecution:
        call_id = str(call.get("id") or "")
        func = call.get("function") or {}
        name = str(func.get("name") or "")
        raw_args = func.get("arguments") or "{}"
        display = [ui.tool_call(name, str(raw_args))]
        self._trace(
            "tool_call_received",
            call_id=call_id,
            tool_name=name,
            raw_arguments_preview=str(raw_args)[:2000],
        )

        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
        except json.JSONDecodeError as exc:
            content = f"InputValidationError: invalid JSON arguments: {exc}"
            display.append(ui.event_line("parse", content, style="red"))
            self._trace(
                "args_parsed",
                call_id=call_id,
                tool_name=name,
                success=False,
                error=content,
            )
            return self._result(call_id, name, content, False, display)
        self._trace(
            "args_parsed",
            call_id=call_id,
            tool_name=name,
            success=True,
            args=_audit_args(args),
        )

        tool = self.registry.get(name)
        if tool is None:
            content = f"Error: no such tool: {name}"
            display.append(ui.event_line("lookup", content, style="red"))
            self._trace(
                "tool_lookup",
                call_id=call_id,
                tool_name=name,
                success=False,
                error=content,
            )
            return self._result(call_id, name, content, False, display)
        self._trace("tool_lookup", call_id=call_id, tool_name=name, success=True)

        schema_error = validate_args(tool.parameters, args)
        if schema_error:
            content = f"InputValidationError: {schema_error}"
            display.append(ui.event_line("schema", schema_error, style="red"))
            self._trace(
                "schema_validated",
                call_id=call_id,
                tool_name=name,
                success=False,
                error=schema_error,
            )
            return self._result(call_id, name, content, False, display)
        display.append(ui.event_line("schema", "ok", style="green"))
        self._trace("schema_validated", call_id=call_id, tool_name=name, success=True)

        planning_status = str(getattr(self.context.state, "planning_status", "idle"))
        if planning_status_blocks_tool(planning_status, tool.name):
            reason = planning_status_reason(planning_status)
            content = f"Planning state blocked {tool.name}: {reason}"
            display.append(ui.event_line("planning", f"blocked - {reason}", style="yellow"))
            self._trace(
                "planning_state_decided",
                call_id=call_id,
                tool_name=name,
                success=False,
                planning_status=planning_status,
                reason=reason,
            )
            return self._result(call_id, name, content, False, display)

        if tool.name in {"Edit", "Write", "Bash"} and planning_status == "executing" and not has_goal_anchor(self.context.state):
            reason = "executing plan-task requires a current_goal anchor"
            content = f"Planning state blocked {tool.name}: {reason}"
            display.append(ui.event_line("goal", f"blocked - {reason}", style="yellow"))
            self._trace(
                "goal_anchor_decided",
                call_id=call_id,
                tool_name=name,
                success=False,
                planning_status=planning_status,
                reason=reason,
            )
            return self._result(call_id, name, content, False, display)

        decision = self.permissions.decide(tool.name, args)
        if not decision.allowed:
            content = f"Permission denied: {decision.reason}"
            display.append(ui.event_line("permission", f"denied - {decision.reason}", style="yellow"))
            self._trace(
                "permission_decided",
                call_id=call_id,
                tool_name=name,
                success=False,
                decision=decision.to_audit_dict(),
            )
            return self._result(call_id, name, content, False, display)
        display.append(ui.event_line("permission", f"allow - {decision.reason}", style="green"))
        self._trace(
            "permission_decided",
            call_id=call_id,
            tool_name=name,
            success=True,
            decision=decision.to_audit_dict(),
        )

        try:
            self._trace("tool_started", call_id=call_id, tool_name=name)
            result = tool.run(args, self.context)
        except Exception as exc:
            result = ToolResult(f"Error calling tool {name}: {exc}", success=False)

        deviation_recorded = False
        target = str(args.get("file_path", "") or args.get("command", ""))
        if result.success and should_record_deviation(self.context.state, tool.name, target):
            record_deviation(
                self.context.state,
                tool_name=tool.name,
                target=target,
                reason="target was not listed in planned_files; allowed as a recorded deviation",
                goal_aligned=True,
                requires_replan=False,
            )
            deviation_recorded = True
            display.append(ui.event_line("deviation", "recorded - target outside planned_files", style="yellow"))

        result_label = "ok" if result.success else "error"
        result_style = "green" if result.success else "red"
        display.append(ui.event_line("result", result_label, style=result_style))
        self._trace(
            "tool_finished",
            call_id=call_id,
            tool_name=name,
            success=result.success,
            result_chars=len(result.content),
            goal=str(getattr(self.context.state, "current_goal", "")),
            current_step=str(getattr(self.context.state, "current_step", "")),
            deviation_recorded=deviation_recorded,
        )
        if not result.success and result.display_summary:
            display.append(ui.error(_indent_block(result.display_summary)))
        if tool.name in {"Edit", "Write", "Bash"}:
            verification_status = self.verification.status(self.context.state)
            display.append(ui.event_line("verification", verification_status, style="blue"))
            self._trace(
                "verification_state_updated",
                call_id=call_id,
                tool_name=name,
                status=verification_status,
                changed_files=len(self.context.state.changed_files),
                verification_commands=len(self.context.state.verification_commands),
            )
        return self._result(call_id, name, result.content, result.success, display)

    def run_local_tool(self, name: str, args: dict[str, Any]) -> ToolResult:
        tool = self.registry.get(name)
        if tool is None:
            return ToolResult(f"Unknown tool: {name}", success=False)

        schema_error = validate_args(tool.parameters, args)
        if schema_error:
            return ToolResult(f"InputValidationError: {schema_error}", success=False)

        planning_status = str(getattr(self.context.state, "planning_status", "idle"))
        if planning_status_blocks_tool(planning_status, tool.name):
            return ToolResult(
                f"Planning state blocked {tool.name}: {planning_status_reason(planning_status)}",
                success=False,
            )
        if tool.name in {"Edit", "Write", "Bash"} and planning_status == "executing" and not has_goal_anchor(self.context.state):
            return ToolResult(
                "Planning state blocked "
                f"{tool.name}: executing plan-task requires a current_goal anchor",
                success=False,
            )

        decision = self.permissions.decide(tool.name, args)
        if not decision.allowed:
            return ToolResult(f"Permission denied: {decision.reason}", success=False)
        result = tool.run(args, self.context)
        target = str(args.get("file_path", "") or args.get("command", ""))
        if result.success and should_record_deviation(self.context.state, tool.name, target):
            record_deviation(
                self.context.state,
                tool_name=tool.name,
                target=target,
                reason="target was not listed in planned_files; allowed as a recorded deviation",
                goal_aligned=True,
                requires_replan=False,
            )
        return result

    def _trace(self, event: str, **fields: Any) -> None:
        if self.trace_store is None:
            return
        self.trace_store.append(
            self.context.state.session_id,
            {
                "event": event,
                **fields,
            },
        )

    def _result(
        self,
        call_id: str,
        name: str,
        content: str,
        success: bool,
        display: list[str],
    ) -> ToolExecution:
        return ToolExecution(
            message=tool_message(call_id, name, content),
            tool_name=name,
            success=success,
            user_display=display,
        )


def validate_args(schema: dict[str, Any], args: Any) -> str:
    issues = validate_json_schema(schema, args)
    return format_schema_issues(issues)


def _indent_block(text: str, prefix: str = "  ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())


def _audit_args(args: dict[str, Any]) -> dict[str, Any]:
    audited: dict[str, Any] = {}
    sensitive_large_fields = {"content", "old_string", "new_string"}
    for key, value in args.items():
        if key in sensitive_large_fields and isinstance(value, str):
            audited[key] = {
                "chars": len(value),
                "sha256": hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest(),
            }
        else:
            audited[key] = value
    return audited
