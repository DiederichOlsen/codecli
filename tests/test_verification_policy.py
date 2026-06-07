from __future__ import annotations

import unittest
from pathlib import Path

from pyagent.messages import AgentState
from pyagent.verification import VerificationPolicy, is_verification_command


class VerificationPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = VerificationPolicy()

    def test_verification_command_detection(self) -> None:
        positive = [
            "pytest",
            "python -m unittest discover -s tests",
            "python.exe -m compileall pyagent",
            r"D:\Tool\Anaconda\envs\codecli\python.exe -m unittest discover -s tests",
            "npm test",
            "cargo check",
            "ruff check pyagent",
        ]
        negative = ["git status", "python script.py", "npm install"]

        for command in positive:
            with self.subTest(command=command):
                self.assertTrue(is_verification_command(command))
        for command in negative:
            with self.subTest(command=command):
                self.assertFalse(is_verification_command(command))

    def test_status_progression(self) -> None:
        state = AgentState()

        self.assertEqual(self.policy.status(state), "not_required")

        self.policy.record_file_change(state, path=Path("pyagent/example.py"), operation="edit")
        self.assertEqual(self.policy.status(state), "unverified")

        self.policy.maybe_record_command(
            state,
            command="python -m unittest discover -s tests",
            exit_code=0,
            success=True,
            summary="OK",
        )
        self.assertEqual(self.policy.status(state), "passed")

        self.policy.maybe_record_command(
            state,
            command="pytest",
            exit_code=1,
            success=False,
            summary="failed",
        )
        self.assertEqual(self.policy.status(state), "failed")

    def test_non_verification_command_is_not_recorded(self) -> None:
        state = AgentState()

        recorded = self.policy.maybe_record_command(
            state,
            command="git status",
            exit_code=0,
            success=True,
            summary="clean",
        )

        self.assertFalse(recorded)
        self.assertEqual(state.verification_commands, [])


if __name__ == "__main__":
    unittest.main()
