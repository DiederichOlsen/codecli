from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from pyagent.agent import Agent
from pyagent.storage import TranscriptStore


class ContextBoundaryTests(unittest.TestCase):
    def test_compact_records_boundary_and_reinjects_plan_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = SimpleNamespace(
                cwd=Path(tmp),
                config_dir=Path(tmp) / ".pyagent",
                permission_mode="default",
                api_key="",
                base_url="https://example.invalid/v1",
                model="test-model",
                max_agent_turns=1,
                command_timeout=1,
                max_tool_output_chars=1000,
            )
            agent = Agent(config=config, interactive=False)
            agent.state.locked_plan = {
                "plan_id": "plan-123",
                "revision": 2,
                "goal": "Keep plan state recoverable",
                "summary": "Reinject plan state after compaction",
                "planned_files": ["pyagent/agent.py"],
            }
            agent.state.maintenance_digest = {
                "digest_id": "digest-123",
                "revision": 3,
                "mental_model": "Planning state and user understanding are restored after compaction.",
                "module_map": [{"module": "pyagent/agent.py", "responsibility": "Compacts context."}],
                "change_paths": [
                    {"scenario": "Change compaction", "start_at": "pyagent/agent.py", "notes": "Update boundary tests."},
                    {"scenario": "Change storage", "start_at": "pyagent/storage.py", "notes": "Update persistence tests."},
                ],
                "extension_points": ["Add new boundary metadata fields in AgentState."],
                "invariants": ["ContextBoundary is metadata, not a tool allowlist."],
                "handoff_notes": ["Inspect /status after compacting."],
            }
            for index in range(12):
                agent.state.messages.append(
                    {
                        "id": f"user-{index}",
                        "role": "user",
                        "content": f"message {index} " + ("x" * 100),
                    }
                )

            changed = agent.compact_now()

            self.assertTrue(changed)
            self.assertEqual(agent.state.compact_epoch, 1)
            self.assertEqual(len(agent.state.context_boundaries), 1)
            boundary = agent.state.context_boundaries[0]
            self.assertEqual(boundary["plan_id"], "plan-123")
            self.assertEqual(boundary["digest_id"], "digest-123")
            self.assertTrue(any(message.get("subtype") == "context_boundary" for message in agent.state.messages))
            compact_content = "\n".join(str(message.get("content", "")) for message in agent.state.messages)
            self.assertIn("Current locked PlanArtifact", compact_content)
            self.assertIn("Current MaintenanceDigest", compact_content)

            loaded = TranscriptStore(config.config_dir).load(agent.state.session_id)

            self.assertEqual(loaded.compact_epoch, 1)
            self.assertEqual(loaded.context_boundaries[0]["plan_id"], "plan-123")


if __name__ == "__main__":
    unittest.main()
