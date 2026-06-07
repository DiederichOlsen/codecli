from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace

from pyagent.cli import _handle_plan_review_message, _run_plan_task_command, _run_session_command
from pyagent.storage import TranscriptStore


class FakeAgent:
    def __init__(self) -> None:
        self.config = SimpleNamespace(permission_mode="default")
        self.permissions = SimpleNamespace(mode="default")
        self.state = SimpleNamespace(
            planning_status="idle",
            planning_request="",
            current_goal="",
            current_plan_summary="",
            current_step="",
            current_slice_id="",
            planned_files=[],
            plan_artifact_candidate={},
            locked_plan={},
            deviations=[],
            messages=[],
            todos=[],
            changed_files=[],
            verification_commands=[],
            session_id="test-session",
        )
        self.prompts: list[str] = []
        self.modes_seen: list[tuple[str, str]] = []
        self.ask_responses: list[str] = []

    def ask(self, prompt: str) -> str:
        self.prompts.append(prompt)
        self.modes_seen.append((self.config.permission_mode, self.permissions.mode))
        if self.ask_responses:
            response = self.ask_responses.pop(0)
        else:
            response = ""
        self.state.messages.append(
            {
                "id": f"assistant-{len(self.state.messages) + 1}",
                "role": "assistant",
                "content": response,
            }
        )
        return response

    def load_session(self, session_id: str):
        self.store.save_state(self.state)
        self.state = self.store.load(session_id)
        return self.state


class PlanTaskCliTests(unittest.TestCase):
    def test_plan_task_draft_runs_agent_in_temporary_plan_mode(self) -> None:
        agent = FakeAgent()
        config = SimpleNamespace(api_key="test-key")

        with contextlib.redirect_stdout(io.StringIO()):
            _run_plan_task_command(agent, config, "/plan-task draft Add a planning command")

        self.assertEqual(agent.modes_seen, [("plan", "plan")])
        self.assertEqual(agent.config.permission_mode, "default")
        self.assertEqual(agent.permissions.mode, "default")
        self.assertEqual(agent.state.planning_status, "needs_confirmation")
        self.assertEqual(agent.state.planning_request, "Add a planning command")
        self.assertIn("IntentModel draft", agent.prompts[0])
        self.assertIn("Add a planning command", agent.prompts[0])

    def test_plan_task_draft_without_api_key_does_not_call_agent(self) -> None:
        agent = FakeAgent()
        with tempfile.TemporaryDirectory() as tmp:
            config = SimpleNamespace(
                api_key="",
                cwd=Path(tmp),
                config_files=(Path(tmp) / "missing.json",),
            )

            with contextlib.redirect_stdout(io.StringIO()) as output:
                _run_plan_task_command(agent, config, "/plan-task draft Add a planning command")

        self.assertEqual(agent.prompts, [])
        self.assertIn("Missing API key", output.getvalue())

    def test_plan_task_draft_requires_request_text(self) -> None:
        agent = FakeAgent()
        config = SimpleNamespace(api_key="test-key")

        with contextlib.redirect_stdout(io.StringIO()) as output:
            _run_plan_task_command(agent, config, "/plan-task draft")

        self.assertEqual(agent.prompts, [])
        self.assertIn("Usage: /plan-task draft TEXT", output.getvalue())

    def test_plan_task_run_requires_active_draft(self) -> None:
        agent = FakeAgent()
        config = SimpleNamespace(api_key="test-key")

        with contextlib.redirect_stdout(io.StringIO()) as output:
            _run_plan_task_command(agent, config, "/plan-task run")

        self.assertEqual(agent.prompts, [])
        self.assertIn("No plan-task draft is active", output.getvalue())

    def test_plan_task_run_enters_executing_state(self) -> None:
        agent = FakeAgent()
        agent.state.planning_status = "needs_confirmation"
        agent.state.planning_request = "Add a planning command"
        config = SimpleNamespace(api_key="test-key")

        with contextlib.redirect_stdout(io.StringIO()):
            _run_plan_task_command(agent, config, "/plan-task run")

        self.assertEqual(agent.state.planning_status, "executing")
        self.assertEqual(agent.state.current_goal, "Add a planning command")
        self.assertIn("Add a planning command", agent.state.current_plan_summary)
        self.assertEqual(len(agent.prompts), 1)
        self.assertIn("Execute the current plan", agent.prompts[0])
        self.assertIn("Surgical changes", agent.prompts[0])

    def test_plan_task_lock_records_execution_anchor(self) -> None:
        agent = FakeAgent()
        agent.state.planning_status = "needs_confirmation"
        agent.state.planning_request = "Add a planning command"
        config = SimpleNamespace(api_key="test-key")

        with contextlib.redirect_stdout(io.StringIO()) as output:
            _run_plan_task_command(agent, config, "/plan-task lock Small scoped planning CLI change")

        self.assertEqual(agent.state.planning_status, "locked")
        self.assertEqual(agent.state.current_goal, "Add a planning command")
        self.assertEqual(agent.state.current_plan_summary, "Small scoped planning CLI change")
        self.assertEqual(agent.state.locked_plan["summary"], "Small scoped planning CLI change")
        self.assertIn("PlanArtifact", output.getvalue())

    def test_plan_task_lock_accepts_json_artifact(self) -> None:
        agent = FakeAgent()
        agent.state.planning_status = "needs_confirmation"
        agent.state.planning_request = "Add a planning command"
        config = SimpleNamespace(api_key="test-key")
        artifact = (
            '{"goal":"Add lock command","summary":"Lock reviewed plan",'
            '"planned_files":["pyagent/cli.py","tests/test_plan_task_cli.py"],'
            '"current_step":"Implement CLI lock"}'
        )

        with contextlib.redirect_stdout(io.StringIO()):
            _run_plan_task_command(agent, config, f"/plan-task lock {artifact}")

        self.assertEqual(agent.state.planning_status, "locked")
        self.assertEqual(agent.state.current_goal, "Add lock command")
        self.assertEqual(agent.state.planned_files, ["pyagent/cli.py", "tests/test_plan_task_cli.py"])
        self.assertEqual(agent.state.current_step, "Implement CLI lock")

    def test_plan_task_lock_accepts_lightweight_execution_contract(self) -> None:
        agent = FakeAgent()
        agent.state.planning_status = "needs_confirmation"
        agent.state.planning_request = "Add a planning command"
        config = SimpleNamespace(api_key="test-key")
        artifact = (
            '{"plan_id":"plan-123","revision":2,"goal":"Add lock command",'
            '"summary":"Lock reviewed plan",'
            '"planned_files":["pyagent/cli.py","tests/test_plan_task_cli.py"],'
            '"non_goals":["Do not build a full PlanStore"],'
            '"constraints":["Keep current_step as free text"],'
            '"slices":[{"id":"slice-1","purpose":"Persist plan metadata",'
            '"files":["pyagent/cli.py"],"check":"python -m unittest tests.test_plan_task_cli"}],'
            '"current_slice_id":"slice-1",'
            '"current_step":"Implement CLI lock",'
            '"verification":["python -m unittest tests.test_plan_task_cli"]}'
        )

        with contextlib.redirect_stdout(io.StringIO()):
            _run_plan_task_command(agent, config, f"/plan-task lock {artifact}")

        self.assertEqual(agent.state.locked_plan["plan_id"], "plan-123")
        self.assertEqual(agent.state.locked_plan["revision"], 2)
        self.assertEqual(agent.state.current_slice_id, "slice-1")
        self.assertEqual(agent.state.locked_plan["non_goals"], ["Do not build a full PlanStore"])
        self.assertEqual(agent.state.locked_plan["constraints"], ["Keep current_step as free text"])
        self.assertEqual(agent.state.locked_plan["slices"][0]["id"], "slice-1")
        self.assertEqual(agent.state.locked_plan["verification"], ["python -m unittest tests.test_plan_task_cli"])
        self.assertTrue(agent.state.locked_plan["confirmed_at"])

    def test_plan_task_lock_rejects_absolute_planned_file(self) -> None:
        agent = FakeAgent()
        agent.state.planning_status = "needs_confirmation"
        agent.state.planning_request = "Add a planning command"
        config = SimpleNamespace(api_key="test-key")

        with contextlib.redirect_stdout(io.StringIO()) as output:
            _run_plan_task_command(
                agent,
                config,
                '/plan-task lock {"goal":"Add lock command","summary":"Lock reviewed plan","planned_files":["C:\\\\tmp\\\\x.py"]}',
            )

        self.assertEqual(agent.state.planning_status, "needs_confirmation")
        self.assertIn("workspace-relative", output.getvalue())

    def test_plan_task_run_uses_locked_plan_summary(self) -> None:
        agent = FakeAgent()
        agent.state.planning_status = "locked"
        agent.state.planning_request = "Add a planning command"
        agent.state.locked_plan = {
            "goal": "Add lock command",
            "summary": "Lock reviewed plan",
            "planned_files": ["pyagent/cli.py"],
            "current_step": "Implement CLI lock",
        }
        config = SimpleNamespace(api_key="test-key")

        with contextlib.redirect_stdout(io.StringIO()):
            _run_plan_task_command(agent, config, "/plan-task run")

        self.assertEqual(agent.state.planning_status, "executing")
        self.assertEqual(agent.state.current_goal, "Add lock command")
        self.assertEqual(agent.state.current_plan_summary, "Lock reviewed plan")
        self.assertEqual(agent.state.current_step, "Implement CLI lock")
        self.assertEqual(agent.state.current_slice_id, "")
        self.assertIn("Lock reviewed plan", agent.prompts[0])

    def test_plan_task_clear_resets_state(self) -> None:
        agent = FakeAgent()
        agent.state.planning_status = "needs_confirmation"
        agent.state.planning_request = "Add a planning command"
        agent.state.plan_artifact_candidate = {"goal": "Candidate"}
        agent.state.locked_plan = {"goal": "Add a planning command"}
        config = SimpleNamespace(api_key="test-key")

        with contextlib.redirect_stdout(io.StringIO()):
            _run_plan_task_command(agent, config, "/plan-task clear")

        self.assertEqual(agent.state.planning_status, "idle")
        self.assertEqual(agent.state.planning_request, "")
        self.assertEqual(agent.state.current_goal, "")
        self.assertEqual(agent.state.current_slice_id, "")
        self.assertEqual(agent.state.plan_artifact_candidate, {})
        self.assertEqual(agent.state.locked_plan, {})

    def test_plan_review_message_uses_model_transition_decision_to_lock_and_run(self) -> None:
        agent = FakeAgent()
        agent.state.planning_status = "needs_confirmation"
        agent.state.planning_request = "Add a planning command"
        agent.ask_responses = [
            (
                "PlanTransitionDecision\n"
                "```json\n"
                '{"action":"confirm_execution","artifact":{"goal":"Add lock command",'
                '"summary":"Lock reviewed plan","planned_files":["pyagent/cli.py"],'
                '"current_step":"Implement CLI lock"}}'
                "\n```"
            ),
            "",
        ]
        config = SimpleNamespace(api_key="test-key")
        with tempfile.TemporaryDirectory() as tmp:
            store = TranscriptStore(Path(tmp) / ".pyagent")

            with patch("builtins.input", return_value="y"):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    handled = _handle_plan_review_message(agent, config, store, "请按这个方案开始")

            loaded = store.load(agent.state.session_id)

        self.assertTrue(handled)
        self.assertEqual(agent.state.planning_status, "executing")
        self.assertEqual(agent.state.current_goal, "Add lock command")
        self.assertEqual(agent.state.planned_files, ["pyagent/cli.py"])
        self.assertTrue(agent.state.locked_plan["plan_id"])
        self.assertTrue(agent.state.locked_plan["source_message_id"])
        self.assertIn("Lock reviewed plan", agent.prompts[1])
        self.assertEqual(loaded.current_goal, "Add lock command")
        self.assertIn("Plan execution confirmation detected by model", output.getvalue())

    def test_plan_review_message_can_be_cancelled_after_model_confirmation(self) -> None:
        agent = FakeAgent()
        agent.state.planning_status = "needs_confirmation"
        agent.state.planning_request = "Add a planning command"
        agent.ask_responses = [
            'PlanTransitionDecision\n```json\n{"action":"confirm_execution","artifact":null}\n```'
        ]
        config = SimpleNamespace(api_key="test-key")
        with tempfile.TemporaryDirectory() as tmp:
            store = TranscriptStore(Path(tmp) / ".pyagent")

            with patch("builtins.input", return_value="n"):
                with contextlib.redirect_stdout(io.StringIO()):
                    handled = _handle_plan_review_message(agent, config, store, "please start")

        self.assertTrue(handled)
        self.assertEqual(agent.state.planning_status, "needs_confirmation")
        self.assertEqual(len(agent.prompts), 1)

    def test_plan_review_confirmation_uses_saved_plan_artifact_candidate(self) -> None:
        agent = FakeAgent()
        agent.state.planning_status = "needs_confirmation"
        agent.state.planning_request = "Add a planning command"
        agent.state.plan_artifact_candidate = {
            "goal": "Stored candidate",
            "summary": "Use stored candidate",
            "planned_files": ["pyagent/cli.py"],
            "non_goals": ["Do not build a full PlanStore"],
            "constraints": ["Keep current_step free text"],
            "slices": [
                {
                    "id": "slice-1",
                    "purpose": "Use stored candidate",
                    "files": ["pyagent/cli.py"],
                    "check": "python -m unittest tests.test_plan_task_cli",
                }
            ],
            "current_slice_id": "slice-1",
            "current_step": "Run stored candidate",
            "verification": ["python -m unittest tests.test_plan_task_cli"],
        }
        agent.ask_responses = [
            'PlanTransitionDecision\n```json\n{"action":"confirm_execution","artifact":null}\n```',
            "",
        ]
        config = SimpleNamespace(api_key="test-key")
        with tempfile.TemporaryDirectory() as tmp:
            store = TranscriptStore(Path(tmp) / ".pyagent")

            with patch("builtins.input", return_value="y"):
                with contextlib.redirect_stdout(io.StringIO()):
                    handled = _handle_plan_review_message(agent, config, store, "please start")

        self.assertTrue(handled)
        self.assertEqual(agent.state.current_goal, "Stored candidate")
        self.assertEqual(agent.state.planned_files, ["pyagent/cli.py"])
        self.assertEqual(agent.state.current_slice_id, "slice-1")
        self.assertEqual(agent.state.locked_plan["constraints"], ["Keep current_step free text"])

    def test_plan_review_message_without_transition_keeps_review_state(self) -> None:
        agent = FakeAgent()
        agent.state.planning_status = "needs_confirmation"
        agent.state.planning_request = "Add a planning command"
        agent.ask_responses = ["I updated the plan notes without starting execution."]
        config = SimpleNamespace(api_key="test-key")
        with tempfile.TemporaryDirectory() as tmp:
            store = TranscriptStore(Path(tmp) / ".pyagent")

            with contextlib.redirect_stdout(io.StringIO()):
                handled = _handle_plan_review_message(agent, config, store, "补充一个约束")

        self.assertTrue(handled)
        self.assertEqual(agent.state.planning_status, "needs_confirmation")
        self.assertEqual(len(agent.prompts), 1)

    def test_session_load_saves_current_and_switches_context(self) -> None:
        agent = FakeAgent()
        agent.state.session_id = "old-session"
        agent.state.planning_status = "needs_confirmation"
        agent.state.planning_request = "Old request"
        with tempfile.TemporaryDirectory() as tmp:
            store = TranscriptStore(Path(tmp) / ".pyagent")
            agent.store = store
            target = store.load("target-session")
            target.planning_status = "locked"
            target.planning_request = "Target request"
            target.current_goal = "Target goal"
            target.locked_plan = {"goal": "Target goal", "summary": "Target plan"}
            target.current_slice_id = "slice-target"
            store.save_state(target)

            with contextlib.redirect_stdout(io.StringIO()) as output:
                _run_session_command(agent, store, "/session load target-session")

            old = store.load("old-session")

        self.assertEqual(agent.state.session_id, "target-session")
        self.assertEqual(agent.state.planning_status, "locked")
        self.assertEqual(agent.state.current_goal, "Target goal")
        self.assertEqual(agent.state.current_slice_id, "slice-target")
        self.assertEqual(old.planning_status, "needs_confirmation")
        self.assertIn("session switched", output.getvalue())

    def test_session_current_reports_active_context(self) -> None:
        agent = FakeAgent()
        agent.state.session_id = "current-session"
        agent.state.planning_status = "executing"
        with tempfile.TemporaryDirectory() as tmp:
            store = TranscriptStore(Path(tmp) / ".pyagent")

            with contextlib.redirect_stdout(io.StringIO()) as output:
                _run_session_command(agent, store, "/session current")

        self.assertIn("current-session", output.getvalue())
        self.assertIn("executing", output.getvalue())

    def test_transcript_store_load_prefers_compacted_message_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = TranscriptStore(Path(tmp) / ".pyagent")
            state = store.load("memory-session")
            state.messages = [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "compacted user"},
            ]
            state.planning_status = "needs_confirmation"
            state.plan_artifact_candidate = {
                "goal": "Stored candidate",
                "summary": "Stored summary",
                "planned_files": ["a.py"],
                "current_step": "step",
            }
            store.append("memory-session", {"role": "user", "content": "old transcript only"})
            store.save_messages(state)
            store.save_state(state)

            loaded = store.load("memory-session")

        self.assertEqual([message["content"] for message in loaded.messages], ["system", "compacted user"])
        self.assertEqual(loaded.planning_status, "needs_confirmation")
        self.assertEqual(loaded.plan_artifact_candidate["goal"], "Stored candidate")


if __name__ == "__main__":
    unittest.main()
