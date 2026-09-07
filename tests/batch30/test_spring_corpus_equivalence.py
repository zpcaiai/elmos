from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from scripts.batch30.evaluate_spring_corpus_equivalence import (
    MANIFEST_SCHEMA_VERSION,
    PROJECT_EVIDENCE_SCHEMA_VERSION,
    RESULT_SCHEMA_VERSION,
    CorpusEquivalenceError,
    canonical_digest,
    evaluate_manifest,
)
from tests.batch30 import test_external_certification_intake as signed_fixture


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "batch30" / "evaluate_spring_corpus_equivalence.py"
SCHEMAS = ROOT / "schemas" / "batch30"


class SpringCorpusEquivalenceTests(unittest.TestCase):
    """The positive aggregate fixture is a full fourteen-role Ed25519 intake.

    These signatures are test-only cryptographic fixtures. They prove the evaluator's
    fail-closed trust wiring, not customer acceptance or repository certification.
    """

    @classmethod
    def setUpClass(cls) -> None:
        signed_fixture.ExternalCertificationIntakeTests.setUpClass()

    @classmethod
    def tearDownClass(cls) -> None:
        signed_fixture.ExternalCertificationIntakeTests.tearDownClass()

    def setUp(self) -> None:
        self.external = signed_fixture.ExternalCertificationIntakeTests(
            "test_valid_intake_is_review_ready_but_never_certifies_or_mutates_pack"
        )
        self.external.setUp()
        self.evidence_root = self.external.evidence_root
        self.pack = self.external.case / "corpus-framework-pack"
        shutil.copytree(self.external.pack, self.pack)
        self.corpus_roots = {
            role: f"corpora/{role}"
            for role in ("development", "holdout", "representative", "customer")
        }
        for relative in self.corpus_roots.values():
            (self.evidence_root / relative).mkdir(parents=True)
        self.exact_tuple = self._exact_tuple_from_external_binding()
        self.tuple_sha256 = canonical_digest(self.exact_tuple)
        self.manifest: dict[str, object] = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "evaluation_id": "spring-signed-corpus-evaluation-one",
            "tuple": self.exact_tuple,
            "tuple_sha256": self.tuple_sha256,
            "corpus_roots": self.corpus_roots,
            "external_intake": {"status": "NOT_RUN", "content": None},
            "projects": [],
        }
        self.outcome_paths: dict[str, Path] = {}
        self.intake_path = self.evidence_root / "signed-external-intake.json"

    def tearDown(self) -> None:
        self.external.tearDown()

    @staticmethod
    def _component(name: str, version: str) -> dict[str, str]:
        return {"name": name, "version": version}

    @staticmethod
    def _build_component(value: str) -> dict[str, str]:
        name, separator, version = value.partition("-")
        if not separator:
            raise AssertionError(f"test binding build tool is not versioned: {value}")
        return {"name": name, "version": version}

    def _side(self, value: dict[str, object]) -> dict[str, object]:
        provider_versions = value["provider_versions"]
        return {
            "framework": self._component(value["framework"], value["framework_version"]),
            "runtime": self._component(value["runtime"], value["runtime_version"]),
            "build_tool": self._build_component(value["build_tool"]),
            "providers": [
                self._component(name, version)
                for name, version in sorted(provider_versions.items())
            ],
        }

    def _exact_tuple_from_external_binding(self) -> dict[str, object]:
        binding = self.external.binding
        recipe_manifest = json.loads(
            (self.pack / "recipes" / "manifest.json").read_text(encoding="utf-8")
        )
        return {
            "route_id": binding["pack_key"],
            "pack": {
                "id": binding["pack_key"],
                "version": binding["pack_version"],
                "sha256": binding["pack_manifest_digest"],
            },
            "recipe": {
                "id": recipe_manifest["recipes"][0],
                "version": binding["pack_version"],
                "sha256": binding["recipe_manifest_digest"],
            },
            "source": self._side(binding["source_tuple"]),
            "target": self._side(binding["target_tuple"]),
        }

    def _write(self, relative: str, raw: bytes) -> Path:
        path = self.evidence_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return path

    def _write_json(self, relative: str, value: object) -> Path:
        return self._write(
            relative,
            (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )

    def _content_reference(self, path: Path, media_type: str) -> dict[str, object]:
        raw = path.read_bytes()
        return {
            "path": path.relative_to(self.evidence_root).as_posix(),
            "sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
            "media_type": media_type,
        }

    def _external_bindings(self, role: str) -> dict[str, object] | None:
        if role == "development":
            return None
        evidence = self.external.intake["evidence"]
        supporting = {}
        supporting["independent_review"] = evidence["independent_review"]["content"]["digest"]
        if role == "customer":
            supporting["customer_acceptance"] = evidence["customer_acceptance"]["content"]["digest"]
        return {
            "artifact_digest": self.external.binding["artifact_digest"],
            "execution_profile_digest": self.external.binding["execution_profile_digest"],
            "runnable_evidence_digests": {
                name: evidence[name]["content"]["digest"]
                for name in ("source_build", "target_build", "source_startup", "target_startup")
            },
            "supporting_evidence_digests": supporting,
        }

    def _add_project(
        self,
        project_id: str,
        role: str,
        outcome: str = "EQUIVALENT",
        *,
        scope: str = "WHOLE_REPOSITORY",
    ) -> dict[str, object]:
        project_relative = f"{self.corpus_roots[role]}/{project_id}"
        (self.evidence_root / project_relative).mkdir(parents=True)
        source = self._write(
            f"{project_relative}/source-repository.snapshot",
            (f"fixed source repository snapshot for {project_id}\n" * 8).encode(),
        )
        target = self._write(
            f"{project_relative}/target-repository.snapshot",
            (f"fixed target repository snapshot for {project_id}\n" * 8).encode(),
        )
        checks = {
            "source_build": "PASS",
            "target_build": "PASS",
            "source_startup": "PASS",
            "target_startup": "PASS",
            "behavior_oracle": "PASS",
            "test_integrity": "PASS",
        }
        regression_count = 0
        unknowns: list[str] = []
        if outcome == "NOT_EQUIVALENT":
            checks["behavior_oracle"] = "FAIL"
            regression_count = 1
        elif outcome == "INCONCLUSIVE":
            checks["behavior_oracle"] = "INCONCLUSIVE"
            unknowns = ["unresolved provider side effect"]
        source_ref = self._content_reference(source, "application/octet-stream")
        target_ref = self._content_reference(target, "application/octet-stream")
        outcome_path = self._write_json(
            f"{project_relative}/outcome.json",
            {
                "schema_version": PROJECT_EVIDENCE_SCHEMA_VERSION,
                "project_id": project_id,
                "tuple_sha256": self.tuple_sha256,
                "corpus_role": role,
                "evaluation_scope": scope,
                "outcome": outcome,
                "source_snapshot_digest": source_ref["sha256"],
                "source_snapshot_size_bytes": source_ref["size_bytes"],
                "target_snapshot_digest": target_ref["sha256"],
                "target_snapshot_size_bytes": target_ref["size_bytes"],
                "external_bindings": self._external_bindings(role),
                "checks": checks,
                "observation_count": 22,
                "regression_count": regression_count,
                "unknowns": unknowns,
            },
        )
        project: dict[str, object] = {
            "project_id": project_id,
            "corpus_role": role,
            "corpus_path": project_relative,
            "tuple_sha256": self.tuple_sha256,
            "evaluation_scope": scope,
            "artifacts": {
                "source_snapshot": source_ref,
                "target_snapshot": target_ref,
                "outcome_evidence": self._content_reference(outcome_path, "application/json"),
            },
        }
        self.manifest["projects"].append(project)
        if role != "development":
            if role in self.outcome_paths:
                raise AssertionError("signed test fixture supports exactly one project per role")
            self.outcome_paths[role] = outcome_path
        return project

    def _rewrite_intake_reference(self) -> None:
        self.external.write_json(self.intake_path, self.external.intake)
        self.manifest["external_intake"] = {
            "status": "SUBMITTED",
            "content": self._content_reference(self.intake_path, "application/json"),
        }

    def _seal_signed_external_intake(self) -> None:
        project_digests = {}
        raw_evidence = []
        for role in ("holdout", "representative", "customer"):
            outcome_path = self.outcome_paths.get(role)
            if outcome_path is None:
                outcome_path = self._write_json(
                    f"corpora/{role}/not-selected.json",
                    {"corpus_role": role, "status": "NOT_RUN"},
                )
            reference = self.external.content_ref(outcome_path)
            project_digests[role] = reference["digest"]
            raw_evidence.append(reference)
        behavior_path = self._write_json(
            "behavioral-equivalence-signed-content.json",
            {
                "schema_version": "elmos.batch30.external-evidence.v1",
                "evidence_type": "behavioral_equivalence",
                "campaign_digest": "sha256:" + "c" * 64,
                "binding_digest": self.external.binding_digest,
                "metrics": {"project_outcome_evidence_digests": project_digests},
                "raw_evidence": raw_evidence,
            },
        )
        behavior_reference = self.external.content_ref(behavior_path)
        behavior = self.external.intake["evidence"]["behavioral_equivalence"]
        behavior["content"] = behavior_reference
        behavior_payload = behavior["attestation"]["payload"]
        behavior_payload["content_digest"] = behavior_reference["digest"]
        behavior_payload["content_size_bytes"] = behavior_reference["size_bytes"]
        authorization = self.external.intake["customer_authorization"]["payload"]
        authorization["scope"]["evidence_content_digests"] = {
            evidence_type: item["content"]["digest"]
            for evidence_type, item in self.external.intake["evidence"].items()
        }
        self.external.resign_authorization_chain()
        self._rewrite_intake_reference()

    def _evaluate(self, *, include_trust_inputs: bool = True) -> dict[str, object]:
        kwargs = {}
        if include_trust_inputs:
            kwargs = {"pack_dir": self.pack, "trust_store": self.external.trust_path}
        return evaluate_manifest(
            self.manifest,
            self.evidence_root,
            now=signed_fixture.NOW,
            **kwargs,
        )

    def _validate_json_schema(self, filename: str, instance: object) -> None:
        try:
            from jsonschema import Draft202012Validator
        except ModuleNotFoundError:
            self.skipTest("jsonschema is required for executable schema validation")
        schema = json.loads((SCHEMAS / filename).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(instance)

    def _project_evidence(self, project: dict[str, object]) -> dict[str, object]:
        artifacts = project["artifacts"]
        path = self.evidence_root / artifacts["outcome_evidence"]["path"]
        return json.loads(path.read_text(encoding="utf-8"))

    def test_unsigned_local_project_claims_cannot_create_an_overall_rate(self) -> None:
        self._add_project("unsigned-holdout", "holdout")
        self._add_project("unsigned-representative", "representative")
        self._add_project("unsigned-customer", "customer")
        result = self._evaluate()
        self.assertEqual(result["external_intake_verification"]["status"], "NOT_RUN")
        self.assertEqual(result["overall_equivalence"]["status"], "NOT_EVALUATED")
        self.assertIsNone(result["overall_equivalence"]["denominator_eligible_projects"])
        self.assertTrue(all(not item["aggregate_eligible"] for item in result["projects"]))

    def test_exact_development_fixture_never_implies_an_overall_rate(self) -> None:
        self._add_project(
            "mvc-exact-fixture",
            "development",
            scope="EXACT_FIXTURE",
        )
        result = self._evaluate()
        project = result["projects"][0]
        self.assertTrue(project["evidence_eligible"])
        self.assertFalse(project["aggregate_eligible"])
        self.assertEqual(project["signed_evidence_status"], "NOT_APPLICABLE")
        self.assertEqual(result["overall_equivalence"]["status"], "NOT_EVALUATED")
        self.assertEqual(
            result["universal_legacy_spring_equivalence"]["status"], "NOT_EVALUATED"
        )

    def test_full_signed_external_bundle_enables_only_the_observed_corpus_rate(self) -> None:
        self._add_project("signed-holdout", "holdout")
        self._add_project("signed-representative", "representative")
        self._add_project("signed-customer", "customer")
        self._seal_signed_external_intake()
        result = self._evaluate()
        overall = result["overall_equivalence"]
        self.assertEqual(result["external_intake_verification"]["status"], "VERIFIED")
        self.assertEqual(overall["status"], "EVALUATED")
        self.assertEqual(overall["numerator_equivalent_projects"], 3)
        self.assertEqual(overall["denominator_eligible_projects"], 3)
        self.assertEqual(overall["percentage"], 100.0)
        self.assertTrue(all(item["aggregate_eligible"] for item in result["projects"]))
        self.assertEqual(
            result["universal_legacy_spring_equivalence"]["status"], "NOT_EVALUATED"
        )
        self.assertEqual(result["certification"]["decision"], "NOT_CERTIFYING")

    def test_complete_signed_intake_without_every_project_role_has_no_denominator(self) -> None:
        self._add_project("signed-holdout-only", "holdout")
        self._add_project("signed-representative-only", "representative")
        self._seal_signed_external_intake()
        result = self._evaluate()
        overall = result["overall_equivalence"]
        self.assertEqual(result["external_intake_verification"]["status"], "VERIFIED")
        self.assertEqual(overall["status"], "NOT_EVALUATED")
        self.assertEqual(overall["missing_roles"], ["customer"])
        self.assertIsNone(overall["numerator_equivalent_projects"])
        self.assertIsNone(overall["denominator_eligible_projects"])
        self.assertIsNone(overall["percentage"])

    def test_signed_behavior_for_a_different_checked_in_campaign_is_not_evaluated(self) -> None:
        self._add_project("campaign-holdout", "holdout")
        self._add_project("campaign-representative", "representative")
        self._add_project("campaign-customer", "customer")
        self._seal_signed_external_intake()
        campaign = self.pack / "certification" / "p0-p11-campaign.json"
        campaign.parent.mkdir(parents=True, exist_ok=True)
        campaign.write_text('{"campaign_id":"different-campaign"}\n', encoding="utf-8")
        result = self._evaluate()
        self.assertEqual(result["external_intake_verification"]["status"], "INVALID")
        self.assertIn(
            "different campaign",
            result["external_intake_verification"]["reason"],
        )
        self.assertEqual(result["overall_equivalence"]["status"], "NOT_EVALUATED")

    def test_signed_customer_outcome_must_bind_customer_acceptance(self) -> None:
        self._add_project("acceptance-holdout", "holdout")
        self._add_project("acceptance-representative", "representative")
        customer_project = self._add_project("acceptance-customer", "customer")
        customer_path = self.outcome_paths["customer"]
        customer_evidence = json.loads(customer_path.read_text(encoding="utf-8"))
        customer_evidence["external_bindings"]["supporting_evidence_digests"][
            "customer_acceptance"
        ] = "sha256:" + "0" * 64
        self.external.write_json(customer_path, customer_evidence)
        customer_project["artifacts"]["outcome_evidence"] = self._content_reference(
            customer_path,
            "application/json",
        )
        self._seal_signed_external_intake()
        result = self._evaluate()
        customer = next(
            item for item in result["projects"] if item["corpus_role"] == "customer"
        )
        self.assertEqual(result["external_intake_verification"]["status"], "VERIFIED")
        self.assertFalse(customer["aggregate_eligible"])
        self.assertIn(
            "SUPPORTING_EVIDENCE_DIGESTS_NOT_BOUND",
            customer["aggregate_exclusion_reasons"],
        )
        self.assertEqual(result["overall_equivalence"]["status"], "NOT_EVALUATED")

    def test_multiple_projects_cannot_reuse_one_signed_role(self) -> None:
        self._add_project("single-signed-holdout", "holdout")
        self._add_project("single-signed-representative", "representative")
        self._add_project("single-signed-customer", "customer")
        self._seal_signed_external_intake()
        self.outcome_paths.pop("holdout")
        self._add_project("unsigned-second-holdout", "holdout")
        result = self._evaluate()
        holdout_projects = [
            item for item in result["projects"] if item["corpus_role"] == "holdout"
        ]
        self.assertEqual(result["external_intake_verification"]["status"], "VERIFIED")
        self.assertEqual(len(holdout_projects), 2)
        self.assertTrue(all(not item["aggregate_eligible"] for item in holdout_projects))
        self.assertTrue(
            all(
                "MULTIPLE_PROJECTS_PER_SIGNED_ROLE_UNSUPPORTED"
                in item["aggregate_exclusion_reasons"]
                for item in holdout_projects
            )
        )
        self.assertEqual(result["overall_equivalence"]["status"], "NOT_EVALUATED")

    def test_draft_2020_12_schemas_validate_a_signed_observed_result(self) -> None:
        for role in ("holdout", "representative", "customer"):
            self._add_project(f"schema-signed-{role}", role)
        self._seal_signed_external_intake()
        result = self._evaluate()
        self.assertEqual(result["overall_equivalence"]["status"], "EVALUATED")
        self._validate_json_schema(
            "spring-corpus-equivalence-manifest.schema.json",
            self.manifest,
        )
        for project in self.manifest["projects"]:
            self._validate_json_schema(
                "spring-project-equivalence-evidence.schema.json",
                self._project_evidence(project),
            )
        self._validate_json_schema(
            "spring-corpus-equivalence-result.schema.json",
            result,
        )

    def test_draft_2020_12_schemas_validate_a_not_evaluated_result(self) -> None:
        project = self._add_project(
            "schema-exact-development-fixture",
            "development",
            scope="EXACT_FIXTURE",
        )
        result = self._evaluate()
        self.assertEqual(result["overall_equivalence"]["status"], "NOT_EVALUATED")
        self._validate_json_schema(
            "spring-corpus-equivalence-manifest.schema.json",
            self.manifest,
        )
        self._validate_json_schema(
            "spring-project-equivalence-evidence.schema.json",
            self._project_evidence(project),
        )
        self._validate_json_schema(
            "spring-corpus-equivalence-result.schema.json",
            result,
        )

    def test_submitted_intake_without_explicit_pack_and_trust_is_not_evaluated(self) -> None:
        self._add_project("signed-holdout", "holdout")
        self._seal_signed_external_intake()
        result = self._evaluate(include_trust_inputs=False)
        self.assertEqual(result["external_intake_verification"]["status"], "NOT_EVALUATED")
        self.assertEqual(result["overall_equivalence"]["status"], "NOT_EVALUATED")

    def test_revoked_signed_authorization_is_not_evaluated(self) -> None:
        for role in ("holdout", "representative", "customer"):
            self._add_project(f"revoked-{role}", role)
        self._seal_signed_external_intake()
        self.external.revoked_record_ids.append("customer-authorization-one")
        self.external.write_trust()
        result = self._evaluate()
        self.assertEqual(result["external_intake_verification"]["status"], "INVALID")
        self.assertIn("revoked", result["external_intake_verification"]["reason"])
        self.assertEqual(result["overall_equivalence"]["status"], "NOT_EVALUATED")

    def test_expired_signed_authorization_is_not_evaluated(self) -> None:
        for role in ("holdout", "representative", "customer"):
            self._add_project(f"expired-{role}", role)
        self._seal_signed_external_intake()
        payload = self.external.intake["customer_authorization"]["payload"]
        payload["issued_at"] = "2024-01-01T00:00:00Z"
        payload["expires_at"] = "2025-01-01T00:00:00Z"
        self.external.intake["customer_authorization"] = self.external.sign(
            signed_fixture.CUSTOMER_AUTHORIZATION_ROLE,
            payload,
        )
        self._rewrite_intake_reference()
        result = self._evaluate()
        self.assertEqual(result["external_intake_verification"]["status"], "INVALID")
        self.assertIn("validity window", result["external_intake_verification"]["reason"])
        self.assertEqual(result["overall_equivalence"]["status"], "NOT_EVALUATED")

    def test_executor_and_independent_verifier_organization_reuse_is_not_evaluated(self) -> None:
        for role in ("holdout", "representative", "customer"):
            self._add_project(f"org-reuse-{role}", role)
        self._seal_signed_external_intake()
        self.external.intake["evidence_executors"]["independent_review"][
            "organization_id"
        ] = self.external.organizations["independent_organization_id"]
        self.external.resign_authorization_chain()
        self._rewrite_intake_reference()
        result = self._evaluate()
        self.assertEqual(result["external_intake_verification"]["status"], "INVALID")
        self.assertIn("organization", result["external_intake_verification"]["reason"])
        self.assertEqual(result["overall_equivalence"]["status"], "NOT_EVALUATED")

    def test_tampered_signed_project_outcome_is_not_evaluated(self) -> None:
        for role in ("holdout", "representative", "customer"):
            self._add_project(f"tampered-{role}", role)
        self._seal_signed_external_intake()
        self.outcome_paths["representative"].write_bytes(b"tampered after Ed25519 signing\n")
        result = self._evaluate()
        self.assertEqual(result["external_intake_verification"]["status"], "VERIFIED")
        representative = next(
            item for item in result["projects"] if item["corpus_role"] == "representative"
        )
        self.assertFalse(representative["aggregate_eligible"])
        self.assertIn(
            "OUTCOME_EVIDENCE_CONTENT_INVALID",
            representative["aggregate_exclusion_reasons"],
        )
        self.assertEqual(result["overall_equivalence"]["status"], "NOT_EVALUATED")

    def test_tampered_actual_recipe_manifest_is_not_evaluated(self) -> None:
        for role in ("holdout", "representative", "customer"):
            self._add_project(f"recipe-tamper-{role}", role)
        self._seal_signed_external_intake()
        recipe = self.pack / "recipes" / "manifest.json"
        recipe.write_text('{"pack_key":"tampered","recipes":[]}\n', encoding="utf-8")
        result = self._evaluate()
        self.assertEqual(result["external_intake_verification"]["status"], "INVALID")
        self.assertIn("pack_key", result["external_intake_verification"]["reason"])
        self.assertEqual(result["overall_equivalence"]["status"], "NOT_EVALUATED")

    def test_tampered_independent_signature_is_not_evaluated(self) -> None:
        for role in ("holdout", "representative", "customer"):
            self._add_project(f"signature-tamper-{role}", role)
        self._seal_signed_external_intake()
        self.external.intake["evidence"]["independent_review"]["attestation"][
            "signature"
        ] = "ZmFrZQ=="
        self._rewrite_intake_reference()
        result = self._evaluate()
        self.assertEqual(result["external_intake_verification"]["status"], "INVALID")
        self.assertIn("signature", result["external_intake_verification"]["reason"])
        self.assertEqual(result["overall_equivalence"]["status"], "NOT_EVALUATED")

    def test_mutable_tuple_version_is_rejected(self) -> None:
        self.manifest["tuple"]["target"]["framework"]["version"] = "latest"
        self.manifest["tuple_sha256"] = canonical_digest(self.manifest["tuple"])
        with self.assertRaisesRegex(CorpusEquivalenceError, "exact immutable version"):
            self._evaluate()

    def test_cli_emits_typed_not_evaluated_without_an_external_intake(self) -> None:
        self._add_project(
            "mvc-exact-fixture",
            "development",
            scope="EXACT_FIXTURE",
        )
        manifest_path = self._write_json("manifest.json", self.manifest)
        result_path = self.external.case / "corpus-result.json"
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(manifest_path),
                "--evidence-root",
                str(self.evidence_root),
                "--output",
                str(result_path),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        result = json.loads(result_path.read_text(encoding="utf-8"))
        self.assertEqual(result["schema_version"], RESULT_SCHEMA_VERSION)
        self.assertEqual(result["external_intake_verification"]["status"], "NOT_RUN")
        self.assertEqual(result["overall_equivalence"]["status"], "NOT_EVALUATED")

        expected = {
            "spring-corpus-equivalence-manifest.schema.json": MANIFEST_SCHEMA_VERSION,
            "spring-project-equivalence-evidence.schema.json": PROJECT_EVIDENCE_SCHEMA_VERSION,
            "spring-corpus-equivalence-result.schema.json": RESULT_SCHEMA_VERSION,
        }
        for filename, version in expected.items():
            schema = json.loads((SCHEMAS / filename).read_text(encoding="utf-8"))
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertEqual(schema["properties"]["schema_version"]["const"], version)


if __name__ == "__main__":
    unittest.main()
