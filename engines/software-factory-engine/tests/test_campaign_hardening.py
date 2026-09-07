from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import FunctionType
from unittest.mock import patch

try:
    import jsonschema
except ImportError:  # pragma: no cover - exercised in the dependency-free suite
    jsonschema = None

from elmos_software_factory import capabilities as capabilities_module
from elmos_software_factory.capabilities import CAPABILITY_REGISTRY_DIGEST
from elmos_software_factory.campaigns import (
    _RUNTIME_SOURCE_FILES,
    _RUNTIME_SOURCE_PREFIX,
    campaign_corpus_digest,
    replay_campaign,
    run_campaign,
)
from elmos_software_factory.canonical import canonical_digest
from elmos_software_factory.evidence_models import CampaignReceipt, EvidenceContractError
from elmos_software_factory.public_methods import PUBLIC_METHOD_REGISTRY_DIGEST
from elmos_software_factory.runtime import SoftwareFactoryEngine


ROOT = Path(__file__).resolve().parents[3]
SCHEMA_ROOT = ROOT / "engines" / "software-factory-engine" / "schemas"


class CampaignHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="elmos-campaign-bindings-")
        self.addCleanup(temporary.cleanup)
        self.evidence_root = Path(temporary.name)

    @staticmethod
    def _scope() -> dict[str, str]:
        return {
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "campaign_id": "campaign-a",
            "policy_revision": "policy-v1",
            "source_revision": "source-v1",
        }

    @staticmethod
    def _controls() -> dict[str, object]:
        return {
            "network_allowed": False,
            "provider_calls_allowed": False,
            "max_production_writes": 0,
        }

    @staticmethod
    def _request(
        action: str,
        payload: dict[str, object],
        *,
        allowed_skill: str = "elmos-software-factory-master",
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
                "allowed_skills": [allowed_skill],
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

    def _write_json(self, name: str, value: object) -> dict[str, object]:
        raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
        path = self.evidence_root / name
        path.write_bytes(raw)
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
            target_rows.append({"path": relative, "sha256": raw_digest, "size_bytes": len(raw)})
        target_rows.sort(key=lambda item: str(item["path"]))
        aggregate_lines = "".join(
            f"{item['sha256']}\t{item['size_bytes']}\t{item['path']}\n" for item in target_rows
        )
        target_hex = hashlib.sha256(aggregate_lines.encode()).hexdigest()
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
                "aggregate_sha256": target_hex,
                "file_count": len(target_rows),
                "total_size_bytes": sum(int(item["size_bytes"]) for item in target_rows),
                "scope": ["bounded test artifact"],
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
        manifest["target_artifact_digest"] = "sha256:" + target_hex
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

    def holdout_manifest(self) -> dict[str, object]:
        manifest: dict[str, object] = {
            "schema_version": "1.0",
            "campaign_type": "local-holdout",
            "scope": self._scope(),
            "target_artifact_digest": "sha256:" + "0" * 64,
            "environment_digest": "sha256:" + "0" * 64,
            "corpus_digest": "sha256:" + "0" * 64,
            "executor_id": "repository-local-runner",
            "controls": self._controls(),
            "bindings": {},
            "development_case_digests": ["sha256:" + hashlib.sha256(b"development-case").hexdigest()],
            "cases": [
                {
                    "case_id": "case-001",
                    "skill_name": "elmos-architecture-invariant-linter",
                    "request": self._request(
                        "compile-workflow",
                        {"nodes": [], "invariants": []},
                        allowed_skill="elmos-architecture-invariant-linter",
                    ),
                    "expected_status": "EXECUTED",
                    "expected_error_code": None,
                }
            ],
        }
        return self._bind(manifest)

    def provider_manifest(self) -> dict[str, object]:
        provider_request = {"input_digest": "sha256:" + "c" * 64, "mode": "fixture"}
        manifest: dict[str, object] = {
            "schema_version": "1.0",
            "campaign_type": "provider-contract-simulation",
            "scope": self._scope(),
            "target_artifact_digest": "sha256:" + "0" * 64,
            "environment_digest": "sha256:" + "0" * 64,
            "corpus_digest": "sha256:" + "0" * 64,
            "executor_id": "repository-local-runner",
            "controls": self._controls(),
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
                    "case_id": "provider-001",
                    "runtime_request": self._request("certify-release", {"evidence_bundle": {}}),
                    "provider_request": provider_request,
                    "provider_response": {
                        "provider_id": "fixture-provider",
                        "operation": "certify-release",
                        "request_digest": "sha256:"
                        + hashlib.sha256(
                            json.dumps(
                                provider_request,
                                ensure_ascii=False,
                                sort_keys=True,
                                separators=(",", ":"),
                            ).encode()
                        ).hexdigest(),
                        "state": "SUCCEEDED",
                        "artifact_digest": "sha256:" + "d" * 64,
                        "error_code": None,
                    },
                    "expected_provider_state": "SUCCEEDED",
                    "expected_mapped_error": None,
                }
            ],
        }
        return self._bind(manifest)

    def test_content_bindings_are_required_and_resolved(self) -> None:
        manifest = self.holdout_manifest()
        receipt = run_campaign(manifest, evidence_root=self.evidence_root)
        self.assertEqual("PASSED", receipt.status)
        with self.assertRaisesRegex(EvidenceContractError, "evidence_root"):
            run_campaign(manifest)
        (self.evidence_root / "local-holdout-environment.json").write_text(
            '{"environment":"tampered"}\n', encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "content"):
            run_campaign(manifest, evidence_root=self.evidence_root)
        manifest = self.holdout_manifest()
        (self.evidence_root / _RUNTIME_SOURCE_PREFIX / "runtime.py").write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "content"):
            run_campaign(manifest, evidence_root=self.evidence_root)

    def test_bound_manifest_semantics_and_runtime_members_are_required(self) -> None:
        manifest = self.holdout_manifest()
        bindings = manifest["bindings"]
        assert isinstance(bindings, dict)
        target_reference = bindings["target_manifest"]
        assert isinstance(target_reference, dict)
        target_path = self.evidence_root / str(target_reference["path"])
        target = json.loads(target_path.read_text(encoding="utf-8"))
        target["files"] = [
            item for item in target["files"] if item["path"] != f"{_RUNTIME_SOURCE_PREFIX}/runtime.py"
        ]
        target["file_count"] = len(target["files"])
        target["total_size_bytes"] = sum(item["size_bytes"] for item in target["files"])
        aggregate = "".join(
            f"{item['sha256']}\t{item['size_bytes']}\t{item['path']}\n" for item in target["files"]
        )
        target["aggregate_sha256"] = hashlib.sha256(aggregate.encode()).hexdigest()
        bindings["target_manifest"] = self._write_json(str(target_reference["path"]), target)
        manifest["target_artifact_digest"] = "sha256:" + target["aggregate_sha256"]
        with self.assertRaisesRegex(EvidenceContractError, "omits required runtime artifact"):
            run_campaign(manifest, evidence_root=self.evidence_root)

        manifest = self.holdout_manifest()
        bindings = manifest["bindings"]
        assert isinstance(bindings, dict)
        environment_reference = bindings["environment_manifest"]
        assert isinstance(environment_reference, dict)
        environment_path = self.evidence_root / str(environment_reference["path"])
        environment = json.loads(environment_path.read_text(encoding="utf-8"))
        environment["scope"]["tenant_id"] = "tenant-b"
        bindings["environment_manifest"] = self._write_json(str(environment_reference["path"]), environment)
        manifest["environment_digest"] = bindings["environment_manifest"]["sha256"]
        with self.assertRaisesRegex(EvidenceContractError, "environment manifest scope"):
            run_campaign(manifest, evidence_root=self.evidence_root)

        manifest = self.holdout_manifest()
        bindings = manifest["bindings"]
        assert isinstance(bindings, dict)
        development_reference = bindings["development_manifest"]
        assert isinstance(development_reference, dict)
        development_path = self.evidence_root / str(development_reference["path"])
        development = json.loads(development_path.read_text(encoding="utf-8"))
        development["cases"][0]["case_id"] = "development-tampered"
        bindings["development_manifest"] = self._write_json(
            str(development_reference["path"]), development
        )
        with self.assertRaisesRegex(EvidenceContractError, "development manifest case_digests"):
            run_campaign(manifest, evidence_root=self.evidence_root)

    def test_runtime_request_scope_must_equal_campaign_scope(self) -> None:
        for manifest, request in (
            (self.holdout_manifest(), lambda item: item["cases"][0]["request"]),
            (self.provider_manifest(), lambda item: item["fixtures"][0]["runtime_request"]),
        ):
            with self.subTest(campaign_type=manifest["campaign_type"]):
                request(manifest)["tenant_id"] = "tenant-b"
                self._refresh_corpus(manifest)
                with self.assertRaisesRegex(EvidenceContractError, "scope differs"):
                    run_campaign(manifest, evidence_root=self.evidence_root)

    def test_provider_receipt_binds_runtime_and_all_registry_digests(self) -> None:
        manifest = self.provider_manifest()
        receipt = run_campaign(manifest, evidence_root=self.evidence_root)
        result = receipt.case_results[0]
        for field in (
            "runtime_request_digest",
            "runtime_result_digest",
            "skill_registry_digest",
            "capability_registry_digest",
            "public_method_registry_digest",
        ):
            self.assertRegex(result[field], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(CAPABILITY_REGISTRY_DIGEST, result["capability_registry_digest"])
        self.assertEqual(PUBLIC_METHOD_REGISTRY_DIGEST, result["public_method_registry_digest"])

        original = SoftwareFactoryEngine.execute_method

        def changed_result(engine: SoftwareFactoryEngine, method_name: str, document: object):
            observed = original(engine, method_name, document)
            return replace(observed, result_digest="sha256:" + "e" * 64)

        with patch.object(SoftwareFactoryEngine, "execute_method", changed_result):
            with self.assertRaisesRegex(EvidenceContractError, "runtime callable"):
                replay_campaign(manifest, receipt.as_dict(), evidence_root=self.evidence_root)

        stale_code = original.__code__.replace(
            co_consts=(*original.__code__.co_consts, "stale-loaded-bytecode")
        )
        stale_loaded = FunctionType(
            stale_code,
            original.__globals__,
            original.__name__,
            original.__defaults__,
            original.__closure__,
        )
        stale_loaded.__module__ = original.__module__
        stale_loaded.__qualname__ = original.__qualname__
        with patch.object(SoftwareFactoryEngine, "execute_method", stale_loaded):
            with self.assertRaisesRegex(EvidenceContractError, "loaded bytecode differs"):
                replay_campaign(manifest, receipt.as_dict(), evidence_root=self.evidence_root)

        contract = next(iter(capabilities_module.CAPABILITY_CONTRACTS.values()))
        original_action = contract.action
        object.__setattr__(contract, "action", "tampered-action")
        try:
            with self.assertRaisesRegex(EvidenceContractError, "loaded capability registry"):
                replay_campaign(manifest, receipt.as_dict(), evidence_root=self.evidence_root)
        finally:
            object.__setattr__(contract, "action", original_action)

    @unittest.skipIf(jsonschema is None, "jsonschema is needed for schema parity checks")
    def test_campaign_schema_and_runtime_reject_the_same_negative_shapes(self) -> None:
        schema = json.loads((SCHEMA_ROOT / "evidence-campaign.schema.json").read_text(encoding="utf-8"))
        valid = self.holdout_manifest()
        jsonschema.Draft202012Validator(schema).validate(valid)
        self.assertEqual("PASSED", run_campaign(valid, evidence_root=self.evidence_root).status)

        negatives: list[dict[str, object]] = []
        missing_cases = copy.deepcopy(valid)
        missing_cases.pop("cases")
        negatives.append(missing_cases)
        wrong_branch = copy.deepcopy(valid)
        wrong_branch["provider_contract"] = {}
        negatives.append(wrong_branch)
        extra_scope = copy.deepcopy(valid)
        extra_scope["scope"]["unexpected"] = "value"
        negatives.append(extra_scope)
        missing_development_binding = copy.deepcopy(valid)
        missing_development_binding["bindings"].pop("development_manifest")
        negatives.append(missing_development_binding)
        for invalid in negatives:
            with self.subTest(invalid=invalid):
                with self.assertRaises(jsonschema.ValidationError):
                    jsonschema.Draft202012Validator(schema).validate(invalid)
                with self.assertRaises(EvidenceContractError):
                    run_campaign(invalid, evidence_root=self.evidence_root)

    @unittest.skipIf(jsonschema is None, "jsonschema is needed for schema parity checks")
    def test_receipt_schema_and_runtime_reject_nested_drift(self) -> None:
        schema = json.loads(
            (SCHEMA_ROOT / "evidence-campaign-receipt.schema.json").read_text(encoding="utf-8")
        )
        receipt = run_campaign(self.holdout_manifest(), evidence_root=self.evidence_root).as_dict()
        jsonschema.Draft202012Validator(schema).validate(receipt)
        CampaignReceipt.from_mapping(receipt)

        for mutate in ("scope", "evidence_state"):
            invalid = copy.deepcopy(receipt)
            if mutate == "scope":
                invalid["scope"]["unexpected"] = "value"
            else:
                invalid["evidence_state"] = "LOCAL_PROVIDER_CONTRACT_SIMULATED_SELF_ATTESTED"
            with self.subTest(mutate=mutate):
                with self.assertRaises(jsonschema.ValidationError):
                    jsonschema.Draft202012Validator(schema).validate(invalid)
                with self.assertRaises(EvidenceContractError):
                    CampaignReceipt.from_mapping(invalid)


if __name__ == "__main__":
    unittest.main()
