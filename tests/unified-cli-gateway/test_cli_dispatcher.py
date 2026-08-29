"""Unit & integration tests for the ELMOS Unified Enterprise CLI Gateway."""

from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import unittest

from elmos_cli.dispatcher import _get_global_status, main
from elmos_cli.composite_pipeline import run_composite_pipeline


class UnifiedCliGatewayTests(unittest.TestCase):
    def test_get_global_status(self) -> None:
        status = _get_global_status()
        self.assertEqual(status["status"], "HEALTHY")
        self.assertEqual(status["version"], "3.0.0")
        self.assertGreaterEqual(status["workspace_skills"], 4000)
        self.assertGreaterEqual(status["runtime_skills"], 6000)
        self.assertGreaterEqual(status["total_engines"], 40)
        self.assertGreaterEqual(len(status["ready_capabilities"]), 5)

    def test_cli_status_command(self) -> None:
        stdout_orig = sys.stdout
        sys.stdout = io.StringIO()
        try:
            exit_code = main(["status", "--json"])
            output = sys.stdout.getvalue()
            self.assertEqual(exit_code, 0)
            data = json.loads(output)
            self.assertEqual(data["status"], "HEALTHY")
        finally:
            sys.stdout = stdout_orig

    def test_cli_polyglot_subcommands(self) -> None:
        stdout_orig = sys.stdout
        sys.stdout = io.StringIO()
        try:
            exit_code = main(["polyglot", "status"])
            output = sys.stdout.getvalue()
            self.assertEqual(exit_code, 0)
            self.assertIn("ready", output.lower())
        finally:
            sys.stdout = stdout_orig

    def test_cli_foundry_subcommands(self) -> None:
        stdout_orig = sys.stdout
        sys.stdout = io.StringIO()
        try:
            exit_code = main(["foundry", "status"])
            output = sys.stdout.getvalue()
            self.assertEqual(exit_code, 0)
            data = json.loads(output)
            self.assertEqual(data["atomic_skills"], 1310)
            self.assertEqual(data["meta_skills"], 41)
        finally:
            sys.stdout = stdout_orig

    def test_cli_pipeline_execution(self) -> None:
        res = run_composite_pipeline(
            src_lang="java",
            tgt_lang="csharp",
            code_snippet="public class Calculator { public int multiply(int a, int b) { return a * b; } }",
        )
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["formal_assurance"]["verdict"], "SATISFIED")
        self.assertEqual(res["differential_fuzzing"]["status"], "PASS")
        self.assertTrue(res["evidence_bundle_digest"].startswith("sha256:"))
        self.assertEqual(res["receipt"]["certification"], "CERTIFIED")


if __name__ == "__main__":
    unittest.main()
