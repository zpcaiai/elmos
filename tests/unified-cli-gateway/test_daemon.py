"""Unit & integration tests for Git PR Autonomous Self-Healing Daemon."""

from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

from elmos_cli.daemon import SelfHealingAnalyzer, process_webhook_event
from elmos_cli.dispatcher import main


class DaemonSelfHealingTests(unittest.TestCase):
    """Test PR code analysis, self-healing patch generation, and webhook events."""

    def test_analyze_legacy_vector_and_hashtable(self) -> None:
        legacy_code = (
            "public class LegacyAccount {\n"
            "  public Vector<String> history = new Vector<>();\n"
            "  public Hashtable<String, Object> state = new Hashtable<>();\n"
            "}\n"
        )
        res = SelfHealingAnalyzer.analyze_code_snippet(legacy_code, "LegacyAccount.java")
        self.assertTrue(res["needs_healing"])
        self.assertEqual(len(res["diagnostics"]), 2)
        self.assertIn("List<String>", res["healed_code"])
        self.assertIn("Map<String, Object>", res["healed_code"])
        self.assertIn("--- a/LegacyAccount.java", res["git_patch"])
        self.assertIn("+++ b/LegacyAccount.java", res["git_patch"])
        self.assertEqual(len(res["patch_sha256"]), 64)
        self.assertIn("ELMOS-RULE-JAVA-001", res["review_markdown"])

    def test_clean_code_requires_no_healing(self) -> None:
        clean_code = "public class CleanService {\n  private final List<String> items = new ArrayList<>();\n}\n"
        res = SelfHealingAnalyzer.analyze_code_snippet(clean_code, "CleanService.java")
        self.assertFalse(res["needs_healing"])
        self.assertEqual(len(res["diagnostics"]), 0)
        self.assertEqual(res["git_patch"], "")

    def test_process_webhook_event(self) -> None:
        event = {
            "action": "opened",
            "pull_request": {"number": 42},
            "repository": {"full_name": "acme/payment-service"},
            "changed_file_content": "public class BillingJob {\n  public Vector<Double> records;\n}",
            "changed_file_path": "src/BillingJob.java",
        }
        res = process_webhook_event(event)
        self.assertEqual(res["pr_number"], 42)
        self.assertEqual(res["repo"], "acme/payment-service")
        self.assertEqual(res["status"], "PROCESSED_WITH_HEALING")
        self.assertTrue(res["auto_fix_applied"])
        self.assertIn("List<Double>", res["git_patch"])

    def test_cli_daemon_simulate_event(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            event_file = Path(td) / "pr_event.json"
            event_payload = {
                "action": "synchronize",
                "pull_request": {"number": 105},
                "repository": {"full_name": "acme/auth-service"},
                "changed_file_content": "System.out.println(\"logging event\");",
                "changed_file_path": "Auth.java",
            }
            event_file.write_text(json.dumps(event_payload), encoding="utf-8")

            stdout_orig = sys.stdout
            sys.stdout = io.StringIO()
            try:
                code = main(["daemon", "--simulate-event", str(event_file)])
                self.assertEqual(code, 0)
                out = sys.stdout.getvalue()
                data = json.loads(out)
                self.assertEqual(data["pr_number"], 105)
                self.assertEqual(data["status"], "PROCESSED_WITH_HEALING")
                self.assertIn("logger.info", data["git_patch"])
            finally:
                sys.stdout = stdout_orig


if __name__ == "__main__":
    unittest.main()
