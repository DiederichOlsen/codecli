from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pyagent.context import build_system_prompt
from pyagent.design_trace import (
    RecommendationDraft,
    all_design_intents,
    find_design_intent,
    format_design_index,
    format_test_intent_map,
    missing_recommendation_fields,
    recommendation_protocol_prompt,
)


class DesignTraceTests(unittest.TestCase):
    def test_design_intent_ids_are_stable_and_unique(self) -> None:
        ids = [item.id for item in all_design_intents()]

        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("DT-RUNTIME-001", ids)
        self.assertIn("DT-TOOLS-001", ids)
        self.assertIn("DT-EDIT-001", ids)
        self.assertIn("DT-BASH-001", ids)
        self.assertIn("DT-VERIFY-001", ids)
        self.assertIn("DT-AUDIT-001", ids)
        self.assertIn("DT-MAINTAINABILITY-001", ids)
        self.assertIn("DT-PLANNING-002", ids)
        self.assertIn("DT-GOAL-001", ids)
        self.assertIn("DT-MEMORY-001", ids)

    def test_edit_intent_maps_to_read_before_write_tests(self) -> None:
        intent = find_design_intent("DT-EDIT-001")

        self.assertIsNotNone(intent)
        assert intent is not None
        joined = "\n".join(intent.test_paths)
        self.assertIn("test_edit_requires_prior_full_read", joined)
        self.assertIn("test_edit_rejects_partial_read_snapshot", joined)
        self.assertIn("test_edit_rejects_file_changed_since_read", joined)

    def test_formatters_expose_design_and_test_maps(self) -> None:
        design_index = format_design_index()
        test_map = format_test_intent_map()

        self.assertIn("Design Trace index", design_index)
        self.assertIn("DT-TOOLS-001", design_index)
        self.assertIn("pyagent/tools/executor.py", design_index)
        self.assertIn("Test intent map", test_map)
        self.assertIn("test_executor_returns_tool_result_for_invalid_json", test_map)

    def test_recommendation_protocol_rejects_naked_recommendations(self) -> None:
        prompt = recommendation_protocol_prompt()

        self.assertIn("No naked recommendation", prompt)
        self.assertIn("observed project facts", prompt)
        self.assertIn("failure modes", prompt)
        self.assertIn("tests, docs, or verification", prompt)

    def test_missing_recommendation_fields_reports_protocol_gaps(self) -> None:
        missing = missing_recommendation_fields(RecommendationDraft(decision="Keep ToolExecutor separate."))

        self.assertEqual(
            missing,
            [
                "evidence",
                "alternatives",
                "tradeoffs",
                "failure_modes",
                "triggers",
                "verification",
            ],
        )

    def test_system_prompt_includes_recommendation_protocol(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prompt = build_system_prompt(Path(tmp), ["Read", "Edit"])

        self.assertIn("Engineering recommendation protocol", prompt)
        self.assertIn("No naked recommendation", prompt)
        self.assertIn("Current working directory", prompt)


if __name__ == "__main__":
    unittest.main()
