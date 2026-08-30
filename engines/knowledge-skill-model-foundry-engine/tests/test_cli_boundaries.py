"""Stable fail-closed CLI behavior for hostile or malformed JSON flags."""

from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
import unittest

from elmos_foundry.cli import main
from elmos_foundry.pipelines import EXPECTED_PIPELINES


class CliBoundaryTests(unittest.TestCase):
    _SCOPE = (
        "--tenant",
        "tenant-cli",
        "--project",
        "project-cli",
        "--actor",
        "actor-cli",
        "--environment",
        "env-cli",
        "--workspace-digest",
        "sha256:" + "a" * 64,
        "--revision",
        "sha256:" + "b" * 64,
        "--invocation",
        "invocation-cli",
        "--lease",
        "lease-cli",
    )

    def _blocked(self, argv: list[str]) -> dict[str, object]:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = main(argv)
        self.assertEqual(code, 2)
        result = json.loads(stdout.getvalue())
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["execution_status"], "NOT_RUN")
        self.assertEqual(result["certification_status"], "NOT_CERTIFIED")
        return result

    def test_non_object_json_is_stably_blocked_for_every_object_flag(self) -> None:
        pipeline = sorted(EXPECTED_PIPELINES)[0]
        commands = (
            [
                "route",
                "elmos-00-foundation-contracts",
                "--filters-json",
                "[]",
            ],
            ["pipeline", pipeline, "--params-json", "[]", *self._SCOPE],
            [
                "skill",
                "typed-skill-contract",
                "--inputs-json",
                "[]",
                *self._SCOPE,
            ],
        )
        for command in commands:
            with self.subTest(command=command[0]):
                result = self._blocked(list(command))
                self.assertIn("JSON object", str(result["error"]))

    def test_malformed_duplicate_and_non_finite_json_are_blocked(self) -> None:
        for value in ('{"broken":', '{"key":1,"key":2}', '{"score":NaN}'):
            with self.subTest(value=value):
                self._blocked(
                    [
                        "route",
                        "elmos-00-foundation-contracts",
                        "--filters-json",
                        value,
                    ]
                )


if __name__ == "__main__":
    unittest.main()
