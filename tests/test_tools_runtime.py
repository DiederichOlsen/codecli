from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

from pyagent.messages import AgentState
from pyagent.permissions import PermissionManager
from pyagent.storage import RuntimeTraceStore
from pyagent.tools.base import ToolContext, ToolResult
from pyagent.tools.bash import BashTool
from pyagent.tools.executor import ToolExecutor, validate_args
from pyagent.tools.files import EditTool, ReadTool, WriteTool
from pyagent.tools.registry import ToolRegistry
from pyagent.tools.scheduler import ToolScheduler


class FakeTool:
    name = "Fake"
    description = "Fake tool for tests."
    read_only = True
    concurrency_safe = True
    parameters = {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
    }

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return ToolResult(f"ok:{args['value']}")


class UnsafeTool(FakeTool):
    name = "Unsafe"
    read_only = False
    concurrency_safe = False


def make_call(name: str, args: Any, call_id: str = "call_1") -> dict[str, Any]:
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": args if isinstance(args, str) else json.dumps(args),
        },
    }


def make_context(cwd: Path, state: AgentState | None = None) -> ToolContext:
    return ToolContext(
        cwd=cwd,
        state=state or AgentState(),
        max_output_chars=20000,
        command_timeout=5,
        interactive=False,
        permission_mode="accept_edits",
    )


def make_executor(cwd: Path, registry: ToolRegistry) -> ToolExecutor:
    return ToolExecutor(
        registry=registry,
        permissions=PermissionManager(
            cwd=cwd,
            config_dir=cwd / ".pyagent",
            mode="accept_edits",
            interactive=False,
        ),
        context=make_context(cwd),
    )


class ToolRuntimeTests(unittest.TestCase):
    def test_validate_args_reports_required_and_type_errors(self) -> None:
        schema = FakeTool.parameters
        self.assertEqual(validate_args(schema, {}), "missing required field: value")
        self.assertEqual(validate_args(schema, {"value": 1}), "field value must be string")
        self.assertEqual(validate_args(schema, {"value": "hello"}), "")

    def test_executor_returns_tool_result_for_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = ToolRegistry([FakeTool()])
            executor = make_executor(Path(tmp), registry)

            result = executor.execute_call(make_call("Fake", "{not-json"))

            self.assertFalse(result.success)
            self.assertEqual(result.message["role"], "tool")
            self.assertIn("invalid JSON", result.message["content"])

    def test_executor_validates_schema_before_running_tool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = ToolRegistry([FakeTool()])
            executor = make_executor(Path(tmp), registry)

            result = executor.execute_call(make_call("Fake", {"value": 123}))

            self.assertFalse(result.success)
            self.assertIn("InputValidationError", result.message["content"])
            self.assertTrue(any("schema" in line for line in result.user_display))

    def test_executor_display_includes_runtime_event_layers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sample.txt").write_text("hello\n", encoding="utf-8")
            registry = ToolRegistry([ReadTool()])
            executor = make_executor(root, registry)

            result = executor.execute_call(make_call("Read", {"file_path": "sample.txt"}))
            display = "\n".join(result.user_display)

            self.assertTrue(result.success)
            self.assertIn("tool", display)
            self.assertIn("args", display)
            self.assertIn("schema", display)
            self.assertIn("permission", display)
            self.assertIn("result", display)

    def test_executor_writes_runtime_audit_trace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sample.txt").write_text("hello\n", encoding="utf-8")
            registry = ToolRegistry([ReadTool()])
            state = AgentState()
            trace_store = RuntimeTraceStore(root / ".pyagent")
            executor = ToolExecutor(
                registry=registry,
                permissions=PermissionManager(
                    cwd=root,
                    config_dir=root / ".pyagent",
                    mode="accept_edits",
                    interactive=False,
                ),
                context=make_context(root, state),
                trace_store=trace_store,
            )

            result = executor.execute_call(make_call("Read", {"file_path": "sample.txt"}))
            events = [
                json.loads(line)
                for line in trace_store.path_for(state.session_id).read_text(encoding="utf-8").splitlines()
            ]

            self.assertTrue(result.success)
            self.assertEqual(
                [event["event"] for event in events],
                [
                    "tool_call_received",
                    "args_parsed",
                    "tool_lookup",
                    "schema_validated",
                    "permission_decided",
                    "tool_started",
                    "tool_finished",
                ],
            )
            self.assertEqual(events[4]["decision"]["policy"], "FilePathPolicy")
            self.assertEqual(events[4]["decision"]["classification"], "readonly")

    def test_executor_blocks_write_when_plan_task_is_not_executing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = AgentState(planning_status="needs_confirmation", planning_request="Add feature")
            registry = ToolRegistry([WriteTool()])
            executor = ToolExecutor(
                registry=registry,
                permissions=PermissionManager(
                    cwd=root,
                    config_dir=root / ".pyagent",
                    mode="accept_edits",
                    interactive=False,
                ),
                context=make_context(root, state),
            )

            result = executor.execute_call(make_call("Write", {"file_path": "new.txt", "content": "hello\n"}))

            self.assertFalse(result.success)
            self.assertIn("Planning state blocked Write", result.message["content"])
            self.assertFalse((root / "new.txt").exists())

    def test_executor_allows_write_when_plan_task_is_executing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = AgentState(
                planning_status="executing",
                planning_request="Add feature",
                current_goal="Add feature",
            )
            registry = ToolRegistry([WriteTool()])
            executor = ToolExecutor(
                registry=registry,
                permissions=PermissionManager(
                    cwd=root,
                    config_dir=root / ".pyagent",
                    mode="accept_edits",
                    interactive=False,
                ),
                context=make_context(root, state),
            )

            result = executor.execute_call(make_call("Write", {"file_path": "new.txt", "content": "hello\n"}))

            self.assertTrue(result.success)
            self.assertEqual((root / "new.txt").read_text(encoding="utf-8"), "hello\n")

    def test_executor_blocks_implementation_without_goal_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = AgentState(planning_status="executing", planning_request="Add feature")
            registry = ToolRegistry([WriteTool()])
            executor = ToolExecutor(
                registry=registry,
                permissions=PermissionManager(
                    cwd=root,
                    config_dir=root / ".pyagent",
                    mode="accept_edits",
                    interactive=False,
                ),
                context=make_context(root, state),
            )

            result = executor.execute_call(make_call("Write", {"file_path": "new.txt", "content": "hello\n"}))

            self.assertFalse(result.success)
            self.assertIn("current_goal anchor", result.message["content"])
            self.assertFalse((root / "new.txt").exists())

    def test_executor_records_deviation_for_unplanned_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = AgentState(
                planning_status="executing",
                planning_request="Add feature",
                current_goal="Add feature",
                planned_files=["planned.txt"],
            )
            registry = ToolRegistry([WriteTool()])
            executor = ToolExecutor(
                registry=registry,
                permissions=PermissionManager(
                    cwd=root,
                    config_dir=root / ".pyagent",
                    mode="accept_edits",
                    interactive=False,
                ),
                context=make_context(root, state),
            )

            result = executor.execute_call(make_call("Write", {"file_path": "surprise.txt", "content": "hello\n"}))

            self.assertTrue(result.success)
            self.assertEqual(state.deviations[-1]["target"], "surprise.txt")
            self.assertFalse(state.deviations[-1]["requires_replan"])

    def test_scheduler_batches_consecutive_safe_tools_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = ToolRegistry([FakeTool(), UnsafeTool()])
            scheduler = ToolScheduler(registry=registry, executor=make_executor(Path(tmp), registry))

            batches = scheduler._partition(
                [
                    make_call("Fake", {"value": "a"}, "a"),
                    make_call("Fake", {"value": "b"}, "b"),
                    make_call("Unsafe", {"value": "c"}, "c"),
                    make_call("Fake", {"value": "d"}, "d"),
                ]
            )

            self.assertEqual([(safe, len(batch)) for safe, batch in batches], [(True, 2), (False, 1), (True, 1)])

    def test_plan_mode_denies_shell_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            permissions = PermissionManager(cwd=root, config_dir=root / ".pyagent", mode="plan", interactive=False)

            decision = permissions.decide("Bash", {"command": "git status"})

            self.assertFalse(decision.allowed)
            self.assertIn("plan mode", decision.reason)

    def test_edit_rejects_file_changed_since_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "sample.txt"
            path.write_text("hello\n", encoding="utf-8")
            state = AgentState()
            ctx = make_context(root, state)

            read_result = ReadTool().run({"file_path": "sample.txt"}, ctx)
            self.assertTrue(read_result.success)

            time.sleep(0.001)
            path.write_text("external change\n", encoding="utf-8")
            edit_result = EditTool().run(
                {
                    "file_path": "sample.txt",
                    "old_string": "hello",
                    "new_string": "goodbye",
                },
                ctx,
            )

            self.assertFalse(edit_result.success)
            self.assertIn("file changed since it was last read", edit_result.content)

    def test_edit_requires_prior_full_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sample.txt").write_text("hello\n", encoding="utf-8")
            ctx = make_context(root)

            edit_result = EditTool().run(
                {
                    "file_path": "sample.txt",
                    "old_string": "hello",
                    "new_string": "goodbye",
                },
                ctx,
            )

            self.assertFalse(edit_result.success)
            self.assertIn("has not been read yet", edit_result.content)

    def test_edit_rejects_partial_read_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sample.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
            ctx = make_context(root)

            read_result = ReadTool().run({"file_path": "sample.txt", "offset": 2, "limit": 1}, ctx)
            self.assertTrue(read_result.success)
            edit_result = EditTool().run(
                {
                    "file_path": "sample.txt",
                    "old_string": "two",
                    "new_string": "TWO",
                },
                ctx,
            )

            self.assertFalse(edit_result.success)
            self.assertIn("only partially read", edit_result.content)

    def test_edit_preserves_crlf_line_endings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "sample.txt"
            path.write_bytes(b"one\r\ntwo\r\n")
            ctx = make_context(root)

            self.assertTrue(ReadTool().run({"file_path": "sample.txt"}, ctx).success)
            edit_result = EditTool().run(
                {
                    "file_path": "sample.txt",
                    "old_string": "one\n",
                    "new_string": "ONE\n",
                },
                ctx,
            )

            self.assertTrue(edit_result.success)
            self.assertEqual(path.read_bytes(), b"ONE\r\ntwo\r\n")

    def test_write_existing_file_requires_prior_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sample.txt").write_text("hello\n", encoding="utf-8")
            ctx = make_context(root)

            write_result = WriteTool().run({"file_path": "sample.txt", "content": "goodbye\n"}, ctx)

            self.assertFalse(write_result.success)
            self.assertIn("has not been read yet", write_result.content)

    def test_write_preserves_existing_crlf_line_endings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "sample.txt"
            path.write_bytes(b"old\r\ncontent\r\n")
            ctx = make_context(root)

            self.assertTrue(ReadTool().run({"file_path": "sample.txt"}, ctx).success)
            write_result = WriteTool().run({"file_path": "sample.txt", "content": "new\ncontent\n"}, ctx)

            self.assertTrue(write_result.success)
            self.assertEqual(path.read_bytes(), b"new\r\ncontent\r\n")

    def test_edit_records_changed_file_for_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sample.txt").write_text("hello\n", encoding="utf-8")
            ctx = make_context(root)

            self.assertTrue(ReadTool().run({"file_path": "sample.txt"}, ctx).success)
            self.assertTrue(
                EditTool()
                .run(
                    {
                        "file_path": "sample.txt",
                        "old_string": "hello",
                        "new_string": "goodbye",
                    },
                    ctx,
                )
                .success
            )

            self.assertEqual(ctx.state.changed_files[-1]["operation"], "edit")
            self.assertTrue(ctx.state.changed_files[-1]["changed"])

    def test_bash_records_verification_command_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = make_context(root)
            command = f'"{sys.executable}" -m compileall .'

            result = BashTool().run({"command": command}, ctx)

            self.assertTrue(result.success)
            self.assertEqual(ctx.state.verification_commands[-1]["command"], command)
            self.assertTrue(ctx.state.verification_commands[-1]["success"])


if __name__ == "__main__":
    unittest.main()
