from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pyagent.permissions import PermissionManager
from pyagent.tools.bash_policy import BashPolicy


FIXTURES = Path(__file__).parent / "fixtures"


class SecurityPolicyFixtureTests(unittest.TestCase):
    def test_bash_policy_fixture_cases(self) -> None:
        policy = BashPolicy()
        cases = json.loads((FIXTURES / "bash_policy_cases.json").read_text(encoding="utf-8"))

        for case in cases:
            with self.subTest(case=case["name"]):
                decision = policy.decide(case["command"], mode=case.get("mode", "default"))

                self.assertEqual(decision.behavior, case["behavior"])
                self.assertEqual(decision.classification, case["classification"])
                for tag in case.get("risk_tags", []):
                    self.assertIn(tag, decision.risk_tags)

    def test_path_policy_fixture_cases(self) -> None:
        cases = json.loads((FIXTURES / "path_policy_cases.json").read_text(encoding="utf-8"))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for case in cases:
                with self.subTest(case=case["name"]):
                    manager = PermissionManager(
                        cwd=root,
                        config_dir=root / ".pyagent",
                        mode=case.get("mode", "default"),
                        interactive=False,
                    )
                    decision = manager.decide(case["tool"], case["args"])

                    self.assertEqual(decision.behavior, case["behavior"])
                    self.assertEqual(decision.classification, case["classification"])
                    self.assertEqual(decision.policy, case["policy"])


if __name__ == "__main__":
    unittest.main()
