"""Tests for the score, gaps, manifest and request commands.

The commands exist to make it harder to certify something that is not true, so
most of these are negative tests: each one removes or corrupts exactly one
precondition and asserts the toolkit refuses.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts" / "mature_product_toolkit.py"
BATCH = 43
PACK_KEY = "extensions-test-pack"
OWNER = "test-owner"
EXECUTOR = "executor@test"
VERIFIER = "verifier@test"
STARTED = "2026-08-06T09:00:00Z"
FINISHED = "2026-08-06T09:01:00Z"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *args], cwd=ROOT, text=True, capture_output=True, check=False
    )


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


class ToolkitExtensionsTest(unittest.TestCase):
    def scaffold(self, root: Path) -> Path:
        result = run("scaffold", "--batch", str(BATCH), "--key", PACK_KEY, "--owner", OWNER,
                     "--output-root", str(root))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        return root / f"batch{BATCH}" / PACK_KEY

    def complete_pack(self, root: Path) -> Path:
        """A pack with every machine-derivable precondition satisfied."""
        pack = self.scaffold(root)
        (pack / "artifact").mkdir(exist_ok=True)
        (pack / "environment").mkdir(exist_ok=True)
        (pack / "artifact" / "surface.json").write_text('{"artifact": true}\n')
        (pack / "environment" / "toolchain.json").write_text('{"environment": true}\n')
        (pack / "holdout" / "holdout-corpus.json").write_text('{"cases": ["h1"]}\n')
        (pack / "representative" / "representative-corpus.json").write_text('{"cases": ["r1"]}\n')
        for role, name in (("execution", "run-record"), ("provenance", "run-provenance"),
                           ("verification", "independent-replay")):
            path = pack / "evidence" / role / f"{name}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"role": role}) + "\n")

        evidence = read(pack / "evidence.json")
        evidence["packKey"] = PACK_KEY
        evidence["claims"] = [{
            "claimId": "example-claim",
            "status": "PASS",
            "evidenceRefs": ["run-record", "independent-replay"],
            "provenanceRefs": ["run-provenance"],
            "externalOperationExecuted": False,
            "authorizationRefs": [],
        }]
        write(pack / "evidence.json", evidence)

        certification = read(pack / "certification.json")
        certification["approvedBy"] = [OWNER, "accountable-approver"]
        write(pack / "certification.json", certification)

        claims = read(pack / "claims.json")
        claims["claims"] = [{
            "claimId": "example-claim",
            "statement": "The example capability behaved as specified during the recorded run.",
            "limitations": ["Covers the example capability only."],
            "evidenceRefs": ["run-record"],
        }]
        write(pack / "claims.json", claims)
        return pack

    def manifest_args(self, pack: Path, *overrides: str) -> list[str]:
        return [
            "manifest", "--batch", str(BATCH), str(pack),
            "--artifact", str(pack / "artifact" / "surface.json"),
            "--environment", str(pack / "environment" / "toolchain.json"),
            "--executor", EXECUTOR, "--verifier", VERIFIER,
            "--authorization", "AUTH-1",
            "--replay-command", "make batch43-evidence",
            "--started-at", STARTED, "--finished-at", FINISHED,
            "--attest-verifier-independent", "--attest-corpus-independence",
            *overrides,
        ]

    # ---- score ---------------------------------------------------------
    def test_score_is_the_mean_and_orders_by_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.scaffold(Path(tmp))
            payload = read(pack / "candidates.json")
            payload["candidates"] = [
                {"id": "low", "customerDemand": 0.0, "riskReduction": 0.0, "reuse": 0.0,
                 "readiness": 0.0, "margin": 0.5, "score": 0.0, "evidenceRefs": ["e1"]},
                {"id": "high", "customerDemand": 1.0, "riskReduction": 1.0, "reuse": 1.0,
                 "readiness": 1.0, "margin": 1.0, "score": 0.0, "evidenceRefs": []},
            ]
            write(pack / "candidates.json", payload)
            result = run("score", "--batch", str(BATCH), str(pack / "candidates.json"), "--write")
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            rows = read(pack / "candidates.json")["candidates"]
            self.assertEqual(["high", "low"], [row["id"] for row in rows])
            self.assertEqual(1.0, rows[0]["score"])
            self.assertEqual(0.1, rows[1]["score"])

    def test_score_marks_candidates_without_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.scaffold(Path(tmp))
            run("score", "--batch", str(BATCH), str(pack / "candidates.json"), "--write")
            rows = read(pack / "candidates.json")["candidates"]
            self.assertTrue(rows[0]["unevidenced"], "a candidate with no evidenceRefs must be flagged")

    def test_score_rejects_an_out_of_range_dimension(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.scaffold(Path(tmp))
            payload = read(pack / "candidates.json")
            payload["candidates"][0]["customerDemand"] = 7.0
            write(pack / "candidates.json", payload)
            self.assertNotEqual(0, run("score", "--batch", str(BATCH), str(pack / "candidates.json")).returncode)

    def test_score_without_write_leaves_the_file_alone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.scaffold(Path(tmp))
            before = (pack / "candidates.json").read_bytes()
            self.assertEqual(0, run("score", "--batch", str(BATCH), str(pack / "candidates.json")).returncode)
            self.assertEqual(before, (pack / "candidates.json").read_bytes())

    # ---- gaps ----------------------------------------------------------
    def test_gaps_reports_a_fresh_scaffold_as_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.scaffold(Path(tmp))
            result = run("gaps", "--batch", str(BATCH), str(pack))
            self.assertEqual(1, result.returncode)
            inventory = read(pack / "gap-inventory.json")
            self.assertGreater(inventory["blockingCount"], 0)
            categories = {gap["category"] for gap in inventory["gaps"]}
            for expected in ("provenance", "corpus", "approval", "metric", "zero-tolerance", "evidence"):
                self.assertIn(expected, categories, f"a fresh scaffold must report a {expected} gap")
            # scaffold substitutes the owner, so a fresh pack has no placeholder.
            self.assertNotIn("ownership", categories)

    def test_gaps_catches_an_owner_reverted_to_a_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.scaffold(Path(tmp))
            program = read(pack / "program.json")
            program["owner"] = "REPLACE_ME"
            write(pack / "program.json", program)
            run("gaps", "--batch", str(BATCH), str(pack), "--allow-blocking")
            gaps = read(pack / "gap-inventory.json")["gaps"]
            self.assertTrue(any(gap["category"] == "ownership" and gap["severity"] == "blocking"
                                for gap in gaps))

    def test_gaps_allow_blocking_still_reports_but_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.scaffold(Path(tmp))
            result = run("gaps", "--batch", str(BATCH), str(pack), "--allow-blocking")
            self.assertEqual(0, result.returncode)
            self.assertGreater(read(pack / "gap-inventory.json")["blockingCount"], 0)

    def test_gaps_separates_unmeasured_from_measured_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.scaffold(Path(tmp))
            metrics = read(pack / "metrics.json")
            target = metrics["metrics"][0]["name"]
            metrics["metrics"][0].update({"measured": True, "value": 0.0, "evidenceRefs": ["e1"],
                                          "comparator": "min", "threshold": 1.0})
            write(pack / "metrics.json", metrics)
            run("gaps", "--batch", str(BATCH), str(pack), "--allow-blocking")
            gaps = read(pack / "gap-inventory.json")["gaps"]
            entry = next(gap for gap in gaps if gap["category"] == "metric" and target in gap["detail"])
            self.assertEqual("open", entry["severity"], "a measured shortfall is open, not a missing measurement")
            self.assertIn("below the required", entry["detail"])

    def test_gaps_rejects_a_measurement_without_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.scaffold(Path(tmp))
            metrics = read(pack / "metrics.json")
            target = metrics["metrics"][0]["name"]
            metrics["metrics"][0].update({"measured": True, "value": 1.0, "evidenceRefs": []})
            write(pack / "metrics.json", metrics)
            run("gaps", "--batch", str(BATCH), str(pack), "--allow-blocking")
            details = [gap["detail"] for gap in read(pack / "gap-inventory.json")["gaps"]
                       if gap["severity"] == "blocking"]
            self.assertTrue(any(target in detail and "no evidence reference" in detail for detail in details))

    def test_gaps_rejects_a_nonzero_zero_tolerance_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.scaffold(Path(tmp))
            flags = read(pack / "zero-tolerance.json")
            target = flags["flags"][0]["name"]
            flags["flags"][0].update({"evaluated": True, "observed": 3, "evidenceRefs": ["e1"]})
            write(pack / "zero-tolerance.json", flags)
            run("gaps", "--batch", str(BATCH), str(pack), "--allow-blocking")
            details = [gap["detail"] for gap in read(pack / "gap-inventory.json")["gaps"]
                       if gap["severity"] == "blocking"]
            self.assertTrue(any(target in detail and "observed 3" in detail for detail in details))

    def test_gaps_blocks_a_passing_claim_without_stated_limitations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.complete_pack(Path(tmp))
            claims = read(pack / "claims.json")
            claims["claims"] = []
            write(pack / "claims.json", claims)
            run("gaps", "--batch", str(BATCH), str(pack), "--allow-blocking")
            gaps = read(pack / "gap-inventory.json")["gaps"]
            self.assertTrue(any(gap["category"] == "claim-scope" and gap["severity"] == "blocking"
                                for gap in gaps))

    def test_gaps_flags_a_narrative_with_no_matching_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.complete_pack(Path(tmp))
            claims = read(pack / "claims.json")
            claims["claims"].append({"claimId": "orphan-claim",
                                     "statement": "A claim nobody declared in evidence.json.",
                                     "limitations": ["none"]})
            write(pack / "claims.json", claims)
            run("gaps", "--batch", str(BATCH), str(pack), "--allow-blocking")
            gaps = read(pack / "gap-inventory.json")["gaps"]
            self.assertTrue(any(gap["category"] == "claim-scope" and "orphan-claim" in gap["detail"]
                                for gap in gaps))

    def test_gaps_never_grants_a_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.complete_pack(Path(tmp))
            run("gaps", "--batch", str(BATCH), str(pack), "--allow-blocking")
            self.assertEqual("NOT_RUN", read(pack / "certification.json")["status"])
            self.assertNotEqual("CERTIFIED", read(pack / "gate-result.json").get("status"))

    # ---- manifest ------------------------------------------------------
    def test_manifest_succeeds_on_a_complete_pack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.complete_pack(Path(tmp))
            result = run(*self.manifest_args(pack))
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            manifest = read(pack / "evidence-manifest.json")
            self.assertEqual({"execution", "provenance", "verification"},
                             {entry["role"] for entry in manifest["evidence"]})
            self.assertEqual(["holdout", "representative"],
                             sorted(entry["kind"] for entry in manifest["corpora"]))
            self.assertTrue(manifest["execution"]["verifierIndependent"])
            self.assertIn(OWNER, manifest["approvals"])

    def test_manifest_refuses_when_the_verifier_is_the_executor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.complete_pack(Path(tmp))
            args = self.manifest_args(pack)
            args[args.index("--verifier") + 1] = EXECUTOR
            result = run(*args)
            self.assertEqual(2, result.returncode)
            self.assertIn("different identities", result.stdout)

    def test_manifest_refuses_without_the_independence_attestation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.complete_pack(Path(tmp))
            args = [item for item in self.manifest_args(pack) if item != "--attest-verifier-independent"]
            result = run(*args)
            self.assertEqual(2, result.returncode)
            self.assertIn("--attest-verifier-independent", result.stdout)

    def test_manifest_refuses_without_the_corpus_attestation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.complete_pack(Path(tmp))
            args = [item for item in self.manifest_args(pack) if item != "--attest-corpus-independence"]
            result = run(*args)
            self.assertEqual(2, result.returncode)
            self.assertIn("--attest-corpus-independence", result.stdout)

    def test_manifest_refuses_without_an_authorization_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.complete_pack(Path(tmp))
            args = self.manifest_args(pack)
            index = args.index("--authorization")
            del args[index:index + 2]
            result = run(*args)
            self.assertEqual(2, result.returncode)
            self.assertIn("authorization", result.stdout)

    def test_manifest_refuses_evidence_outside_a_role_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.complete_pack(Path(tmp))
            (pack / "evidence" / "stray.json").write_text('{"stray": true}\n')
            result = run(*self.manifest_args(pack))
            self.assertEqual(2, result.returncode)
            self.assertIn("evidence/<role>/", result.stdout)

    def test_manifest_refuses_evidence_no_claim_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.complete_pack(Path(tmp))
            (pack / "evidence" / "execution" / "unreferenced.json").write_text('{"orphan": true}\n')
            result = run(*self.manifest_args(pack))
            self.assertEqual(2, result.returncode)
            self.assertIn("not referenced by any claim", result.stdout)

    def test_manifest_refuses_an_ambiguous_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.complete_pack(Path(tmp))
            (pack / "holdout" / "second-corpus.json").write_text('{"cases": ["h2"]}\n')
            result = run(*self.manifest_args(pack))
            self.assertEqual(2, result.returncode)
            self.assertIn("exactly one non-empty corpus file", result.stdout)

    def test_manifest_refuses_when_the_owner_did_not_approve(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.complete_pack(Path(tmp))
            certification = read(pack / "certification.json")
            certification["approvedBy"] = ["somebody-else"]
            write(pack / "certification.json", certification)
            result = run(*self.manifest_args(pack))
            self.assertEqual(2, result.returncode)
            self.assertIn("program owner", result.stdout)

    # ---- request -------------------------------------------------------
    def test_request_binds_the_exact_bytes_it_certifies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.complete_pack(Path(tmp))
            self.assertEqual(0, run(*self.manifest_args(pack)).returncode)
            result = run("request", "--batch", str(BATCH), str(pack), "--key-id", "offline-key-1")
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            request = read(pack / "certification-request.json")
            before = request["evidenceDigest"]

            evidence = read(pack / "evidence.json")
            evidence["claims"][0]["status"] = "FAIL"
            write(pack / "evidence.json", evidence)
            self.assertEqual(0, run("request", "--batch", str(BATCH), str(pack), "--key-id", "offline-key-1").returncode)
            self.assertNotEqual(before, read(pack / "certification-request.json")["evidenceDigest"],
                                "editing evidence.json must invalidate the previous request digest")

    def test_request_refuses_when_the_key_belongs_to_the_executor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.complete_pack(Path(tmp))
            self.assertEqual(0, run(*self.manifest_args(pack)).returncode)
            result = run("request", "--batch", str(BATCH), str(pack), "--key-id", EXECUTOR)
            self.assertEqual(2, result.returncode)
            self.assertIn("differ from the executor", result.stdout)

    def test_request_prints_the_signing_command_rather_than_signing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.complete_pack(Path(tmp))
            self.assertEqual(0, run(*self.manifest_args(pack)).returncode)
            result = run("request", "--batch", str(BATCH), str(pack), "--key-id", "offline-key-1")
            self.assertIn("openssl dgst -sha256 -sign", result.stdout)
            self.assertFalse((pack / "certification-request.sig").exists(),
                             "the toolkit must never produce a signature itself")


if __name__ == "__main__":
    unittest.main()
