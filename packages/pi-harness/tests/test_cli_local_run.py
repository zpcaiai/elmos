from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout

from elmos_pi_harness.cli import main


class TestCliLocalRun(unittest.TestCase):
    def test_cli_local_run_json_output(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main([
                "local-run",
                "--objective", "Verify unit test run",
                "--allowed-tools", "tool.echo,repo.read",
                "--denied-tools", "network.egress",
                "--json",
            ])
        self.assertEqual(code, 0)
        output = buf.getvalue()
        data = json.loads(output)
        self.assertEqual(data["status"], "COMPLETED")
        self.assertEqual(data["mode"], "ephemeral-local")
        self.assertIn("tool.echo", data["allowed_capabilities"])
        self.assertIn("network.egress", data["denied_capabilities"])
        self.assertEqual(data["external_evidence"], "NOT_RUN")
        self.assertEqual(data["certification"], "NOT_CERTIFIED")
        self.assertEqual(len(data["executed_tools"]), 1)
        self.assertEqual(data["executed_tools"][0]["status"], "completed")

    def test_cli_local_run_human_output(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main([
                "local-run",
                "--objective", "Human readable smoke test",
            ])
        self.assertEqual(code, 0)
        output = buf.getvalue()
        self.assertIn("=== Elmos PI Harness Ephemeral Local Run ===", output)
        self.assertIn("COMPLETED", output)
        self.assertIn("NOT_CERTIFIED", output)


if __name__ == "__main__":
    unittest.main()
