from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from elmos_software_factory.archive_contracts import (
    ArchiveContractError,
    SCRIPT_CONTRACTS,
    _json_bytes,
    _schema_meta,
    _validate_root_manifest,
    _yaml_subset,
    inspect_archive_contracts,
)
from elmos_software_factory.artifact_binding import (
    ArtifactBindingError,
    ContentReference,
)
from elmos_software_factory.campaigns import (
    _RUNTIME_SOURCE_FILES,
    _RUNTIME_SOURCE_PREFIX,
    campaign_corpus_digest,
    replay_campaign,
    run_campaign,
)
from elmos_software_factory.canonical import canonical_digest
from elmos_software_factory.evidence_intake import (
    evaluate_external_preflight,
    ingest_external_receipt,
)
from elmos_software_factory.evidence_models import CampaignReceipt, EvidenceContractError


SHA = "sha256:" + "a" * 64
ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "skills" / "elmos-7plus1-commercial-skills-v1.0.0"


class EvidenceCampaignTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="elmos-evidence-campaign-")
        self.addCleanup(temporary.cleanup)
        self.evidence_root = Path(temporary.name)

    def _write_json(self, name: str, value: object) -> dict[str, object]:
        raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
        (self.evidence_root / name).write_bytes(raw)
        return {
            "path": name,
            "sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
            "media_type": "application/json",
        }

    def _bind(self, manifest: dict[str, object]) -> dict[str, object]:
        corpus_digest = campaign_corpus_digest(manifest)
        manifest["corpus_digest"] = corpus_digest
        prefix = str(manifest["campaign_type"])
        target_rows: list[dict[str, object]] = []
        for name in _RUNTIME_SOURCE_FILES:
            relative = f"{_RUNTIME_SOURCE_PREFIX}/{name}"
            raw = (ROOT / relative).read_bytes()
            destination = self.evidence_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
            target_rows.append(
                {
                    "path": relative,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "size_bytes": len(raw),
                }
            )
        generated: dict[str, dict[str, str]] = {}
        for label in ("compiled_manifest", "installed_manifest"):
            relative = f"docs/{prefix}-{label.replace('_', '-')}.json"
            raw = (json.dumps({"kind": label, "campaign_type": prefix}, sort_keys=True) + "\n").encode()
            destination = self.evidence_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
            raw_digest = hashlib.sha256(raw).hexdigest()
            generated[label] = {"path": relative, "sha256": raw_digest}
            target_rows.append(
                {"path": relative, "sha256": raw_digest, "size_bytes": len(raw)}
            )
        target_rows.sort(key=lambda item: str(item["path"]))
        aggregate_lines = "".join(
            f"{item['sha256']}\t{item['size_bytes']}\t{item['path']}\n" for item in target_rows
        )
        aggregate = hashlib.sha256(aggregate_lines.encode()).hexdigest()
        target = self._write_json(
            f"{prefix}-target.json",
            {
                "schema_version": 1,
                "artifact_set": f"{prefix}-target-v1",
                "aggregate_algorithm": (
                    "SHA-256 over UTF-8 lines "
                    "'<sha256>\\t<size_bytes>\\t<repository_relative_path>\\n' "
                    "in LC_ALL=C path order"
                ),
                "aggregate_sha256": aggregate,
                "file_count": len(target_rows),
                "total_size_bytes": sum(int(item["size_bytes"]) for item in target_rows),
                "scope": ["bounded unit-test artifact"],
                "generated_install_manifests": {
                    "status": "LOCAL_INSTALLED_AND_CHECKED_SELF_ATTESTED",
                    **generated,
                    "transitive_scope": ["bounded test install roots"],
                    "limitations": ["self-attested test fixture"],
                },
                "files": target_rows,
            },
        )
        scope = manifest["scope"]
        assert isinstance(scope, dict)
        environment = self._write_json(
            f"{prefix}-environment.json",
            {
                "schema_version": 1,
                "environment_key": f"{prefix}-environment-v1",
                "operating_system": "local-test",
                "python": "test-interpreter",
                "jsonschema": "test-version",
                "network_required": False,
                "production_access": False,
                "provider_access": False,
                "authorized_scope": "bounded local unit test",
                "scope": {
                    "tenant_id": scope["tenant_id"],
                    "project_id": scope["project_id"],
                    "policy_revision": scope["policy_revision"],
                    "source_revision": scope["source_revision"],
                },
                "local_test_commands": ["python -m unittest"],
                "limitations": ["self-attested test fixture"],
            },
        )
        development = None
        if prefix == "local-holdout":
            development = self._development_reference(manifest, self._development_cases(manifest))
        corpus = self._write_json(f"{prefix}-corpus.json", self._corpus_document(manifest))
        manifest["target_artifact_digest"] = "sha256:" + aggregate
        manifest["environment_digest"] = environment["sha256"]
        manifest["bindings"] = {
            "target_manifest": target,
            "environment_manifest": environment,
            "corpus_manifest": corpus,
        }
        if development is not None:
            manifest["bindings"]["development_manifest"] = development
        return manifest

    @staticmethod
    def _development_cases(manifest: dict[str, object]) -> list[dict[str, object]]:
        cases = manifest["cases"]
        assert isinstance(cases, list)
        development: list[dict[str, object]] = []
        for index, value in enumerate(cases, 1):
            case = copy.deepcopy(value)
            assert isinstance(case, dict)
            case["case_id"] = f"development-{index:03d}"
            request = case["request"]
            assert isinstance(request, dict)
            request["idempotency_key"] = f"development-{index:03d}"
            development.append(case)
        return development

    def _development_reference(
        self,
        manifest: dict[str, object],
        cases: list[dict[str, object]],
    ) -> dict[str, object]:
        digests = [canonical_digest(case) for case in cases]
        manifest["development_case_digests"] = digests
        return self._write_json(
            "local-holdout-development.json",
            {
                "schema_version": 1,
                "corpus_key": "local-holdout-development-v1",
                "corpus_role": "LOCAL_SELF_AUTHORED_DEVELOPMENT_INPUT",
                "scope": copy.deepcopy(manifest["scope"]),
                "case_count": len(cases),
                "case_digests": digests,
                "cases": cases,
                "limitations": ["self-attested test development fixture"],
            },
        )

    def _replace_development_cases(
        self,
        manifest: dict[str, object],
        cases: list[dict[str, object]],
    ) -> None:
        bindings = manifest["bindings"]
        assert isinstance(bindings, dict)
        bindings["development_manifest"] = self._development_reference(manifest, cases)

    def _corpus_document(self, manifest: dict[str, object]) -> dict[str, object]:
        campaign_type = str(manifest["campaign_type"])
        scope = manifest["scope"]
        assert isinstance(scope, dict)
        common: dict[str, object] = {
            "schema_version": 1,
            "corpus_key": f"{campaign_type}-corpus-v1",
            "campaign_type": campaign_type,
            "campaign_ref": f"campaigns/{campaign_type}.json",
            "scope": copy.deepcopy(scope),
            "corpus_digest": manifest["corpus_digest"],
            "limitations": ["self-attested test fixture"],
        }
        if campaign_type == "local-holdout":
            cases = manifest["cases"]
            assert isinstance(cases, list)
            ids = [str(item["case_id"]) for item in cases]
            return {
                **common,
                "corpus_role": "IMMUTABLE_LOCAL_INPUT",
                "input_state": "LOCAL_SELF_AUTHORED_NOT_INDEPENDENT",
                "case_count": len(ids),
                "case_ids": ids,
                "separation": "digest-disjoint self-attested test cases",
                "independent": False,
                "external_holdout_state": "NOT_RUN",
            }
        if campaign_type == "provider-contract-simulation":
            fixtures = manifest["fixtures"]
            assert isinstance(fixtures, list)
            ids = [str(item["case_id"]) for item in fixtures]
            return {
                **common,
                "corpus_role": "IMMUTABLE_OFFLINE_FIXTURE_INPUT",
                "input_state": "LOCAL_SELF_AUTHORED_FIXTURE_ONLY",
                "case_count": len(ids),
                "case_ids": ids,
                "provider_execution_state": "NOT_RUN",
            }
        rehearsal = manifest["rehearsal"]
        assert isinstance(rehearsal, dict)
        events = rehearsal["events"]
        assert isinstance(events, list)
        ids = [str(item["case_id"]) for item in events]
        return {
            **common,
            "corpus_role": "IMMUTABLE_SYNTHETIC_INPUT",
            "input_state": "LOCAL_SELF_AUTHORED_SYNTHETIC_ONLY",
            "event_count": len(ids),
            "event_ids": ids,
            "production_derived": False,
            "production_execution_state": "NOT_RUN",
        }

    def _refresh_corpus(self, manifest: dict[str, object]) -> None:
        corpus_digest = campaign_corpus_digest(manifest)
        manifest["corpus_digest"] = corpus_digest
        manifest["bindings"]["corpus_manifest"] = self._write_json(
            f"{manifest['campaign_type']}-corpus.json", self._corpus_document(manifest)
        )

    def execute_campaign(self, manifest: object) -> CampaignReceipt:
        return run_campaign(manifest, evidence_root=self.evidence_root)

    def replay(self, manifest: object, receipt: object) -> dict[str, object]:
        return replay_campaign(manifest, receipt, evidence_root=self.evidence_root)

    @staticmethod
    def scope() -> dict[str, str]:
        return {
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "campaign_id": "campaign-a",
            "policy_revision": "policy-v1",
            "source_revision": "source-v1",
        }

    @staticmethod
    def controls() -> dict[str, object]:
        return {
            "network_allowed": False,
            "provider_calls_allowed": False,
            "max_production_writes": 0,
        }

    @staticmethod
    def request(
        action: str,
        payload: dict[str, object],
        skill_name: str = "elmos-software-factory-master",
    ) -> dict[str, object]:
        return {
            "contract_version": "1.0",
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "correlation_id": "campaign-a",
            "idempotency_key": "campaign-a-case",
            "policy_revision": "policy-v1",
            "source_revision": "source-v1",
            "payload": {**payload, "action": action},
            "policy": {
                "allowed_skills": [skill_name],
                "allowed_actions": [action],
                "allowed_permissions": ["read"],
                "allowed_sandbox_modes": ["read-only"],
                "allowed_providers": [],
                "allowed_data_classes": ["public"],
                "max_nodes": 64,
                "max_parallelism": 1,
                "max_retries": 0,
                "max_cost_micros": 0,
                "min_quality_basis_points": 0,
                "allow_global_knowledge": False,
            },
            "dependencies": [],
            "observations": [],
        }

    def holdout_manifest(self) -> dict[str, object]:
        cases = [
            {
                "case_id": "case-001-local",
                "skill_name": "elmos-architecture-invariant-linter",
                "request": self.request(
                    "compile-workflow",
                    {"nodes": [], "invariants": []},
                    "elmos-architecture-invariant-linter",
                ),
                "expected_status": "EXECUTED",
                "expected_error_code": None,
            },
            {
                "case_id": "case-002-adapter-boundary",
                "skill_name": "elmos-release-certification",
                "request": self.request(
                    "certify-release",
                    {"evidence_bundle": {}},
                    "elmos-release-certification",
                ),
                "expected_status": "REQUIRES_ADAPTER",
                "expected_error_code": "ADAPTER_REQUIRED",
            },
        ]
        manifest: dict[str, object] = {
            "schema_version": "1.0",
            "campaign_type": "local-holdout",
            "scope": self.scope(),
            "target_artifact_digest": SHA,
            "environment_digest": SHA,
            "corpus_digest": SHA,
            "executor_id": "repository-local-runner",
            "controls": self.controls(),
            "bindings": {},
            "development_case_digests": [canonical_digest({"development": "case-a"})],
            "cases": cases,
        }
        return self._bind(manifest)

    def provider_manifest(self) -> dict[str, object]:
        provider_request = {"input_digest": SHA, "mode": "fixture"}
        manifest: dict[str, object] = {
            "schema_version": "1.0",
            "campaign_type": "provider-contract-simulation",
            "scope": self.scope(),
            "target_artifact_digest": SHA,
            "environment_digest": SHA,
            "corpus_digest": SHA,
            "executor_id": "repository-local-runner",
            "controls": self.controls(),
            "bindings": {},
            "provider_contract": {
                "method": "ReleaseManager.certify",
                "provider_id": "fixture-provider",
                "operation": "certify-release",
                "response_fields": [
                    "provider_id",
                    "operation",
                    "request_digest",
                    "state",
                    "artifact_digest",
                    "error_code",
                ],
                "error_map": {"STALE": "EVIDENCE_STALE"},
            },
            "fixtures": [
                {
                    "case_id": "provider-001-success",
                    "runtime_request": self.request("certify-release", {"evidence_bundle": {}}),
                    "provider_request": provider_request,
                    "provider_response": {
                        "provider_id": "fixture-provider",
                        "operation": "certify-release",
                        "request_digest": canonical_digest(provider_request),
                        "state": "SUCCEEDED",
                        "artifact_digest": SHA,
                        "error_code": None,
                    },
                    "expected_provider_state": "SUCCEEDED",
                    "expected_mapped_error": None,
                }
            ],
        }
        return self._bind(manifest)

    def canary_manifest(self) -> dict[str, object]:
        manifest: dict[str, object] = {
            "schema_version": "1.0",
            "campaign_type": "production-like-rehearsal",
            "scope": self.scope(),
            "target_artifact_digest": SHA,
            "environment_digest": SHA,
            "corpus_digest": SHA,
            "executor_id": "repository-local-runner",
            "controls": self.controls(),
            "bindings": {},
            "rehearsal": {
                "mode": "LOCAL_REHEARSAL",
                "canary_population": 0,
                "initial_state": {"release": "v1", "enabled": False},
                "canary_state": {"release": "v2", "enabled": True},
                "rollback_state": {"release": "v1", "enabled": False},
                "events": [
                    {"case_id": "event-001", "outcome": "SUCCESS"},
                    {"case_id": "event-002", "outcome": "ERROR"},
                ],
                "abort_error_basis_points": 1000,
                "expected_control_decision": "ROLLBACK",
            },
        }
        return self._bind(manifest)

    def test_local_holdout_executes_and_replays_without_claiming_independence(self) -> None:
        manifest = self.holdout_manifest()
        receipt = self.execute_campaign(manifest)
        self.assertEqual("PASSED", receipt.status)
        self.assertEqual("LOCAL_HOLDOUT_EXECUTED_SELF_ATTESTED", receipt.evidence_state)
        self.assertEqual("NOT_RUN", receipt.external_states["independent_holdout"])
        self.assertFalse(receipt.external_states["archive_scripts_executed"])
        parsed = CampaignReceipt.from_mapping(receipt.as_dict())
        self.assertEqual(receipt.receipt_digest, parsed.receipt_digest)
        self.assertEqual("MATCHED", self.replay(manifest, receipt.as_dict())["status"])

    def test_local_holdout_rejects_overlap_and_manifest_drift(self) -> None:
        manifest = self.holdout_manifest()
        self._replace_development_cases(manifest, [copy.deepcopy(manifest["cases"][0])])
        receipt = self.execute_campaign(manifest)
        self.assertEqual("BLOCKED", receipt.status)
        clean = self.holdout_manifest()
        original = self.execute_campaign(clean).as_dict()
        clean["executor_id"] = "different-executor"
        decision = self.replay(clean, original)
        self.assertEqual("BLOCKED", decision["status"])
        self.assertEqual("MANIFEST_DIGEST_MISMATCH", decision["reason"])

    def test_cases_must_be_unique_and_sorted(self) -> None:
        manifest = self.holdout_manifest()
        manifest["cases"] = list(reversed(manifest["cases"]))
        self._refresh_corpus(manifest)
        with self.assertRaisesRegex(EvidenceContractError, "sorted"):
            self.execute_campaign(manifest)
        duplicate = self.holdout_manifest()
        duplicate["cases"].append(dict(duplicate["cases"][0]))
        self._refresh_corpus(duplicate)
        with self.assertRaisesRegex(EvidenceContractError, "duplicate"):
            self.execute_campaign(duplicate)

    def test_provider_fixture_validates_contract_but_runtime_stays_adapter_bound(self) -> None:
        receipt = self.execute_campaign(self.provider_manifest())
        self.assertEqual("PASSED", receipt.status)
        self.assertEqual("LOCAL_PROVIDER_CONTRACT_SIMULATED_SELF_ATTESTED", receipt.evidence_state)
        case = receipt.case_results[0]
        self.assertEqual("REQUIRES_ADAPTER", case["bounded_runtime_state"])
        self.assertEqual("ADAPTER_REQUIRED", case["bounded_runtime_error"])
        self.assertFalse(case["provider_calls_executed"])
        self.assertEqual("NOT_RUN", receipt.external_states["provider_execution"])

    def test_provider_fixture_rejects_stale_request_digest_and_reordered_keys_are_stable(self) -> None:
        manifest = self.provider_manifest()
        response = manifest["fixtures"][0]["provider_response"]
        manifest["fixtures"][0]["provider_response"] = dict(reversed(list(response.items())))
        self._refresh_corpus(manifest)
        self.assertEqual("PASSED", self.execute_campaign(manifest).status)
        manifest["fixtures"][0]["provider_response"]["request_digest"] = SHA
        self._refresh_corpus(manifest)
        with self.assertRaisesRegex(EvidenceContractError, "request digest"):
            self.execute_campaign(manifest)

    def test_canary_rehearsal_rolls_back_without_network_provider_or_writes(self) -> None:
        receipt = self.execute_campaign(self.canary_manifest())
        self.assertEqual("PASSED", receipt.status)
        case = receipt.case_results[0]
        self.assertEqual("ROLLBACK", case["control_decision"])
        self.assertTrue(case["rollback_complete"])
        self.assertFalse(case["network_calls_executed"])
        self.assertFalse(case["provider_calls_executed"])
        self.assertEqual(0, case["production_writes_executed"])
        self.assertEqual("NOT_RUN", receipt.external_states["production_canary"])

    def test_canary_rehearsal_fails_closed_on_unsafe_controls_or_incomplete_rollback(self) -> None:
        unsafe = self.canary_manifest()
        unsafe["controls"]["network_allowed"] = True
        with self.assertRaisesRegex(EvidenceContractError, "network_allowed"):
            self.execute_campaign(unsafe)
        incomplete = self.canary_manifest()
        incomplete["rehearsal"]["rollback_state"] = {"release": "unknown"}
        self._refresh_corpus(incomplete)
        self.assertEqual("BLOCKED", self.execute_campaign(incomplete).status)


class ExternalIntakeTests(unittest.TestCase):
    def make_receipt(self, raw: bytes) -> dict[str, object]:
        body: dict[str, object] = {
            "schema_version": "1.0",
            "receipt_id": "external-receipt-a",
            "evidence_kind": "provider-contract",
            "scope": {
                "tenant_id": "tenant-a",
                "project_id": "project-a",
                "campaign_id": "campaign-a",
                "policy_revision": "policy-v1",
                "source_revision": "source-v1",
            },
            "target_artifact_digest": SHA,
            "environment_digest": SHA,
            "corpus_digest": SHA,
            "authorization_digest": SHA,
            "replay_digest": SHA,
            "raw_evidence": {
                "path": "raw/evidence.bin",
                "sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
                "size_bytes": len(raw),
                "media_type": "application/octet-stream",
            },
            "author": {"principal_id": "author-a", "organization_id": "org-author"},
            "executor": {"principal_id": "executor-a", "organization_id": "org-executor"},
            "verifier": {"principal_id": "verifier-a", "organization_id": "org-verifier"},
            "execution_state": "PASSED",
            "signature_state": "UNVERIFIED_CALLER_ASSERTION",
        }
        return {**body, "receipt_digest": canonical_digest(body)}

    @staticmethod
    def policy(receipt_digest: str) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "policy_id": "local-intake-v1",
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "allowed_evidence_kinds": ["provider-contract"],
            "allowed_receipt_digests": [receipt_digest],
            "allowed_organizations": ["org-author", "org-executor", "org-verifier"],
            "revoked_principals": [],
            "require_distinct_organizations": True,
            "trust_root_state": "NOT_CONFIGURED",
        }

    def test_exact_external_receipt_can_be_locally_admitted_but_not_trusted(self) -> None:
        raw = b"external fixture bytes\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "raw").mkdir()
            (root / "raw/evidence.bin").write_bytes(raw)
            receipt = self.make_receipt(raw)
            decision = ingest_external_receipt(
                receipt, evidence_root=root, policy=self.policy(receipt["receipt_digest"])
            )
        self.assertEqual("EXTERNAL_RECEIPT_POLICY_ADMITTED", decision["status"])
        self.assertEqual("ADMITTED_UNVERIFIED", decision["local_admission_state"])
        self.assertEqual("NOT_RUN", decision["external_states"]["external_receipt_trust"])
        self.assertEqual("NOT_CERTIFIED", decision["external_states"]["external_certification"])

    def test_unallowlisted_revoked_or_nonseparated_receipt_is_quarantined(self) -> None:
        raw = b"raw"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "raw").mkdir()
            (root / "raw/evidence.bin").write_bytes(raw)
            receipt = self.make_receipt(raw)
            policy = self.policy(SHA)
            policy["revoked_principals"] = ["verifier-a"]
            receipt["executor"] = dict(receipt["author"])
            body = dict(receipt)
            body.pop("receipt_digest")
            receipt["receipt_digest"] = canonical_digest(body)
            decision = ingest_external_receipt(receipt, evidence_root=root, policy=policy)
        self.assertEqual("EXTERNAL_RECEIPT_QUARANTINED", decision["status"])
        self.assertIn("ROLE_PRINCIPALS_NOT_DISTINCT", decision["failures"])
        self.assertIn("VERIFIER_REVOKED", decision["failures"])
        self.assertIn("RECEIPT_NOT_ALLOWLISTED", decision["failures"])

    def test_external_intake_rejects_symlink_fifo_and_digest_drift(self) -> None:
        raw = b"raw"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "raw").mkdir()
            target = root / "target.bin"
            target.write_bytes(raw)
            os.symlink(target, root / "raw/evidence.bin")
            receipt = self.make_receipt(raw)
            with self.assertRaises(ArtifactBindingError):
                ingest_external_receipt(
                    receipt, evidence_root=root, policy=self.policy(receipt["receipt_digest"])
                )
            (root / "raw/evidence.bin").unlink()
            os.mkfifo(root / "raw/evidence.bin")
            with self.assertRaises(ArtifactBindingError):
                ingest_external_receipt(
                    receipt, evidence_root=root, policy=self.policy(receipt["receipt_digest"])
                )
            (root / "raw/evidence.bin").unlink()
            (root / "raw/evidence.bin").write_bytes(b"drift")
            with self.assertRaises(ArtifactBindingError):
                ingest_external_receipt(
                    receipt, evidence_root=root, policy=self.policy(receipt["receipt_digest"])
                )

    def test_caller_cannot_assert_signature_verification(self) -> None:
        raw = b"raw"
        receipt = self.make_receipt(raw)
        receipt["signature_state"] = "VERIFIED"
        body = dict(receipt)
        body.pop("receipt_digest")
        receipt["receipt_digest"] = canonical_digest(body)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "raw").mkdir()
            (root / "raw/evidence.bin").write_bytes(raw)
            with self.assertRaisesRegex(EvidenceContractError, "unverified"):
                ingest_external_receipt(
                    receipt, evidence_root=root, policy=self.policy(receipt["receipt_digest"])
                )

    def test_structural_external_preflight_never_claims_execution(self) -> None:
        def role(principal: str, organization: str) -> dict[str, str]:
            return {"principal_id": principal, "organization_id": organization}

        result = evaluate_external_preflight(
            {
                "schema_version": "1.0",
                "scope": {
                    "tenant_id": "tenant-a",
                    "project_id": "project-a",
                    "campaign_id": "external-a",
                    "policy_revision": "policy-v1",
                    "source_revision": "source-v1",
                },
                "release_digest": SHA,
                "provider_adapter": {
                    "provider_id": "provider-a",
                    "adapter_id": "adapter-a",
                    "adapter_registry_digest": SHA,
                    "executable_digest": SHA,
                    "effect_class": "REVERSIBLE",
                    "rollback_adapter_id": "rollback-a",
                    "authorization_digest": SHA,
                },
                "independent_holdout": {
                    "manifest_digest": SHA,
                    "case_count": 2,
                    "owner": role("owner-a", "org-owner"),
                    "executor": role("executor-a", "org-executor"),
                    "verifier": role("verifier-a", "org-verifier"),
                    "authorization_digest": SHA,
                },
                "representative_workload": {
                    "manifest_digest": SHA,
                    "case_count": 1,
                    "customer_authorizer": role("customer-a", "org-customer"),
                    "authorization_digest": SHA,
                },
                "production_change": {
                    "environment": "production-a",
                    "pkcs11_secret_reference": "pkcs11:token=external;object=release",
                    "canary_plan_digest": SHA,
                    "rollback_plan_digest": SHA,
                    "authorization_digest": SHA,
                },
            }
        )
        self.assertEqual("STRUCTURALLY_READY_FOR_EXTERNAL_TRUST_VERIFICATION", result["status"])
        self.assertFalse(result["external_operations_executed"])
        self.assertFalse(result["checks"]["external_signatures_verified"])
        self.assertEqual("NOT_RUN", result["external_states"]["real_provider_execution"])


class ArchiveContractTests(unittest.TestCase):
    def test_archive_scripts_are_neutralized_and_safe_reimplementation_runs(self) -> None:
        report = inspect_archive_contracts(SOURCE)
        self.assertEqual("PASSED", report["inspection_status"])
        self.assertFalse(report["archive_scripts_executed"])
        self.assertEqual([], report["active_archive_executables"])
        self.assertEqual(2, len(report["archive_scripts"]))
        for script in report["archive_scripts"]:
            self.assertEqual("0644", script["materialized_mode"])
            self.assertEqual("NOT_EXECUTED", script["execution_state"])
            self.assertEqual(SCRIPT_CONTRACTS[script["logical_path"]]["sha256"], script["sha256"])
        self.assertEqual("SOURCE_LAYOUT_INCOMPATIBLE", report["source_validator_parity_state"])
        self.assertEqual(95, report["source_blueprint_presence_score"])
        self.assertEqual("NOT_RUN", report["external_states"]["provider_execution"])

    def test_archive_inspection_rejects_active_script_and_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            (root / "scripts/score_readiness.py").write_text("raise SystemExit\n", encoding="utf-8")
            with self.assertRaisesRegex(ArchiveContractError, "neutralized script"):
                inspect_archive_contracts(root)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "target").write_text("data", encoding="utf-8")
            os.symlink(root / "target", root / "link")
            with self.assertRaisesRegex(ArchiveContractError, "symlink"):
                inspect_archive_contracts(root)

    def test_content_reference_contract_rejects_parent_escape(self) -> None:
        with self.assertRaises(ArtifactBindingError):
            ContentReference.from_mapping(
                {"path": "../outside", "sha256": SHA, "size_bytes": 0, "media_type": "text/plain"}
            )

    def test_safe_archive_parsers_reject_ambiguous_or_active_source_features(self) -> None:
        with self.assertRaisesRegex(ArchiveContractError, "duplicate key"):
            _json_bytes(b'{"value": 1, "value": 2}', "duplicate.json")
        with self.assertRaisesRegex(ArchiveContractError, "invalid number"):
            _json_bytes(b'{"value": NaN}', "nan.json")
        with self.assertRaisesRegex(ArchiveContractError, "unsupported schema keywords"):
            _schema_meta(
                {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "$ref": "https://example.invalid/remote-schema",
                },
                "remote.schema.json",
            )
        for payload in (
            b"value: &anchor unsafe\ncopy: *anchor\n",
            b"value: !python/object unsafe\n",
            b"value: first\nvalue: second\n",
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(ArchiveContractError):
                    _yaml_subset(payload, "unsafe.yaml")

    def test_safe_root_manifest_never_resolves_paths_from_disk(self) -> None:
        logical = {"inside.txt": (b"inside", 0o644, "inside.txt")}
        for unsafe in ("../outside", "/absolute", "nested\\windows"):
            with self.subTest(path=unsafe):
                with self.assertRaisesRegex(ArchiveContractError, "unsafe"):
                    _validate_root_manifest(
                        {
                            "files": [
                                {
                                    "path": unsafe,
                                    "sha256": hashlib.sha256(b"inside").hexdigest(),
                                }
                            ]
                        },
                        logical,
                    )

    def test_new_schema_roots_are_strict_json_and_receipt_fields_match(self) -> None:
        schemas = ROOT / "engines/software-factory-engine/schemas"
        for name in (
            "archive-contract-inspection.schema.json",
            "evidence-campaign.schema.json",
            "evidence-campaign-receipt.schema.json",
            "external-evidence-receipt.schema.json",
            "evidence-intake-policy.schema.json",
            "evidence-intake-decision.schema.json",
            "external-preflight.schema.json",
        ):
            with self.subTest(schema=name):
                document = json.loads((schemas / name).read_text(encoding="utf-8"))
                self.assertEqual("https://json-schema.org/draft/2020-12/schema", document["$schema"])
                self.assertFalse(document["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
