from __future__ import annotations

import json
import math
import re
import tempfile
import unittest
import zipfile
from pathlib import Path

from elmos_software_factory.canonical import canonical_digest
from elmos_software_factory.cli import _load_document
from elmos_software_factory.capabilities import (
    CAPABILITY_CONTRACTS,
    CapabilityRegistryError,
    load_capability_registry,
)
from elmos_software_factory.models import (
    _POLICY_KEYS,
    _REQUEST_KEYS,
    _REQUEST_REQUIRED_KEYS,
    _TOKEN,
    DependencyReceipt,
    ExternalObservation,
    ScopeEnvelope,
    make_dependency_receipt,
)
from elmos_software_factory.public_methods import (
    PUBLIC_METHODS,
    PublicMethodRegistryError,
    load_public_method_registry,
)
from elmos_software_factory.runtime import SoftwareFactoryEngine, dispatch_skill


SHA = "sha256:" + "a" * 64
ROOT = Path(__file__).resolve().parents[3]


class RuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = SoftwareFactoryEngine()
        self.registry = self.engine.registry

    @staticmethod
    def envelope() -> ScopeEnvelope:
        return ScopeEnvelope("tenant-a", "project-a", "run-a", "policy-v1", "source-v1", "idem-a")

    def receipts(self, package_id: str) -> list[dict[str, object]]:
        binding = next(item for item in self.registry.bindings.values() if item.package_id == package_id)
        result: list[dict[str, object]] = []
        for dependency in binding.dependencies:
            skill = self.registry.packages[dependency].name
            result.append(
                make_dependency_receipt(
                    package_id=dependency,
                    skill_name=skill,
                    envelope=self.envelope(),
                    request_digest=canonical_digest({"dependency_request": dependency}),
                    result_digest=canonical_digest({"dependency": dependency}),
                )
            )
        return result

    def request(
        self,
        skill_name: str,
        payload: dict[str, object],
        *,
        action: str | None = None,
        observations: list[dict[str, object]] | None = None,
        idempotency: bool = True,
    ) -> dict[str, object]:
        binding = self.registry.binding(skill_name)
        assert binding is not None
        selected_action = action or CAPABILITY_CONTRACTS[skill_name].action
        document_payload = dict(payload)
        document_payload.setdefault("action", selected_action)
        return {
            "contract_version": "1.0",
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "correlation_id": "run-a",
            "idempotency_key": "idem-a" if idempotency else None,
            "policy_revision": "policy-v1",
            "source_revision": "source-v1",
            "payload": document_payload,
            "policy": {
                "allowed_skills": [skill_name],
                "allowed_actions": [selected_action],
                "allowed_permissions": ["read", "write"],
                "allowed_sandbox_modes": ["read-only"],
                "allowed_providers": ["provider-a", "value"],
                "allowed_data_classes": ["public"],
                "max_nodes": 64,
                "max_parallelism": 4,
                "max_retries": 2,
                "max_cost_micros": 10_000,
                "min_quality_basis_points": 5000,
                "allow_global_knowledge": False,
            },
            "dependencies": [] if binding.package_id == "ROOT" else self.receipts(binding.package_id),
            "observations": observations or [],
        }

    @staticmethod
    def minimal_value(field: str) -> object:
        if field == "target_skill_or_public_method":
            return None
        if field in {
            "nodes", "invariants", "requested_permissions", "tools", "inventory", "edges",
            "capabilities", "unknowns", "requirements", "rules", "roles", "evidence_refs",
            "claims", "changes", "failures", "candidates", "data_classes", "entries",
            "argv", "scenario_set",
        }:
            return []
        if field in {
            "job", "target_profile", "rollback", "task", "usage", "candidate",
            "execution_contract", "event", "tool_call", "output", "limits", "lsp_request",
            "api_request", "repository_snapshot", "query", "target_ir", "workspace_request",
            "journal_event", "handoff", "build_request", "test_request", "generator_profile",
            "journey", "workload", "evidence_bundle", "outcome", "training_request",
        }:
            return {}
        if field in {"budget_micros", "capacity", "value_score"}:
            return 1
        return "value"

    def capability_payload(self, skill_name: str) -> dict[str, object]:
        contract = CAPABILITY_CONTRACTS[skill_name]
        payload: dict[str, object] = {"action": contract.action}
        for field in contract.required_inputs:
            if field == "target_skill_or_public_method":
                payload["target_skill"] = "elmos-software-factory-master"
            elif field != "source_revision":
                payload[field] = self.minimal_value(field)
        return payload

    def valid_claim(self) -> dict[str, object]:
        return {
            "id": "claim-a",
            "state": "PASSED",
            "critical": True,
            "evidence_digest": SHA,
            "executor_id": "executor-a",
            "verifier_id": "verifier-a",
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "correlation_id": "run-a",
            "policy_revision": "policy-v1",
            "source_revision": "source-v1",
        }

    def trusted_entry(self) -> dict[str, object]:
        return {
            "id": "entry-a",
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "visibility": "tenant",
            "score": 9000,
            "evidence_digest": SHA,
            "state": "trusted-verified",
        }

    def test_registry_matches_exact_archive_frontmatter_names(self) -> None:
        archive_names: set[str] = set()
        archive_dir = ROOT / "skills" / "subskills" / "archives"
        for archive in sorted(archive_dir.glob("*.zip")):
            with zipfile.ZipFile(archive) as source:
                for member in source.namelist():
                    if not member.endswith("/SKILL.md"):
                        continue
                    text = source.read(member).decode("utf-8")
                    match = re.search(r"(?m)^name:\s*[\"']?([^\"'\n]+)", text)
                    if match:
                        archive_names.add(match.group(1).strip())
        expected = archive_names | {"elmos-7plus1-commercial-software-factory"}
        self.assertEqual(expected, set(self.registry.bindings))
        self.assertEqual(102, len(expected))
        self.assertTrue(all(name.startswith("elmos-") for name in expected))

    def test_every_skill_has_an_exact_capability_contract(self) -> None:
        self.assertEqual(set(self.registry.bindings), set(CAPABILITY_CONTRACTS))
        self.assertEqual(102, len(CAPABILITY_CONTRACTS))
        for name, contract in CAPABILITY_CONTRACTS.items():
            with self.subTest(skill=name):
                result = self.engine.execute(name, self.request(name, self.capability_payload(name)))
                binding = result.as_dict()["output"]["binding_contract"]
                self.assertEqual(name, binding["skill_name"])
                self.assertEqual(contract.action, binding["effective_action"])
                self.assertEqual(contract.mode, binding["effective_mode"])
                self.assertNotEqual(
                    "CAPABILITY_UNSUPPORTED",
                    None if result.error is None else result.error.code,
                )
                if contract.mode == "requires_adapter":
                    self.assertEqual("REQUIRES_ADAPTER", result.status.value)

    def test_machine_readable_capability_registry_is_strict(self) -> None:
        path = ROOT / "engines" / "software-factory-engine" / "src" / "elmos_software_factory" / "capability_registry.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(102, len(document["capabilities"]))
        self.assertEqual(set(self.registry.bindings), {item["skill_name"] for item in document["capabilities"]})
        corrupted = path.read_text(encoding="utf-8").replace(
            '"schema_version": "1.0"',
            '"schema_version": "1.0", "schema_version": "1.0"',
            1,
        )
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "registry.json"
            target.write_text(corrupted, encoding="utf-8")
            with self.assertRaises(CapabilityRegistryError):
                load_capability_registry(target)

    def test_machine_readable_public_method_registry_and_adapter_union(self) -> None:
        source_dir = ROOT / "engines" / "software-factory-engine" / "src" / "elmos_software_factory"
        path = source_dir / "public_method_registry.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(50, len(document["methods"]))
        self.assertEqual(set(PUBLIC_METHODS), {item["method"] for item in document["methods"]})
        corrupted = path.read_text(encoding="utf-8").replace(
            '"schema_version": "1.0"',
            '"schema_version": "1.0", "schema_version": "1.0"',
            1,
        )
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "registry.json"
            target.write_text(corrupted, encoding="utf-8")
            with self.assertRaises(PublicMethodRegistryError):
                load_public_method_registry(target)
        raw_skill_registry = json.loads((source_dir / "skill_registry.json").read_text(encoding="utf-8"))
        for package in raw_skill_registry["packages"]:
            package_id = package["package_id"]
            names = [package["name"], *package["skills"]]
            expected = {
                CAPABILITY_CONTRACTS[name].action
                for name in names
                if CAPABILITY_CONTRACTS[name].mode == "requires_adapter"
            }
            expected.update(
                binding.action
                for binding in PUBLIC_METHODS.values()
                if binding.package_id == package_id and binding.execution_mode == "requires_adapter"
            )
            self.assertEqual(sorted(expected), package["adapter_actions"])

    def test_tool_and_compiler_children_require_adapters(self) -> None:
        cases = {
            "elmos-tool-runtime": "execute-tool",
            "elmos-compiler-static-pipeline": "invoke-compiler",
        }
        for skill, action in cases.items():
            with self.subTest(skill=skill):
                result = self.engine.execute(skill, self.request(skill, self.capability_payload(skill)))
                self.assertEqual("REQUIRES_ADAPTER", result.status.value)
                self.assertEqual(action, result.output["binding_contract"]["capability_action"])
                self.assertEqual("ADAPTER_REQUIRED", result.error.code)

    def test_local_linter_and_planner_are_child_specific(self) -> None:
        linter = "elmos-architecture-invariant-linter"
        planner = "elmos-implementation-dag-planner"
        linter_result = self.engine.execute(
            linter,
            self.request(linter, {"nodes": [], "invariants": []}),
        )
        planner_result = self.engine.execute(
            planner,
            self.request(
                planner,
                {"requirements": [{"id": "r1", "support_state": "supported"}]},
            ),
        )
        self.assertEqual("EXECUTED", linter_result.status.value)
        self.assertEqual("EXECUTED", planner_result.status.value)
        self.assertNotEqual(
            linter_result.output["binding_contract"]["capability_key"],
            planner_result.output["binding_contract"]["capability_key"],
        )

    def test_child_cannot_switch_to_another_package_action(self) -> None:
        skill = "elmos-architecture-invariant-linter"
        result = self.engine.execute(
            skill,
            self.request(skill, {"nodes": [], "invariants": []}, action="plan-job"),
        )
        self.assertEqual("BLOCKED", result.status.value)
        self.assertEqual("CAPABILITY_ACTION_MISMATCH", result.error.code)

    def test_missing_required_input_fails_closed(self) -> None:
        skill = "elmos-tool-runtime"
        result = self.engine.execute(skill, self.request(skill, {}))
        self.assertEqual("BLOCKED", result.status.value)
        self.assertEqual("REQUIRED_INPUT_MISSING", result.error.code)

    def test_external_observation_never_substitutes_for_adapter(self) -> None:
        skill = "elmos-tool-runtime"
        body = {
            "observation_id": "obs-a",
            "action": "execute-tool",
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "correlation_id": "run-a",
            "policy_revision": "policy-v1",
            "source_revision": "source-v1",
            "evidence_digest": SHA,
            "byte_count": 100,
            "executor_id": "executor-a",
            "verifier_id": "verifier-a",
            "authorized": True,
            "verified": True,
        }
        observation = {**body, "observation_digest": canonical_digest(body)}
        result = self.engine.execute(
            skill,
            self.request(skill, {"tool_call": {"name": "safe"}}, observations=[observation]),
        )
        self.assertEqual("REQUIRES_ADAPTER", result.status.value)
        self.assertEqual("NOT_RUN", result.as_dict()["external_evidence_status"])
        self.assertEqual("CALLER_ASSERTED_NOT_LOCALLY_VERIFIED", result.evidence[0]["trust_state"])

    def test_observation_correlation_mismatch_blocks(self) -> None:
        skill = "elmos-tool-runtime"
        body = {
            "observation_id": "obs-a", "action": "execute-tool", "tenant_id": "tenant-a",
            "project_id": "project-a", "correlation_id": "other-run", "policy_revision": "policy-v1",
            "source_revision": "source-v1", "evidence_digest": SHA, "byte_count": 1,
            "executor_id": "executor-a", "verifier_id": "verifier-a", "authorized": True,
            "verified": True,
        }
        observation = {**body, "observation_digest": canonical_digest(body)}
        result = self.engine.execute(
            skill,
            self.request(skill, {"tool_call": {}}, observations=[observation]),
        )
        self.assertEqual("EVIDENCE_SCOPE_MISMATCH", result.error.code)

    def test_evidence_gate_is_local_structure_only_and_scope_bound(self) -> None:
        skill = "elmos-mechanical-completion-gate"
        complete = self.engine.execute(skill, self.request(skill, {"claims": [self.valid_claim()]}))
        self.assertEqual("EXECUTED", complete.status.value)
        self.assertEqual("LOCAL_STRUCTURE_PASSED", complete.output["decision"])
        self.assertEqual("EXTERNAL_GATE_NOT_RUN", complete.output["external_gate_state"])
        self.assertFalse(complete.output["certified"])
        stale = self.valid_claim()
        stale["source_revision"] = "old"
        blocked = self.engine.execute(skill, self.request(skill, {"claims": [stale]}))
        self.assertEqual("BLOCKED", blocked.status.value)
        self.assertEqual("EVIDENCE_INCOMPLETE", blocked.error.code)

    def test_promotion_stays_blocked_and_queries_are_tenant_safe(self) -> None:
        promote = "elmos-rule-promotion-governance"
        result = self.engine.execute(
            promote,
            self.request(promote, {"entries": [self.trusted_entry()], "candidate": {"id": "c1"}}),
        )
        self.assertEqual("BLOCKED", result.status.value)
        self.assertFalse(result.output["promoted"])
        query = "elmos-transformation-knowledge-base"
        cross = self.trusted_entry()
        cross["tenant_id"] = "tenant-b"
        blocked = self.engine.execute(query, self.request(query, {"entries": [cross]}))
        self.assertEqual("NO_TRUSTED_RULE", blocked.error.code)

    def test_caller_availability_is_explicitly_unverified(self) -> None:
        skill = "elmos-multi-objective-router"
        payload = {
            "candidates": [{
                "provider": "provider-a", "model": "model-a", "available": True,
                "cost_micros": 100, "quality_basis_points": 9000, "data_classes": ["public"],
            }],
            "data_classes": ["public"],
        }
        result = self.engine.execute(skill, self.request(skill, payload))
        self.assertEqual("EXECUTED", result.status.value)
        self.assertEqual("CALLER_DECLARED_UNVERIFIED", result.output["selected"]["availability_state"])
        self.assertEqual("NOT_RUN", result.output["availability_evidence_state"])

    def test_ready_tasks_with_zero_capacity_block(self) -> None:
        skill = "elmos-task-dag-orchestrator"
        result = self.engine.execute(
            skill,
            self.request(skill, {"nodes": [{"id": "a", "depends_on": []}], "capacity": 0}),
        )
        self.assertEqual("NO_CAPACITY", result.error.code)

    def public_payload(self, action: str) -> dict[str, object]:
        payloads: dict[str, dict[str, object]] = {
            "resolve-package": {"package_id": "P00"},
            "compile-workflow": {"nodes": [], "invariants": []},
            "plan-job": {"job": {}, "budget_micros": 1},
            "permission-decision": {"requested_permissions": [], "sandbox_mode": "read-only", "tools": []},
            "build-graph": {"inventory": [], "edges": [], "capabilities": [], "unknowns": []},
            "compile-semantic-ir": {"inventory": [], "edges": [], "capabilities": [], "unknowns": []},
            "discover-capabilities": {"inventory": [], "edges": [], "capabilities": [], "unknowns": []},
            "query-repository": {"inventory": [], "edges": [], "capabilities": [], "unknowns": [], "query": {}},
            "expand-requirements": {"requirements": []},
            "design-architecture": {"requirements": [], "target_profile": {}},
            "plan-transformation": {"requirements": []},
            "plan-migration": {"requirements": [], "rollback": {}},
            "evaluate-gap": {"requirements": []},
            "reconcile-tasks": {"nodes": []},
            "dispatch-plan": {"nodes": [], "capacity": 1},
            "compose-agent": {"roles": ["reviewer"]},
            "assemble-proof": {"evidence_refs": [SHA]},
            "evaluate-coverage": {"claims": [self.valid_claim()]},
            "plan-verification": {"claims": [], "changes": ["change-a"]},
            "evaluate-gate": {"claims": [self.valid_claim()]},
            "plan-repair": {"failures": [{"id": "failure-a"}], "budget_micros": 1},
            "classify-task": {"task": {"kind": "code", "modalities": [], "context_tokens": 1}},
            "route-plan": {"candidates": [{"provider": "provider-a", "model": "m", "available": True, "cost_micros": 1, "quality_basis_points": 9000, "data_classes": ["public"]}], "data_classes": ["public"]},
            "forecast-cost": {"usage": {"input_tokens": 1, "output_tokens": 1, "runs": 1}},
            "query-knowledge": {"entries": [self.trusted_entry()]},
            "rank-repairs": {"entries": [self.trusted_entry()], "failure_signature": "f"},
            "evaluate-promotion": {"entries": [self.trusted_entry()], "candidate": {"id": "c"}},
            "plan-learning": {"entries": [], "candidate": {}, "value_score": 1},
        }
        return dict(payloads.get(action, {}))

    def test_all_50_public_method_modes_are_authoritative(self) -> None:
        self.assertEqual(50, len(PUBLIC_METHODS))
        for method, method_binding in PUBLIC_METHODS.items():
            with self.subTest(method=method):
                skill = self.registry.packages[method_binding.package_id].name
                payload = self.public_payload(method_binding.action)
                for field in method_binding.required_inputs:
                    payload.setdefault(field, self.minimal_value(field))
                request = self.request(skill, payload, action=method_binding.action)
                result = self.engine.execute_method(method, request)
                contract = result.output["binding_contract"]
                self.assertEqual(method, contract["public_method"])
                self.assertEqual(method_binding.execution_mode, contract["effective_mode"])
                if method_binding.execution_mode == "requires_adapter":
                    self.assertEqual("REQUIRES_ADAPTER", result.status.value)
                else:
                    self.assertNotEqual("REQUIRES_ADAPTER", result.status.value)
                if result.error is not None:
                    self.assertIn(
                        result.error.code,
                        set(method_binding.domain_errors) | set(method_binding.platform_errors),
                    )

    def test_all_50_public_methods_fail_when_a_required_input_is_missing(self) -> None:
        for method, method_binding in PUBLIC_METHODS.items():
            with self.subTest(method=method):
                skill = self.registry.packages[method_binding.package_id].name
                payload = self.public_payload(method_binding.action)
                for field in method_binding.required_inputs:
                    payload.setdefault(field, self.minimal_value(field))
                payload.pop(method_binding.required_inputs[0])
                result = self.engine.execute_method(
                    method,
                    self.request(skill, payload, action=method_binding.action),
                )
                self.assertEqual("BLOCKED", result.status.value)
                self.assertEqual("REQUIRED_INPUT_MISSING", result.error.code)
                self.assertIn(
                    result.error.code,
                    set(method_binding.domain_errors) | set(method_binding.platform_errors),
                )
                self.assertIn(
                    method_binding.required_inputs[0],
                    result.error.details["missing"],
                )

    def test_invalid_non_json_request_returns_stable_failure(self) -> None:
        result = dispatch_skill("elmos-software-factory-master", {"value": math.nan})
        self.assertEqual("FAILED", result["status"])
        self.assertEqual("REQUEST_INVALID", result["error"]["code"])
        self.assertIsNone(result["output"]["input_digest"])
        self.assertEqual({"retryable": False, "after_ms": None}, result["retry"])

    def test_json_schema_fields_match_runtime_models(self) -> None:
        schemas = ROOT / "engines" / "software-factory-engine" / "schemas"
        request_schema = json.loads((schemas / "request.schema.json").read_text(encoding="utf-8"))
        result_schema = json.loads((schemas / "result.schema.json").read_text(encoding="utf-8"))
        dependency_schema = json.loads(
            (schemas / "dependency-receipt.schema.json").read_text(encoding="utf-8")
        )
        observation_schema = json.loads(
            (schemas / "external-observation.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(_REQUEST_KEYS, frozenset(request_schema["properties"]))
        self.assertEqual(_REQUEST_REQUIRED_KEYS, frozenset(request_schema["required"]))
        self.assertEqual(_POLICY_KEYS, frozenset(request_schema["properties"]["policy"]["properties"]))
        self.assertEqual(_TOKEN.pattern, request_schema["$defs"]["token"]["pattern"])
        self.assertEqual(_TOKEN.pattern, result_schema["$defs"]["token"]["pattern"])
        self.assertEqual(_TOKEN.pattern, dependency_schema["$defs"]["token"]["pattern"])
        self.assertEqual(_TOKEN.pattern, observation_schema["$defs"]["token"]["pattern"])
        dependency = self.receipts("P01")[0]
        self.assertEqual(set(dependency), set(dependency_schema["properties"]))
        parsed_dependency = DependencyReceipt.from_mapping(dependency)
        self.assertEqual(set(parsed_dependency.as_dict()), set(dependency_schema["properties"]))
        observation_body = {
            "observation_id": "obs", "action": "execute-tool", "tenant_id": "tenant-a",
            "project_id": "project-a", "correlation_id": "run-a", "policy_revision": "policy-v1",
            "source_revision": "source-v1", "evidence_digest": SHA, "byte_count": 1,
            "executor_id": "executor", "verifier_id": "verifier", "authorized": True, "verified": True,
        }
        observation = {**observation_body, "observation_digest": canonical_digest(observation_body)}
        self.assertEqual(
            set(ExternalObservation.from_mapping(observation).as_dict()),
            set(observation_schema["properties"]),
        )
        sample_skill = "elmos-architecture-invariant-linter"
        sample = self.engine.execute(
            sample_skill,
            self.request(sample_skill, {"nodes": [], "invariants": []}),
        ).as_dict()
        self.assertEqual(set(sample), set(result_schema["properties"]))

    def test_request_model_requires_schema_required_documents_and_token_syntax(self) -> None:
        skill = "elmos-architecture-invariant-linter"
        base = self.request(skill, {"nodes": [], "invariants": []})
        for field in ("payload", "policy", "dependencies", "observations"):
            with self.subTest(field=field):
                invalid = json.loads(json.dumps(base))
                invalid.pop(field)
                result = dispatch_skill(skill, invalid)
                self.assertEqual("FAILED", result["status"])
                self.assertEqual("REQUEST_INVALID", result["error"]["code"])
        invalid_token = json.loads(json.dumps(base))
        invalid_token["tenant_id"] = "tenant with spaces"
        result = dispatch_skill(skill, invalid_token)
        self.assertEqual("FAILED", result["status"])
        self.assertEqual("REQUEST_INVALID", result["error"]["code"])

    def test_request_payload_policy_and_dependencies_bind_result_and_receipt_digests(self) -> None:
        skill = "elmos-architecture-invariant-linter"
        first_request = self.request(
            skill,
            {"nodes": [{"id": "alpha", "depends_on": []}], "invariants": []},
        )
        second_request = json.loads(json.dumps(first_request))
        second_request["payload"]["nodes"][0]["id"] = "beta"
        first = self.engine.execute(skill, first_request)
        second = self.engine.execute(skill, second_request)
        self.assertNotEqual(first.request_digest, second.request_digest)
        self.assertNotEqual(first.result_digest, second.result_digest)
        self.assertNotEqual(first.dependency_receipt["receipt_digest"], second.dependency_receipt["receipt_digest"])
        self.assertEqual(first.request_digest, first.dependency_receipt["request_digest"])

        policy_request = json.loads(json.dumps(first_request))
        policy_request["policy"]["max_nodes"] = 65
        policy_result = self.engine.execute(skill, policy_request)
        self.assertNotEqual(first.request_digest, policy_result.request_digest)
        self.assertNotEqual(first.result_digest, policy_result.result_digest)
        self.assertNotEqual(
            first.dependency_receipt["receipt_digest"],
            policy_result.dependency_receipt["receipt_digest"],
        )

        dependent_skill = "elmos-permission-policy-engine"
        dependency_one = make_dependency_receipt(
            package_id="P00",
            skill_name="elmos-software-factory-master",
            envelope=self.envelope(),
            request_digest=canonical_digest({"dependency_input": "alpha"}),
            result_digest=canonical_digest({"dependency_result": "same"}),
        )
        dependency_two = make_dependency_receipt(
            package_id="P00",
            skill_name="elmos-software-factory-master",
            envelope=self.envelope(),
            request_digest=canonical_digest({"dependency_input": "beta"}),
            result_digest=canonical_digest({"dependency_result": "same"}),
        )
        dependent_one = self.request(dependent_skill, {"requested_permissions": []})
        dependent_two = json.loads(json.dumps(dependent_one))
        dependent_one["dependencies"] = [dependency_one]
        dependent_two["dependencies"] = [dependency_two]
        result_one = self.engine.execute(dependent_skill, dependent_one)
        result_two = self.engine.execute(dependent_skill, dependent_two)
        self.assertNotEqual(result_one.request_digest, result_two.request_digest)
        self.assertNotEqual(result_one.result_digest, result_two.result_digest)
        self.assertNotEqual(
            result_one.dependency_receipt["receipt_digest"],
            result_two.dependency_receipt["receipt_digest"],
        )

    def test_named_local_inputs_have_meaningful_distinct_outputs(self) -> None:
        cases = [
            (
                "RepoQuery.execute",
                {"inventory": [], "query": {"term": "alpha"}},
                {"inventory": [], "query": {"term": "beta"}},
                lambda output: output["query_plan"]["query_digest"],
            ),
            (
                "VerificationPlanner.plan",
                {"claims": [{"id": "alpha"}], "changes": ["change"]},
                {"claims": [{"id": "beta"}], "changes": ["change"]},
                lambda output: output["claim_set_digest"],
            ),
            (
                "CostEngine.forecast",
                {"candidates": [{"provider": "provider-a", "model": "m", "cost_micros": 1}], "usage": {"runs": 1}},
                {"candidates": [{"provider": "provider-a", "model": "m", "cost_micros": 2}], "usage": {"runs": 1}},
                lambda output: output["candidate_set_digest"],
            ),
            (
                "RepairCorpus.retrieve",
                {"entries": [self.trusted_entry()], "failure_signature": "alpha"},
                {"entries": [self.trusted_entry()], "failure_signature": "beta"},
                lambda output: output["repair_query_digest"],
            ),
            (
                "LearningQueue.enqueue",
                {"entries": [self.trusted_entry()], "candidate": {}, "value_score": 1},
                {"entries": [{**self.trusted_entry(), "id": "entry-b"}], "candidate": {}, "value_score": 1},
                lambda output: output["learning_item_plan"]["entries_digest"],
            ),
        ]
        for method, alpha_payload, beta_payload, selector in cases:
            with self.subTest(method=method):
                binding = PUBLIC_METHODS[method]
                skill = self.registry.packages[binding.package_id].name
                alpha = self.engine.execute_method(
                    method, self.request(skill, alpha_payload, action=binding.action)
                )
                beta = self.engine.execute_method(
                    method, self.request(skill, beta_payload, action=binding.action)
                )
                self.assertNotEqual(selector(alpha.output), selector(beta.output))
                self.assertNotEqual(alpha.result_digest, beta.result_digest)
                self.assertEqual(method, alpha.output["handler_contract"]["capability_identity"])

    def test_public_domain_and_platform_errors_are_separate(self) -> None:
        for method, binding in PUBLIC_METHODS.items():
            with self.subTest(method=method):
                self.assertTrue(binding.domain_errors)
                self.assertIn("REQUIRED_INPUT_MISSING", binding.platform_errors)
                self.assertIn("ADAPTER_REQUIRED", binding.platform_errors)
                self.assertFalse(set(binding.domain_errors) & set(binding.platform_errors))

    def test_every_public_method_blocked_envelope_code_is_registry_authorized(self) -> None:
        for method, binding in PUBLIC_METHODS.items():
            skill = self.registry.packages[binding.package_id].name
            payload = self.public_payload(binding.action)
            for field in binding.required_inputs:
                payload.setdefault(field, self.minimal_value(field))
            authorized_codes = set(binding.domain_errors) | set(binding.platform_errors)

            denied = self.request(skill, payload, action=binding.action)
            denied["policy"]["allowed_skills"] = []
            denied_result = self.engine.execute_method(method, denied)
            with self.subTest(method=method, path="policy"):
                self.assertEqual("POLICY_DENIED", denied_result.error.code)
                self.assertIn(denied_result.error.code, authorized_codes)

            approval = self.request(skill, payload, action=binding.action)
            approval["policy"]["approval_required_actions"] = [binding.action]
            approval["policy"]["approved_actions"] = []
            approval_result = self.engine.execute_method(method, approval)
            with self.subTest(method=method, path="approval"):
                self.assertEqual("APPROVAL_REQUIRED", approval_result.error.code)
                self.assertIn(approval_result.error.code, authorized_codes)

            if self.registry.packages[binding.package_id].dependencies:
                dependency = self.request(skill, payload, action=binding.action)
                dependency["dependencies"] = []
                dependency_result = self.engine.execute_method(method, dependency)
                with self.subTest(method=method, path="dependency"):
                    self.assertEqual("DEPENDENCY_BLOCKED", dependency_result.error.code)
                    self.assertIn(dependency_result.error.code, authorized_codes)

            if binding.execution_mode == "requires_adapter":
                idempotency = self.request(skill, payload, action=binding.action, idempotency=False)
                idempotency_result = self.engine.execute_method(method, idempotency)
                with self.subTest(method=method, path="idempotency"):
                    self.assertEqual("IDEMPOTENCY_KEY_REQUIRED", idempotency_result.error.code)
                    self.assertIn(idempotency_result.error.code, authorized_codes)

    def test_workflow_violation_maps_to_declared_domain_error(self) -> None:
        method = "WorkflowCompiler.compile"
        binding = PUBLIC_METHODS[method]
        skill = self.registry.packages[binding.package_id].name
        result = self.engine.execute_method(
            method,
            self.request(
                skill,
                {"nodes": [], "violations": ["invariant-x"]},
                action=binding.action,
            ),
        )
        self.assertEqual("BLOCKED", result.status.value)
        self.assertEqual("WORKFLOW_INVALID", result.error.code)
        self.assertEqual("INVARIANT_VIOLATION", result.error.details["runtime_error_code"])
        self.assertIn(result.error.code, binding.domain_errors)

    def test_cli_rejects_oversized_sparse_file_before_read(self) -> None:
        from elmos_software_factory.canonical import MAX_JSON_BYTES

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "oversized.json"
            with path.open("wb") as stream:
                stream.truncate(MAX_JSON_BYTES + 1)
            with self.assertRaisesRegex(ValueError, "request exceeds"):
                _load_document(str(path))


if __name__ == "__main__":
    unittest.main()
