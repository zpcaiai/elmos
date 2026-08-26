from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/operations/assess_spring_boot_4_1_external_readiness.py"
SPEC = importlib.util.spec_from_file_location("spring_external_readiness", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
READINESS = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = READINESS
SPEC.loader.exec_module(READINESS)


class SpringExternalReadinessTests(unittest.TestCase):
    PACK = ROOT / "framework-packs/spring-to-boot-4-1-0"

    def test_current_pack_reports_unrun_external_roles_without_mutation(self) -> None:
        result = READINESS.assess(self.PACK)
        self.assertEqual(result["decision"], "NOT_READY_FOR_EXTERNAL_GATE")
        self.assertFalse(result["certification_eligible"])
        self.assertEqual(result["certification_status"], "NOT_CERTIFIED")
        self.assertEqual(
            result["local_route_evidence"]["routes"],
            [
                "boot-2.7-maven-to-boot-4.1.0-java-21",
                "boot-3.5-maven-to-boot-4.1.0-java-21",
            ],
        )
        self.assertEqual(
            set(result["external_evidence_boundary"].values()), {"NOT_RUN"}
        )
        checks = {item["role"]: item for item in result["readiness_checks"]}
        self.assertEqual(checks["independent_holdout"]["status"], "NOT_RUN")
        self.assertEqual(checks["representative_repository"]["status"], "NOT_RUN")
        self.assertEqual(checks["independent_verifier"]["status"], "NOT_RUN")

    def test_docker_preflight_blocker_is_diagnostic_not_external_evidence(self) -> None:
        result = READINESS.assess(self.PACK, engine=Path("/usr/local/bin/docker"))
        checks = {item["role"]: item for item in result["readiness_checks"]}
        self.assertEqual(checks["protected_rootless_runner"]["status"], "BLOCKED")
        self.assertEqual(
            result["external_evidence_boundary"]["rootless_runner"], "NOT_RUN"
        )

    def test_readme_only_corpus_is_not_counted_as_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="spring-readiness-corpus-") as directory:
            corpus = Path(directory)
            (corpus / "README.md").write_text("placeholder", encoding="utf-8")
            self.assertEqual(
                READINESS.corpus_readiness(corpus, "holdout")["status"], "NOT_RUN"
            )
            (corpus / "candidate.json").write_text(
                json.dumps({"synthetic": True}), encoding="utf-8"
            )
            self.assertEqual(
                READINESS.corpus_readiness(corpus, "holdout")["status"],
                "EVIDENCE_PENDING",
            )


if __name__ == "__main__":
    unittest.main()
