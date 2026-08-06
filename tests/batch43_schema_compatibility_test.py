"""Tests for the Batch 43 schema compatibility check and the run-context capture.

The check exists to answer one question honestly: can a document that validated
against the baseline still validate today? Each test below introduces exactly
one change and asserts the verdict, including the changes it must NOT call
breaking — a checker that flags everything is as useless as one that flags
nothing.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "scripts" / "batch43_schema_compatibility_check.py"
CONTEXT = ROOT / "scripts" / "mature_product_run_context.py"

BASE = {
    "type": "object",
    "required": ["a"],
    "additionalProperties": True,
    "properties": {
        "a": {"type": "string"},
        "b": {"enum": ["x", "y"]},
        "c": {"type": "integer"},
        "d": {"type": "array", "minItems": 1},
    },
}


def write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


class SchemaCompatibilityTest(unittest.TestCase):
    def check(self, current: dict | None, baseline: dict | None = BASE) -> tuple[int, dict]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            if baseline is not None:
                write(root / "base" / "schemas" / "a.schema.json", baseline)
            else:
                (root / "base" / "schemas").mkdir(parents=True)
            if current is not None:
                write(root / "schemas" / "a.schema.json", current)
            else:
                (root / "schemas").mkdir(parents=True)
            output = root / "report.json"
            result = subprocess.run(
                [sys.executable, str(CHECK), "--repo", str(root),
                 "--baseline-dir", str(root / "base"), "--output", str(output)],
                capture_output=True, text=True, check=False,
            )
            return result.returncode, json.loads(output.read_text())

    def verdict(self, current: dict) -> tuple[str, list[str]]:
        code, report = self.check(current)
        entry = report["results"][0]
        breaking = [item["kind"] for item in entry["findings"] if item["breaking"]]
        return entry["verdict"], breaking

    def mutate(self, **changes) -> dict:
        payload = json.loads(json.dumps(BASE))
        payload.update(changes)
        return payload

    # ---- breaking changes ----------------------------------------------
    def test_a_newly_required_property_is_breaking(self) -> None:
        verdict, kinds = self.verdict(self.mutate(required=["a", "b"]))
        self.assertEqual("breaking", verdict)
        self.assertIn("required-added", kinds)

    def test_narrowing_an_enum_is_breaking(self) -> None:
        payload = json.loads(json.dumps(BASE))
        payload["properties"]["b"]["enum"] = ["x"]
        verdict, kinds = self.verdict(payload)
        self.assertEqual("breaking", verdict)
        self.assertIn("enum-narrowed", kinds)

    def test_changing_a_type_is_breaking(self) -> None:
        payload = json.loads(json.dumps(BASE))
        payload["properties"]["c"]["type"] = "string"
        verdict, kinds = self.verdict(payload)
        self.assertEqual("breaking", verdict)
        self.assertIn("type-changed", kinds)

    def test_closing_an_open_object_is_breaking(self) -> None:
        verdict, kinds = self.verdict(self.mutate(additionalProperties=False))
        self.assertEqual("breaking", verdict)
        self.assertIn("object-closed", kinds)

    def test_tightening_a_bound_is_breaking(self) -> None:
        payload = json.loads(json.dumps(BASE))
        payload["properties"]["d"]["minItems"] = 3
        verdict, kinds = self.verdict(payload)
        self.assertEqual("breaking", verdict)
        self.assertIn("bound-tightened", kinds)

    def test_introducing_a_bound_is_breaking(self) -> None:
        payload = json.loads(json.dumps(BASE))
        payload["properties"]["a"]["minLength"] = 5
        verdict, kinds = self.verdict(payload)
        self.assertEqual("breaking", verdict)
        self.assertIn("bound-introduced", kinds)

    def test_changing_a_pattern_is_breaking(self) -> None:
        payload = json.loads(json.dumps(BASE))
        payload["properties"]["a"]["pattern"] = "^z"
        base = json.loads(json.dumps(BASE))
        base["properties"]["a"]["pattern"] = "^a"
        code, report = self.check(payload, base)
        self.assertEqual("breaking", report["results"][0]["verdict"])

    def test_removing_a_property_from_a_closed_object_is_breaking(self) -> None:
        base = json.loads(json.dumps(BASE))
        base["additionalProperties"] = False
        payload = json.loads(json.dumps(base))
        del payload["properties"]["c"]
        code, report = self.check(payload, base)
        kinds = [item["kind"] for item in report["results"][0]["findings"] if item["breaking"]]
        self.assertIn("property-removed", kinds)

    # ---- changes that must NOT be called breaking ------------------------
    def test_adding_an_optional_property_is_compatible(self) -> None:
        payload = json.loads(json.dumps(BASE))
        payload["properties"]["e"] = {"type": "string"}
        verdict, kinds = self.verdict(payload)
        self.assertEqual("compatible", verdict)
        self.assertEqual([], kinds)

    def test_dropping_a_requirement_is_compatible(self) -> None:
        verdict, kinds = self.verdict(self.mutate(required=[]))
        self.assertEqual("compatible", verdict)
        self.assertEqual([], kinds)

    def test_widening_an_enum_is_compatible(self) -> None:
        payload = json.loads(json.dumps(BASE))
        payload["properties"]["b"]["enum"] = ["x", "y", "z"]
        verdict, kinds = self.verdict(payload)
        self.assertEqual([], kinds)

    def test_removing_a_property_from_an_open_object_is_not_breaking(self) -> None:
        payload = json.loads(json.dumps(BASE))
        del payload["properties"]["c"]
        verdict, kinds = self.verdict(payload)
        self.assertEqual([], kinds, "an open object still accepts the removed property")

    def test_an_identical_schema_is_unchanged(self) -> None:
        verdict, kinds = self.verdict(json.loads(json.dumps(BASE)))
        self.assertEqual("unchanged", verdict)

    def test_a_schema_with_no_baseline_is_added_not_compared(self) -> None:
        code, report = self.check(json.loads(json.dumps(BASE)), baseline=None)
        self.assertEqual("added", report["results"][0]["verdict"])
        self.assertEqual(0, report["totals"]["schemasCompared"],
                         "a schema with no baseline must not count toward the compatibility rate")

    # ---- reporting contract ---------------------------------------------
    def test_exit_code_three_signals_breaking_changes(self) -> None:
        code, report = self.check(self.mutate(required=["a", "b"]))
        self.assertEqual(3, code)
        self.assertEqual(1.0, report["metrics"]["unsupportedBreakingChangeCount"])

    def test_exit_code_zero_when_nothing_broke(self) -> None:
        code, report = self.check(json.loads(json.dumps(BASE)))
        self.assertEqual(0, code)
        self.assertEqual(0.0, report["metrics"]["unsupportedBreakingChangeCount"])
        self.assertEqual(1.0, report["metrics"]["schemaSurfaceCompatibilityRate"])

    def test_the_report_records_a_replay_command_and_tool_digest(self) -> None:
        code, report = self.check(json.loads(json.dumps(BASE)))
        self.assertTrue(report["replayCommand"])
        self.assertTrue(report["toolDigest"].startswith("sha256:"))
        self.assertIn("startedAt", report)
        self.assertIn("finishedAt", report)


class RunContextTest(unittest.TestCase):
    def build(self, tmp: Path, *, git_repo: bool) -> tuple[Path, Path, subprocess.CompletedProcess[str]]:
        repo = tmp / "repo"
        pack = repo / "pack"
        write(repo / "schemas" / "a.schema.json", BASE)
        report = pack / "evidence" / "execution" / "run.json"
        write(report, {"check": "demo-check", "batch": 43, "startedAt": "2026-08-06T09:00:00Z",
                       "finishedAt": "2026-08-06T09:00:05Z", "baselineRevision": "HEAD",
                       "replayCommand": "demo", "toolDigest": "sha256:" + "a" * 64})
        if git_repo:
            for command in (["git", "init", "-q"], ["git", "add", "-A"],
                            ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base"]):
                subprocess.run(command, cwd=repo, check=False, capture_output=True)
        result = subprocess.run(
            [sys.executable, str(CONTEXT), "--repo", str(repo), "--pack", str(pack),
             "--run-report", str(report), "--claim", "demo-claim", "--surface-root", "schemas"],
            capture_output=True, text=True, check=False,
        )
        return repo, pack, result

    def test_it_records_the_artifact_environment_and_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo, pack, result = self.build(Path(tmp), git_repo=True)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            surface = json.loads((pack / "artifact" / "schema-surface.json").read_text())
            self.assertEqual(1, surface["memberCount"])
            self.assertTrue(surface["compositeDigest"].startswith("sha256:"))
            environment = json.loads((pack / "environment" / "toolchain.json").read_text())
            self.assertTrue(environment["pythonVersion"])
            provenance = json.loads((pack / "evidence" / "provenance" / "demo-check-provenance.json").read_text())
            self.assertEqual(["demo-claim"], provenance["claimIds"])
            self.assertTrue(provenance["reproducible"], "a committed tree must be reported reproducible")

    def test_an_uncommitted_change_is_reported_as_not_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo, pack, _ = self.build(Path(tmp), git_repo=True)
            payload = json.loads(json.dumps(BASE))
            payload["title"] = "edited after the commit"
            write(repo / "schemas" / "a.schema.json", payload)
            report = pack / "evidence" / "execution" / "run.json"
            result = subprocess.run(
                [sys.executable, str(CONTEXT), "--repo", str(repo), "--pack", str(pack),
                 "--run-report", str(report), "--claim", "demo-claim", "--surface-root", "schemas"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(0, result.returncode)
            provenance = json.loads((pack / "evidence" / "provenance" / "demo-check-provenance.json").read_text())
            self.assertFalse(provenance["reproducible"])
            self.assertIn("does not reproduce", provenance["reproducibilityNote"])

    def test_it_refuses_an_empty_artifact_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            pack = repo / "pack"
            report = pack / "evidence" / "execution" / "run.json"
            write(report, {"check": "demo-check", "batch": 43})
            result = subprocess.run(
                [sys.executable, str(CONTEXT), "--repo", str(repo), "--pack", str(pack),
                 "--run-report", str(report), "--claim", "demo-claim"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(2, result.returncode)
            self.assertIn("artifact surface is empty", result.stderr)


if __name__ == "__main__":
    unittest.main()
