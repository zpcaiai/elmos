from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "batch40_dependabot_alerts.py"
MODULE_SPEC = importlib.util.spec_from_file_location("batch40_dependabot_alerts", SCRIPT)
assert MODULE_SPEC and MODULE_SPEC.loader
MODULE = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(MODULE)


COMMIT = "a" * 40
ENDPOINT = "https://api.github.com/repos/zpcaiai/elmos/dependabot/alerts"
QUERIED_AT = "2026-08-31T00:00:00Z"


def alert(number: int, state: str = "fixed", severity: str | None = None) -> dict:
    value = {
        "number": number,
        "state": state,
        "dependency": {
            "package": {"name": "setuptools"},
            "manifest_path": "engines/example/pyproject.toml",
        },
        "security_advisory": {"ghsa_id": f"GHSA-example-{number}"},
        "security_vulnerability": {},
    }
    if severity is not None:
        value["security_advisory"]["severity"] = severity
    return value


class DependabotAlertEvidenceTest(unittest.TestCase):
    def run_cli(self, payload: object) -> tuple[int, dict]:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "alerts.json"
            output = root / "report.json"
            raw_output = root / "raw-output.json"
            raw = json.dumps(payload, separators=(",", ":")).encode()
            source.write_bytes(raw)
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--alerts-file",
                    str(source),
                    "--repository",
                    "zpcaiai/elmos",
                    "--commit",
                    COMMIT,
                    "--endpoint",
                    ENDPOINT,
                    "--queried-at",
                    QUERIED_AT,
                    "--output",
                    str(output),
                    "--raw-output",
                    str(raw_output),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(raw, raw_output.read_bytes())
            return result.returncode, json.loads(output.read_text())

    def test_paginated_snapshot_with_no_open_alerts_passes(self) -> None:
        code, report = self.run_cli([[alert(1), alert(2)], []])
        self.assertEqual(0, code)
        self.assertEqual("PASS", report["status"])
        self.assertEqual(0, report["openCount"])
        self.assertEqual({"fixed": 2}, report["stateCounts"])
        self.assertEqual("sha256:", report["inputSha256"][:7])
        self.assertEqual(
            "gh api repos/zpcaiai/elmos/dependabot/alerts --paginate --slurp",
            report["replayCommand"],
        )

    def test_open_high_alert_blocks_and_is_not_hidden(self) -> None:
        code, report = self.run_cli([alert(3, "open", "high")])
        self.assertEqual(3, code)
        self.assertEqual("BLOCKED", report["status"])
        self.assertEqual(1, report["openBySeverity"]["high"])
        self.assertEqual("GHSA-example-3", report["openAlerts"][0]["ghsaId"])
        self.assertEqual(1, len(report["blockers"]))

    def test_open_medium_alert_uses_current_github_severity_name(self) -> None:
        code, report = self.run_cli([alert(31, "open", "medium")])
        self.assertEqual(3, code)
        self.assertEqual("BLOCKED", report["status"])
        self.assertEqual(1, report["openBySeverity"]["medium"])
        self.assertEqual(1, report["openCount"])

    def test_legacy_moderate_severity_normalizes_to_medium(self) -> None:
        code, report = self.run_cli([alert(32, "open", "moderate")])
        self.assertEqual(3, code)
        self.assertEqual("BLOCKED", report["status"])
        self.assertEqual(1, report["openBySeverity"]["medium"])
        self.assertNotIn("moderate", report["openBySeverity"])

    def test_open_alert_without_severity_fails_closed(self) -> None:
        code, report = self.run_cli([alert(4, "open")])
        self.assertEqual(2, code)
        self.assertEqual("INVALID", report["status"])
        self.assertIn("severity", report["error"])

    def test_duplicate_alert_numbers_fail_closed(self) -> None:
        code, report = self.run_cli([alert(5), alert(5)])
        self.assertEqual(2, code)
        self.assertEqual("INVALID", report["status"])
        self.assertIn("duplicate", report["error"])

    def test_invalid_commit_scope_fails_closed(self) -> None:
        raw = b"[]"
        with self.assertRaises(MODULE.AlertSnapshotError):
            MODULE.analyze_snapshot(
                raw,
                [],
                repository="zpcaiai/elmos",
                commit="short",
                endpoint=ENDPOINT,
                queried_at=QUERIED_AT,
            )


if __name__ == "__main__":
    unittest.main()
