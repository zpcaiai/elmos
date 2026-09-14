from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/batch40_docker_local_evidence.py"
SPEC = importlib.util.spec_from_file_location("batch40_docker_local_evidence", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def hardened_inspect() -> dict:
    return {
        "Config": {"User": "65532:65532"},
        "HostConfig": {
            "NetworkMode": "none",
            "ReadonlyRootfs": True,
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges:true"],
            "Binds": None,
            "PidsLimit": 64,
            "Memory": 64 * 1024 * 1024,
            "NanoCpus": 500_000_000,
            "Tmpfs": {"/tmp": "rw,nosuid,nodev,noexec,size=16777216"},
        },
        "Mounts": [],
    }


def valid_probe() -> dict:
    return {
        "status": "PASS",
        "independentVerification": "NOT_RUN",
        "certificationStatus": "NOT_CERTIFIED",
        "controls": [{"controlId": "fixture", "status": "PASS", "details": ["ok"]}],
        "corpora": {
            "development": ["dev-a"],
            "holdout": ["holdout-a"],
            "representative": ["representative-a"],
        },
    }


class Batch40DockerLocalEvidenceTest(unittest.TestCase):
    def test_hardened_runtime_contract_passes(self) -> None:
        controls, observed = MODULE.validate_runtime_inspect(hardened_inspect())
        self.assertTrue(all(item["status"] == "PASS" for item in controls))
        self.assertEqual("none", observed["networkMode"])
        self.assertTrue(observed["readOnlyRootFilesystem"])

    def test_each_privilege_downgrade_fails_closed(self) -> None:
        mutations = (
            ("Config", "User", "0:0"),
            ("HostConfig", "NetworkMode", "bridge"),
            ("HostConfig", "ReadonlyRootfs", False),
            ("HostConfig", "CapDrop", []),
            ("HostConfig", "SecurityOpt", []),
            ("HostConfig", "PidsLimit", 0),
            ("HostConfig", "Memory", 0),
            ("HostConfig", "NanoCpus", 0),
            ("HostConfig", "Tmpfs", {}),
        )
        for section, key, value in mutations:
            with self.subTest(key=key):
                fixture = hardened_inspect()
                fixture[section][key] = value
                controls, _ = MODULE.validate_runtime_inspect(fixture)
                self.assertIn("FAIL", {item["status"] for item in controls})

    def test_probe_cannot_claim_independent_or_certified(self) -> None:
        for field, value in (
            ("independentVerification", "PASSED"),
            ("certificationStatus", "CERTIFIED"),
        ):
            with self.subTest(field=field):
                report = valid_probe()
                report[field] = value
                with self.assertRaises(MODULE.EvidenceError):
                    MODULE.validate_probe(report)

    def test_overlapping_corpora_fail_closed(self) -> None:
        report = valid_probe()
        report["corpora"]["representative"] = ["holdout-a"]
        with self.assertRaises(MODULE.EvidenceError):
            MODULE.validate_probe(report)

    def test_packaged_dockerfile_has_no_remote_base_and_is_nonroot(self) -> None:
        dockerfile = (ROOT / "scripts/batch40/Dockerfile.local-evidence").read_text()
        self.assertIn("FROM scratch", dockerfile)
        self.assertIn("USER 65532:65532", dockerfile)
        self.assertNotIn("http", dockerfile.lower())

    def test_committed_report_preserves_evidence_boundary_when_present(self) -> None:
        path = (
            ROOT / "mature-product-packs/batch40/elmos-platform-supply-chain"
            / "evidence/execution/b40-docker-local-evidence.json"
        )
        if not path.is_file():
            self.skipTest("Docker evidence is opt-in and has not been captured")
        report = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual("LOCAL_EXECUTED_SELF_ATTESTED", report["evidenceClass"])
        self.assertEqual("NOT_RUN", report["productionEvidence"])
        self.assertEqual("NOT_RUN", report["independentVerification"])
        self.assertEqual("NOT_CERTIFIED", report["certificationStatus"])
        self.assertFalse(report["externalOperationExecuted"])


if __name__ == "__main__":
    unittest.main()
