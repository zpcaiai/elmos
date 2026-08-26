from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


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

    def test_rootless_preflight_retries_transient_engine_unavailability(self) -> None:
        unavailable = subprocess.CompletedProcess(
            args=[],
            returncode=2,
            stdout=json.dumps({"reason": "CONTAINER_ENGINE_UNAVAILABLE"}),
            stderr="",
        )
        ready = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps({"status": "READY"}),
            stderr="",
        )
        with tempfile.TemporaryDirectory(prefix="spring-readiness-engine-") as directory:
            engine = Path(directory) / "podman"
            engine.touch()
            with patch.object(
                READINESS.subprocess,
                "run",
                side_effect=[unavailable, ready],
            ) as run, patch.object(READINESS.time, "sleep") as sleep:
                result = READINESS.rootless_preflight(engine)

        self.assertEqual(result["status"], "PREFLIGHT_READY")
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(run.call_count, 2)
        sleep.assert_called_once_with(READINESS.PREFLIGHT_RETRY_DELAY_SECONDS)

    def test_rootless_preflight_does_not_retry_policy_failure(self) -> None:
        blocked = subprocess.CompletedProcess(
            args=[],
            returncode=2,
            stdout=json.dumps({"reason": "ROOTLESS_CONTAINER_ENGINE_REQUIRED"}),
            stderr="",
        )
        with tempfile.TemporaryDirectory(prefix="spring-readiness-engine-") as directory:
            engine = Path(directory) / "docker"
            engine.touch()
            with patch.object(
                READINESS.subprocess, "run", return_value=blocked
            ) as run, patch.object(READINESS.time, "sleep") as sleep:
                result = READINESS.rootless_preflight(engine)

        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reason"], "ROOTLESS_CONTAINER_ENGINE_REQUIRED")
        self.assertEqual(result["attempts"], 1)
        run.assert_called_once()
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
