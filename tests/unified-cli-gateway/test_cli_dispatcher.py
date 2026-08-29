"""Unit & integration tests for the ELMOS Unified Enterprise CLI Gateway."""

from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

from elmos_cli.dispatcher import _get_global_status, main
from elmos_cli.composite_pipeline import run_composite_pipeline, derive_action_key


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
            exit_code = main(["foundry", "status", "--json"])
            output = sys.stdout.getvalue()
            self.assertEqual(exit_code, 0)
            data = json.loads(output)
            self.assertEqual(data["atomic_skills"], 1310)
            self.assertEqual(data["meta_skills"], 41)
        finally:
            sys.stdout = stdout_orig

    def test_cli_pipeline_execution_and_action_cache(self) -> None:
        # First execution (cold run)
        res1 = run_composite_pipeline(
            src_lang="java",
            tgt_lang="csharp",
            code_snippet="public class UserAuthService { public String token; }",
        )
        self.assertEqual(res1["status"], "SUCCESS")
        self.assertIn("receipt", res1)
        self.assertEqual(res1["receipt"]["slsa_level"], "SLSA_BUILD_LEVEL_3")
        self.assertFalse(res1.get("cache_hit", False))

        # Second execution (cache hit)
        res2 = run_composite_pipeline(
            src_lang="java",
            tgt_lang="csharp",
            code_snippet="public class UserAuthService { public String token; }",
        )
        self.assertEqual(res2["status"], "SUCCESS")
        self.assertTrue(res2.get("cache_hit", False))
        self.assertEqual(res1["action_key"], res2["action_key"])

    def test_cli_completion_subcommand(self) -> None:
        for sh in ["bash", "zsh", "fish"]:
            stdout_orig = sys.stdout
            sys.stdout = io.StringIO()
            try:
                code = main(["completion", sh])
                output = sys.stdout.getvalue()
                self.assertEqual(code, 0)
                self.assertIn("elmos", output)
            finally:
                sys.stdout = stdout_orig

    def test_cli_config_subcommand(self) -> None:
        stdout_orig = sys.stdout
        sys.stdout = io.StringIO()
        try:
            code = main(["config", "show", "--json"])
            output = sys.stdout.getvalue()
            self.assertEqual(code, 0)
            cfg = json.loads(output)
            self.assertIn("tenant_id", cfg)
            self.assertIn("smt_solver", cfg)
        finally:
            sys.stdout = stdout_orig

    def test_cli_export_html_report(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_html = Path(td) / "test_report.html"
            stdout_orig = sys.stdout
            sys.stdout = io.StringIO()
            try:
                code = main(["pipeline", "--src-lang", "java", "--tgt-lang", "rust", "--export-html", str(out_html)])
                self.assertEqual(code, 0)
                self.assertTrue(out_html.is_file())
                content = out_html.read_text(encoding="utf-8")
                self.assertIn("ELMOS Executive Assurance Report", content)
                self.assertIn("SLSA Level 3", content)
            finally:
                sys.stdout = stdout_orig


if __name__ == "__main__":
    unittest.main()
