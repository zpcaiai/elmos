from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/operations/validate_spring_verification_plan.py"
SPEC = importlib.util.spec_from_file_location("spring_verification_plan", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class SpringVerificationPlanTests(unittest.TestCase):
    SOURCE_PACK = ROOT / "framework-packs/spring-to-boot-4-1-1"

    def _copy_pack(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory(prefix="spring-verification-plan-")
        pack = Path(temporary.name) / self.SOURCE_PACK.name
        shutil.copytree(self.SOURCE_PACK, pack)
        return temporary, pack

    @staticmethod
    def _load(pack: Path, relative: str) -> dict[str, object]:
        return json.loads((pack / relative).read_text(encoding="utf-8"))

    @staticmethod
    def _write(pack: Path, relative: str, value: dict[str, object]) -> None:
        (pack / relative).write_text(
            json.dumps(value, indent=2) + "\n", encoding="utf-8"
        )

    def test_current_plan_is_complete_and_not_run(self) -> None:
        self.assertEqual(VALIDATOR.validate(self.SOURCE_PACK), [])

    def test_track_contract_is_complete_and_not_run(self) -> None:
        contract = self._load(self.SOURCE_PACK, "verification/track-contract.json")
        self.assertEqual(contract["status"], "PREPARED_NOT_RUN")
        tracks = contract["tracks"]
        self.assertEqual(
            [track["id"] for track in tracks], list(VALIDATOR.TRACK_IDS)
        )
        self.assertTrue(all(track["status"] == "NOT_RUN" for track in tracks))
        self.assertTrue(
            all(track["authorization_status"] == "NOT_RUN" for track in tracks)
        )
        self.assertTrue(
            all(track["independent_verifier_status"] == "NOT_RUN" for track in tracks)
        )

    def test_plan_exposes_all_provider_domains_as_not_run(self) -> None:
        plan = self._load(self.SOURCE_PACK, "verification/validation-plan.json")
        domains = plan["provider_domains"]
        self.assertEqual(
            [domain["id"] for domain in domains],
            ["security", "database", "transaction", "messaging", "provider"],
        )
        self.assertTrue(all(domain["status"] == "NOT_RUN" for domain in domains))

    def test_provider_domain_evidence_cannot_advance(self) -> None:
        temporary, pack = self._copy_pack()
        try:
            evidence = self._load(pack, "certification/evidence.json")
            evidence["provider_domains"]["security"] = "PASSED"
            self._write(pack, "certification/evidence.json", evidence)
            errors = VALIDATOR.validate(pack)
            self.assertIn(
                "certification evidence provider domain statuses must remain NOT_RUN",
                errors,
            )
        finally:
            temporary.cleanup()

    def test_placeholder_replay_protocol_is_rejected(self) -> None:
        temporary, pack = self._copy_pack()
        try:
            contract = self._load(pack, "verification/track-contract.json")
            tracks = contract["tracks"]
            assert isinstance(tracks, list)
            tracks[0]["protocol"] = "<unbound-runner> --source-build"
            self._write(pack, "verification/track-contract.json", contract)
            errors = VALIDATOR.validate(pack)
            self.assertTrue(
                any("track contract contains a placeholder" in error for error in errors),
                errors,
            )
        finally:
            temporary.cleanup()

    def test_provider_domains_cover_security_data_transaction_messaging(self) -> None:
        temporary, pack = self._copy_pack()
        try:
            contract = self._load(pack, "verification/track-contract.json")
            domains = contract["provider_domains"]
            assert isinstance(domains, list)
            domains[1]["feature_ids"].remove("data-jpa")
            self._write(pack, "verification/track-contract.json", contract)
            errors = VALIDATOR.validate(pack)
            self.assertIn("provider domain database feature_ids drift", errors)
            self.assertIn("provider domains must exactly cover provider feature set", errors)
        finally:
            temporary.cleanup()

    def test_track_contract_cannot_promote_runtime_status(self) -> None:
        temporary, pack = self._copy_pack()
        try:
            contract = self._load(pack, "verification/track-contract.json")
            tracks = contract["tracks"]
            assert isinstance(tracks, list)
            tracks[0]["status"] = "PASSED"
            self._write(pack, "verification/track-contract.json", contract)
            errors = VALIDATOR.validate(pack)
            self.assertTrue(
                any(
                    "track contract source-build status must remain NOT_RUN" in error
                    for error in errors
                ),
                errors,
            )
        finally:
            temporary.cleanup()

    def test_provider_domains_cannot_overlap(self) -> None:
        temporary, pack = self._copy_pack()
        try:
            contract = self._load(pack, "verification/track-contract.json")
            domains = contract["provider_domains"]
            assert isinstance(domains, list)
            domains[1]["feature_ids"].append("security-web")
            self._write(pack, "verification/track-contract.json", contract)
            errors = VALIDATOR.validate(pack)
            self.assertIn("provider domain database feature_ids drift", errors)
            self.assertIn("provider domain feature coverage must be duplicate-free", errors)
        finally:
            temporary.cleanup()

    def test_track_status_cannot_be_manually_promoted(self) -> None:
        temporary, pack = self._copy_pack()
        try:
            plan = self._load(pack, "verification/validation-plan.json")
            tracks = plan["tracks"]
            assert isinstance(tracks, list)
            tracks[0]["status"] = "PASSED"
            self._write(pack, "verification/validation-plan.json", plan)
            errors = VALIDATOR.validate(pack)
            self.assertTrue(
                any("source-build status must remain NOT_RUN" in error for error in errors),
                errors,
            )
        finally:
            temporary.cleanup()

    def test_corpus_binding_cannot_overlap_or_drift(self) -> None:
        temporary, pack = self._copy_pack()
        try:
            plan = self._load(pack, "verification/validation-plan.json")
            corpora = plan["corpora"]
            assert isinstance(corpora, dict)
            corpora["holdout"]["path"] = "corpus/development"
            self._write(pack, "verification/validation-plan.json", plan)
            errors = VALIDATOR.validate(pack)
            self.assertIn("verification corpus path drift: holdout", errors)
        finally:
            temporary.cleanup()

    def test_provider_features_cannot_fall_back_to_static_mapping(self) -> None:
        temporary, pack = self._copy_pack()
        try:
            plan = self._load(pack, "verification/validation-plan.json")
            provider_features = plan["feature_verification"]["provider_behavior"]
            assert isinstance(provider_features, list)
            provider_features.remove("security-web")
            plan["feature_verification"]["static_conversion"].append("security-web")
            self._write(pack, "verification/validation-plan.json", plan)
            errors = VALIDATOR.validate(pack)
            self.assertIn(
                "security/data/transaction/messaging/provider features must use provider_behavior",
                errors,
            )
        finally:
            temporary.cleanup()

    def test_certification_evidence_cannot_advance_with_the_plan(self) -> None:
        temporary, pack = self._copy_pack()
        try:
            evidence = self._load(pack, "certification/evidence.json")
            evidence["provider_behavior"] = "PASSED"
            self._write(pack, "certification/evidence.json", evidence)
            errors = VALIDATOR.validate(pack)
            self.assertIn(
                "certification evidence provider_behavior must remain NOT_RUN", errors
            )
        finally:
            temporary.cleanup()


if __name__ == "__main__":
    unittest.main()
