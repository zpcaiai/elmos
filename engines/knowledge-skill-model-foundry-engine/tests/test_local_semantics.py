"""Forward acceptance for the exact repository-owned local semantic Skills."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
import tempfile
import unittest
from typing import Any

from elmos_foundry.domain import CertificationStatus, TenantScope
from elmos_foundry.kernel import ExecutionKernel
from elmos_foundry.local_semantics import LOCAL_SEMANTIC_SKILLS
from elmos_foundry.service import FoundryService
from elmos_foundry.store import FoundryStore


class LocalSemanticAcceptanceTests(unittest.TestCase):
    """Exercise every local binding through the public service boundary."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.kernel = ExecutionKernel()
        self.store = FoundryStore(
            Path(self.directory.name) / "local-semantics.sqlite3",
            context_verifier=self.kernel.require_context,
        )
        self.addCleanup(self.store.close)
        self.service = FoundryService(kernel=self.kernel, store=self.store)
        self.scope = self._mint_scope(
            tenant_id="tenant-local-a",
            project_id="project-local-a",
            invocation_id="invocation-local-a",
            lease_id="lease-local-a",
        )

    def _mint_scope(
        self,
        *,
        tenant_id: str,
        project_id: str,
        invocation_id: str,
        lease_id: str,
    ) -> TenantScope:
        return self.kernel.mint_context(
            tenant_id=tenant_id,
            project_id=project_id,
            actor_id="actor-local",
            environment_id="environment-local",
            workspace_digest="sha256:" + "a" * 64,
            revision_set_id="sha256:" + "b" * 64,
            purpose="local-semantic-acceptance",
            capabilities=(
                "foundry.adapter.execute",
                "foundry.store.read",
                "foundry.store.write",
            ),
            ttl_seconds=600,
            invocation_id=invocation_id,
            lease_id=lease_id,
        )

    @staticmethod
    def _foundation_inputs(skill_name: str) -> dict[str, Any]:
        architecture: Mapping[str, Any] = {
            "owner": "foundry-team",
            "version": "3.0.0",
            "rollback": {"mode": "content-addressed"},
        }
        policy: Mapping[str, Any] = {
            "allowed_tools": ["repository.read"],
            "required_gates": ["local-contract"],
            "side_effects": "none",
        }
        runtime: Mapping[str, Any] = {
            "runtime_version": "3.0.0",
            "capabilities": ["local.semantic"],
        }
        requirement: Mapping[str, Any] = {
            "skill_name": "typed-skill-contract",
            "purpose": "validate a typed local contract",
            "acceptance": {"status": "PASS"},
        }
        if skill_name == "package-conformance-validator":
            requirement = {
                "package_name": "knowledge-skill-model-foundry",
                "version": "3.0.0",
                "skills": ["typed-skill-contract", "artifact-identity-and-hashing"],
                "owner": "foundry-team",
                "rollback": {"mode": "content-addressed"},
            }
        elif skill_name == "capability-dependency-graph":
            runtime = {
                "nodes": [
                    {"id": "capability-root", "dependencies": []},
                    {"id": "capability-child", "dependencies": ["capability-root"]},
                ]
            }
        return {
            "business requirement": requirement,
            "architecture decision": architecture,
            "policy profile": policy,
            "runtime capability inventory": runtime,
        }

    @staticmethod
    def _skill_runtime_inputs() -> dict[str, Any]:
        return {
            "runbook": {"runbook_id": "runbook-local"},
            "experience episodes": {"episode_ids": ["episode-local"]},
            "task contract": {
                "pack": "05-skill-foundry-runtime",
                "query": "skill dependency resolver",
                "candidate_limit": 4,
            },
            "semantic IR": {"requested_skills": ["typed-skill-contract"]},
            "policy context": {"mode": "default-deny"},
        }

    @staticmethod
    def _security_inputs(scope: TenantScope) -> dict[str, Any]:
        return {
            "identity": {
                "tenant_id": scope.tenant_id,
                "project_id": scope.project_id,
                "actor_id": scope.actor_id,
            },
            "request context": {
                "environment_id": scope.environment_id,
                "authority_source": "host",
                "authorized": True,
                "requested_tools": ["repository.read"],
                "aggregate_id": "audit-local",
            },
            "artifact provenance": {
                "tenant_id": scope.tenant_id,
                "project_id": scope.project_id,
                "workspace_digest": scope.workspace_digest,
                "revision_set_id": scope.revision_set_id,
            },
            "data classification": {"classification": "internal"},
            "policy profile": {
                "leased_tools": ["repository.read"],
                "default_deny": True,
            },
        }

    @staticmethod
    def _knowledge_inputs(*, include_secret: bool = False) -> dict[str, Any]:
        document: dict[str, Any] = {"body": "bounded local document"}
        if include_secret:
            document.update(
                {
                    "api_token": "top-secret-value",
                    "note": "Authorization: Bearer abc.def.ghi",
                }
            )
        return {
            "repository": {"path": "src/service.py", "revision": "abc123"},
            "document": document,
            "API schema": {"openapi": "3.1.0"},
            "database metadata": {"engine": "sqlite"},
            "runtime trace": {"status": "PASS"},
            "ticket or incident": {"ticket_id": "ticket-local"},
        }

    @staticmethod
    def _memory_inputs(*, aggregate_id: str = "memory-local-empty") -> dict[str, Any]:
        return {
            "agent trace": {
                "task_type": "semantic-validation",
                "task_goal": "validate deterministic local behavior",
                "trajectory": [{"step": "inspect"}],
                "aggregate_id": aggregate_id,
            },
            "tool event": {"tool": "repository.read", "status": "PASS"},
            "patch": {"content_digest": "sha256:" + "c" * 64},
            "test result": {"reward_score": 0.95, "outcome": {"status": "PASS"}},
            "human feedback": {"decision": "accepted"},
        }

    @staticmethod
    def _dataset_inputs(skill_name: str) -> dict[str, Any]:
        episode: Mapping[str, Any] = {
            "episodes": [{"episode_id": "episode-dataset", "outcome": "PASS"}],
            "training_consent": "allow",
        }
        evidence: Mapping[str, Any] = {"verdict": "PASS", "independent": True}
        if skill_name == "dataset-quarantine-management":
            episode = {
                "dataset_items": [
                    {"item_id": "item-safe", "content_digest": "sha256:" + "d" * 64},
                    {"item_id": "item-risk", "content_digest": "sha256:" + "e" * 64},
                ]
            }
            evidence = {"quarantine_item_ids": ["item-risk"]}
        return {
            "experience episode": episode,
            "knowledge object": {"object_id": "knowledge-local"},
            "human feedback": {"decision": "accepted"},
            "verification evidence": evidence,
        }

    @staticmethod
    def _evaluation_inputs(skill_name: str) -> dict[str, Any]:
        candidate: Mapping[str, Any] = {"status": "PASS", "confidence": 0.96}
        policy: Mapping[str, Any] = {"required_gates": ["gate-local"]}
        if skill_name == "uncertainty-and-abstention-evaluation":
            policy = {"minimum_confidence": 0.90}
        return {
            "candidate output": candidate,
            "trace": [
                {
                    "gate": "gate-local",
                    "status": "PASS",
                    "digest": "sha256:" + "f" * 64,
                }
            ],
            "repository snapshot": {"revision": "abc123"},
            "policy": policy,
            "baseline": {"version": "baseline-local"},
        }

    @staticmethod
    def _serving_inputs() -> dict[str, Any]:
        schema = {
            "type": "object",
            "required": ["path"],
            "properties": {"path": {"type": "string"}},
            "additionalProperties": False,
        }
        return {
            "inference request": {
                "request_id": "request-local",
                "tool_calls": [
                    {"tool": "repository.read", "arguments": {"path": "README.md"}}
                ],
            },
            "task risk": {"class": "medium"},
            "tenant policy": {
                "max_cost_usd": 0.20,
                "max_latency_ms": 500,
                "allowed_tools": ["repository.read"],
                "tool_schemas": {"repository.read": schema},
            },
            "model registry": {
                "candidates": [
                    {
                        "candidate_id": "model-local",
                        "version": "1.2.3",
                        "artifact_digest": "sha256:" + "1" * 64,
                        "health": "AVAILABLE",
                        "warmup": "PASS",
                        "estimated_cost_usd": 0.05,
                        "estimated_latency_ms": 100,
                        "quality_score": 0.9,
                    }
                ]
            },
            "capacity state": {"status": "AVAILABLE"},
        }

    def _inputs_for(self, skill_name: str, scope: TenantScope | None = None) -> dict[str, Any]:
        record = self.service.skills.get_skill_record(skill_name)
        self.assertIsNotNone(record)
        assert record is not None
        pack = record["pack"]
        if pack == "00-foundation-contracts":
            values = self._foundation_inputs(skill_name)
        elif pack == "05-skill-foundry-runtime":
            values = self._skill_runtime_inputs()
        elif pack == "11-security-privacy-compliance":
            values = self._security_inputs(scope or self.scope)
        elif pack == "01-knowledge-ingestion-governance":
            values = self._knowledge_inputs(
                include_secret=skill_name == "sensitive-data-and-secret-detection"
            )
        elif pack == "04-memory-experience-flywheel":
            values = self._memory_inputs()
        elif pack == "06-dataset-foundry":
            values = self._dataset_inputs(skill_name)
        elif pack == "09-evaluation-proof-certification":
            values = self._evaluation_inputs(skill_name)
        elif pack == "10-serving-routing-inference":
            values = self._serving_inputs()
        else:  # pragma: no cover - exact allowlist contract
            self.fail(f"no local semantic fixture is defined for pack {pack}")
        self.assertEqual(set(values), set(record["inputs"]))
        return values

    def _execute(
        self,
        skill_name: str,
        inputs: Mapping[str, Any],
        *,
        scope: TenantScope | None = None,
        service: FoundryService | None = None,
    ) -> Any:
        selected_scope = scope or self.scope
        selected_service = service or self.service
        return selected_service.execute_skill(
            skill_name,
            {"operation": "local-semantic-execute", "inputs": inputs},
            selected_scope,
            adapter_id=f"local.{skill_name}",
            invocation_id=selected_scope.invocation_id,
        )

    @classmethod
    def _values_for_key(cls, value: Any, key: str) -> list[Any]:
        matches: list[Any] = []
        if isinstance(value, Mapping):
            for child_key, child in value.items():
                if child_key == key:
                    matches.append(child)
                matches.extend(cls._values_for_key(child, key))
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for child in value:
                matches.extend(cls._values_for_key(child, key))
        return matches

    def _assert_local_success(self, skill_name: str, result: Any) -> Mapping[str, Any]:
        record = self.service.skills.get_skill_record(skill_name)
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(result.status, "SUCCESS", result.error)
        self.assertIsNone(result.error)
        self.assertFalse(result.external_effects_performed)
        self.assertEqual(result.external_evidence_status, "NOT_RUN")
        self.assertIs(result.certification_status, CertificationStatus.NOT_CERTIFIED)
        self.assertEqual(result.outputs["outcome"], "SUCCEEDED")
        self.assertEqual(result.outputs["execution_status"], "SUCCEEDED")
        self.assertEqual(result.outputs["effect_class"], "LOCAL_DETERMINISTIC")
        self.assertEqual(result.outputs["effect_outcome"], "NOT_APPLICABLE")
        self.assertIsNone(result.outputs["broker_id"])
        self.assertIsNone(result.outputs["route_id"])
        inner = result.outputs["result"]
        self.assertEqual(inner["status"], "SUCCEEDED")
        self.assertEqual(set(inner["outputs"]), set(record["outputs"]))
        self.assertEqual(inner["external_evidence_status"], "NOT_RUN")
        self.assertEqual(inner["certification_status"], "NOT_CERTIFIED")
        self.assertTrue(self._values_for_key(result.outputs, "certification_status"))
        self.assertEqual(
            set(self._values_for_key(result.outputs, "certification_status")),
            {"NOT_CERTIFIED"},
        )
        self.assertEqual(
            set(self._values_for_key(result.outputs, "external_evidence_status")),
            {"NOT_RUN"},
        )
        self.assertLessEqual(
            set(self._values_for_key(result.outputs, "provider_execution_status")),
            {"NOT_RUN"},
        )
        self.assertLessEqual(
            set(self._values_for_key(result.outputs, "certified")),
            {False},
        )
        return inner["outputs"]

    def test_all_exact_local_skills_execute_with_declared_contracts(self) -> None:
        self.assertEqual(len(LOCAL_SEMANTIC_SKILLS), 26)
        described = {
            skill_name
            for row in self.service.status()["adapters"]
            if row["effect_class"] == "LOCAL_DETERMINISTIC"
            for skill_name in row["exact_skills"]
        }
        self.assertEqual(set(described), set(LOCAL_SEMANTIC_SKILLS))
        for skill_name in sorted(LOCAL_SEMANTIC_SKILLS):
            with self.subTest(skill_name=skill_name):
                result = self._execute(skill_name, self._inputs_for(skill_name))
                self._assert_local_success(skill_name, result)

    def test_every_local_skill_rejects_a_missing_declared_input(self) -> None:
        for skill_name in sorted(LOCAL_SEMANTIC_SKILLS):
            with self.subTest(skill_name=skill_name):
                values = self._inputs_for(skill_name)
                missing_name = sorted(values)[0]
                del values[missing_name]
                result = self._execute(skill_name, values)
                self.assertEqual(result.status, "BLOCKED")
                self.assertEqual(result.outputs["outcome"], "NOT_RUN")
                self.assertEqual(result.outputs["execution_status"], "NOT_RUN")
                self.assertIn(missing_name, result.error or "")
                self.assertFalse(result.external_effects_performed)

    def test_local_skill_rejects_an_undeclared_input(self) -> None:
        skill_name = "artifact-identity-and-hashing"
        values = self._inputs_for(skill_name)
        values["undeclared provider credential"] = {"token": "must-not-cross-boundary"}
        result = self._execute(skill_name, values)
        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual(result.outputs["outcome"], "NOT_RUN")
        self.assertIn("undeclared", result.error or "")

    def test_family_specific_invalid_semantics_fail_closed(self) -> None:
        invalid_cases: list[tuple[str, dict[str, Any], str]] = []

        typed = self._foundation_inputs("typed-skill-contract")
        typed["business requirement"] = {
            **typed["business requirement"],
            "undeclared": True,
        }
        invalid_cases.append(("typed-skill-contract", typed, "keys are not exact"))

        cyclic = self._foundation_inputs("capability-dependency-graph")
        cyclic["runtime capability inventory"] = {
            "nodes": [
                {"id": "capability-a", "dependencies": ["capability-b"]},
                {"id": "capability-b", "dependencies": ["capability-a"]},
            ]
        }
        invalid_cases.append(("capability-dependency-graph", cyclic, "contains a cycle"))

        disclosure = self._skill_runtime_inputs()
        disclosure["task contract"] = {"pack": "unknown-pack", "candidate_limit": 2}
        invalid_cases.append(
            ("progressive-skill-disclosure", disclosure, "references an unknown pack")
        )

        resolver = self._skill_runtime_inputs()
        resolver["semantic IR"] = {"requested_skills": ["unknown-local-skill"]}
        invalid_cases.append(("skill-dependency-resolver", resolver, "unknown requested Skills"))

        quarantine = self._dataset_inputs("dataset-quarantine-management")
        quarantine["verification evidence"] = {"quarantine_item_ids": ["item-unknown"]}
        invalid_cases.append(
            ("dataset-quarantine-management", quarantine, "references unknown items")
        )

        evidence = self._evaluation_inputs("evidence-aggregation-and-completeness")
        evidence["trace"] = [
            {"gate": "gate-local", "status": "PASS", "digest": "not-a-digest"}
        ]
        invalid_cases.append(
            ("evidence-aggregation-and-completeness", evidence, "must use sha256")
        )

        for skill_name, values, error_fragment in invalid_cases:
            with self.subTest(skill_name=skill_name):
                result = self._execute(skill_name, values)
                self.assertEqual(result.status, "FAILED")
                self.assertEqual(result.outputs["outcome"], "FAILED")
                self.assertEqual(result.outputs["local_maximum_decision"], "NOT_READY")
                self.assertIn(error_fragment, result.error or "")
                self.assertFalse(result.external_effects_performed)

    def test_policy_denials_are_explicit_but_remain_local_self_attested(self) -> None:
        pending_cases = {
            "environment-owned-authority": "trusted-authorization-receipt-verifier-unbound",
            "least-privilege-tool-authorization": "trusted-tool-lease-verifier-unbound",
            "workspace-attachment-ownership-fencing": "trusted-provenance-receipt-verifier-unbound",
        }
        for skill_name, reason in pending_cases.items():
            with self.subTest(skill_name=skill_name, state="unverified-input-claims"):
                pending = self._execute(skill_name, self._security_inputs(self.scope))
                pending_outputs = self._assert_local_success(skill_name, pending)
                self.assertEqual(
                    pending_outputs["policy decision"]["decision"],
                    "EVIDENCE_PENDING",
                )
                self.assertEqual(
                    pending_outputs["policy decision"]["reason_codes"], [reason]
                )

        environment_inputs = self._security_inputs(self.scope)
        environment_inputs["identity"] = {
            **environment_inputs["identity"],
            "tenant_id": "tenant-wrong",
        }
        environment = self._execute("environment-owned-authority", environment_inputs)
        environment_outputs = self._assert_local_success(
            "environment-owned-authority", environment
        )
        self.assertEqual(environment_outputs["policy decision"]["decision"], "DENY")
        self.assertIn(
            "tenant_id-mismatch",
            environment_outputs["policy decision"]["reason_codes"],
        )

        tool_inputs = self._security_inputs(self.scope)
        tool_inputs["request context"] = {
            **tool_inputs["request context"],
            "requested_tools": ["repository.write"],
        }
        tool = self._execute("least-privilege-tool-authorization", tool_inputs)
        tool_outputs = self._assert_local_success("least-privilege-tool-authorization", tool)
        self.assertEqual(tool_outputs["policy decision"]["decision"], "DENY")
        self.assertEqual(
            tool_outputs["policy decision"]["reason_codes"],
            ["unleased-tool:repository.write"],
        )

        fence_inputs = self._security_inputs(self.scope)
        fence_inputs["artifact provenance"] = {
            **fence_inputs["artifact provenance"],
            "project_id": "project-wrong",
        }
        fence = self._execute("workspace-attachment-ownership-fencing", fence_inputs)
        fence_outputs = self._assert_local_success(
            "workspace-attachment-ownership-fencing", fence
        )
        self.assertEqual(fence_outputs["policy decision"]["decision"], "DENY")
        self.assertIn(
            "project_id-mismatch",
            fence_outputs["policy decision"]["reason_codes"],
        )

    def test_secret_detection_redacts_values_without_claiming_full_coverage(self) -> None:
        result = self._execute(
            "sensitive-data-and-secret-detection",
            self._knowledge_inputs(include_secret=True),
        )
        outputs = self._assert_local_success("sensitive-data-and-secret-detection", result)
        normalized = outputs["normalized artifact"]
        self.assertEqual(normalized["content"]["document"]["api_token"], "[REDACTED]")
        self.assertNotIn("abc.def.ghi", str(normalized["content"]))
        self.assertGreaterEqual(len(normalized["secret_findings"]), 2)
        self.assertEqual(
            normalized["secret_scan_coverage"], "LOCAL_HEURISTIC_SELF_ATTESTED"
        )

    def test_durable_capture_replay_is_idempotent_and_tenant_project_isolated(self) -> None:
        capture_inputs = self._memory_inputs()
        first = self._execute("experience-episode-capture", capture_inputs)
        first_outputs = self._assert_local_success("experience-episode-capture", first)
        second = self._execute("experience-episode-capture", capture_inputs)
        second_outputs = self._assert_local_success("experience-episode-capture", second)
        self.assertEqual(first_outputs["memory record"], second_outputs["memory record"])
        self.assertEqual(first_outputs["memory record"]["sequence"], 1)

        aggregate_id = first_outputs["memory record"]["aggregate_id"]
        replay_a = self._execute(
            "tenant-memory-isolation-and-replay",
            self._memory_inputs(aggregate_id=aggregate_id),
        )
        replay_a_outputs = self._assert_local_success(
            "tenant-memory-isolation-and-replay", replay_a
        )
        self.assertEqual(replay_a_outputs["experience episode"]["episode_count"], 1)

        scope_b = self._mint_scope(
            tenant_id="tenant-local-b",
            project_id="project-local-b",
            invocation_id="invocation-local-b",
            lease_id="lease-local-b",
        )
        replay_b = self._execute(
            "tenant-memory-isolation-and-replay",
            self._memory_inputs(aggregate_id=aggregate_id),
            scope=scope_b,
        )
        replay_b_outputs = self._assert_local_success(
            "tenant-memory-isolation-and-replay", replay_b
        )
        self.assertEqual(replay_b_outputs["experience episode"]["episode_count"], 0)
        self.assertEqual(
            replay_b_outputs["memory record"]["tenant_id"], scope_b.tenant_id
        )
        self.assertEqual(
            replay_b_outputs["memory record"]["project_id"], scope_b.project_id
        )

    def test_durable_audit_uses_separate_tenant_project_event_chains(self) -> None:
        inputs_a = self._security_inputs(self.scope)
        audit_a = self._execute("tamper-evident-audit-log", inputs_a)
        outputs_a = self._assert_local_success("tamper-evident-audit-log", audit_a)

        scope_b = self._mint_scope(
            tenant_id="tenant-local-b",
            project_id="project-local-b",
            invocation_id="invocation-audit-b",
            lease_id="lease-audit-b",
        )
        inputs_b = self._security_inputs(scope_b)
        audit_b = self._execute("tamper-evident-audit-log", inputs_b, scope=scope_b)
        outputs_b = self._assert_local_success("tamper-evident-audit-log", audit_b)

        self.assertEqual(outputs_a["audit event"]["sequence"], 1)
        self.assertEqual(outputs_b["audit event"]["sequence"], 1)
        self.assertNotEqual(
            outputs_a["audit event"]["event_digest"],
            outputs_b["audit event"]["event_digest"],
        )
        self.assertEqual(len(self.store.list_events(self.scope, "audit-local")), 1)
        self.assertEqual(len(self.store.list_events(scope_b, "audit-local")), 1)

    def test_store_dependent_skills_fail_closed_without_durable_store(self) -> None:
        no_store_service = FoundryService(kernel=self.kernel)
        for skill_name in (
            "tamper-evident-audit-log",
            "experience-episode-capture",
            "tenant-memory-isolation-and-replay",
        ):
            with self.subTest(skill_name=skill_name):
                result = self._execute(
                    skill_name,
                    self._inputs_for(skill_name),
                    service=no_store_service,
                )
                self.assertEqual(result.status, "FAILED")
                self.assertEqual(result.outputs["outcome"], "FAILED")
                self.assertFalse(result.external_effects_performed)
                self.assertEqual(result.external_evidence_status, "NOT_RUN")
                self.assertIs(
                    result.certification_status,
                    CertificationStatus.NOT_CERTIFIED,
                )

    def test_dataset_and_inference_uncertainty_never_promote_or_execute(self) -> None:
        dataset_inputs = self._dataset_inputs("dataset-contract-and-schema")
        dataset = self._execute("dataset-contract-and-schema", dataset_inputs)
        dataset_outputs = self._assert_local_success("dataset-contract-and-schema", dataset)
        eligibility = dataset_outputs["training eligibility decision"]
        self.assertFalse(eligibility["eligible"])
        self.assertEqual(eligibility["decision"], "EVIDENCE_PENDING")
        self.assertEqual(
            eligibility["input_claims_only"],
            {
                "training_consent_claimed": True,
                "independent_verification_claimed": True,
            },
        )
        self.assertEqual(
            eligibility["reason_codes"],
            [
                "trusted-request-bound-consent-verifier-required",
                "trusted-independent-evidence-verifier-required",
            ],
        )

        canonical_inputs = self._dataset_inputs("task-canonicalization-and-normalization")
        raw_secret = "customer-secret-must-not-be-returned"
        canonical_inputs["knowledge object"] = {
            "object_id": "knowledge-local",
            "api_token": raw_secret,
        }
        canonical = self._execute(
            "task-canonicalization-and-normalization", canonical_inputs
        )
        canonical_outputs = self._assert_local_success(
            "task-canonicalization-and-normalization", canonical
        )
        canonical_item = canonical_outputs["versioned dataset"]["items"][0]
        self.assertFalse(canonical_item["raw_content_stored"])
        self.assertNotIn("content", canonical_item)
        self.assertNotIn(raw_secret, str(canonical_outputs))

        uncertainty_inputs = self._evaluation_inputs(
            "uncertainty-and-abstention-evaluation"
        )
        uncertainty_inputs["candidate output"] = {
            "status": "INCONCLUSIVE",
            "confidence": 0.99,
        }
        uncertainty = self._execute(
            "uncertainty-and-abstention-evaluation", uncertainty_inputs
        )
        uncertainty_outputs = self._assert_local_success(
            "uncertainty-and-abstention-evaluation", uncertainty
        )
        self.assertEqual(
            uncertainty_outputs["certification decision"]["decision"], "ABSTAIN"
        )
        self.assertFalse(
            uncertainty_outputs["certification decision"]["certified"]
        )

        serving_inputs = self._serving_inputs()
        serving_inputs["model registry"]["candidates"][0]["version"] = "latest"
        serving = self._execute("model-version-pinning-determinism", serving_inputs)
        serving_outputs = self._assert_local_success(
            "model-version-pinning-determinism", serving
        )
        self.assertEqual(serving_outputs["routed request"]["decision"], "BLOCKED")
        self.assertEqual(
            serving_outputs["structured response"]["provider_response"], None
        )
        self.assertEqual(serving_outputs["usage record"]["provider_calls"], 0)

    def test_tool_policy_violation_blocks_route_without_provider_execution(self) -> None:
        values = self._serving_inputs()
        values["inference request"]["tool_calls"] = [
            {"tool": "repository.write", "arguments": {"path": "README.md"}}
        ]
        result = self._execute("tool-call-schema-and-policy-check", values)
        outputs = self._assert_local_success("tool-call-schema-and-policy-check", result)
        self.assertEqual(outputs["routed request"]["decision"], "BLOCKED")
        self.assertEqual(
            outputs["serving evidence"]["tool_call_violations"][0]["code"],
            "TOOL_NOT_ALLOWED",
        )
        self.assertEqual(outputs["usage record"]["provider_calls"], 0)

    def test_duplicate_evidence_gate_cannot_erase_an_unresolved_result(self) -> None:
        values = self._evaluation_inputs("evidence-aggregation-and-completeness")
        values["trace"] = [
            {
                "gate": "gate-local",
                "status": "NOT_RUN",
                "digest": "sha256:" + "1" * 64,
            },
            {
                "gate": "gate-local",
                "status": "PASS",
                "digest": "sha256:" + "2" * 64,
            },
        ]
        result = self._execute("evidence-aggregation-and-completeness", values)
        self.assertEqual(result.status, "FAILED")
        self.assertEqual(result.outputs["outcome"], "FAILED")
        self.assertIn("duplicates gate", result.error or "")

    def test_empty_noop_collections_and_model_identity_are_handled_exactly(self) -> None:
        quarantine_values = self._dataset_inputs("dataset-quarantine-management")
        raw_secret = "customer-payload-must-not-be-returned"
        quarantine_values["experience episode"] = {
            "dataset_items": [
                {
                    "item_id": "item-safe",
                    "content": raw_secret,
                }
            ]
        }
        quarantine_values["verification evidence"] = {"quarantine_item_ids": []}
        quarantine = self._execute(
            "dataset-quarantine-management", quarantine_values
        )
        quarantine_outputs = self._assert_local_success(
            "dataset-quarantine-management", quarantine
        )
        self.assertEqual(
            quarantine_outputs["training eligibility decision"]["decision"],
            "NO_CHANGE",
        )
        self.assertNotIn(raw_secret, str(quarantine_outputs))

        tool_values = self._serving_inputs()
        tool_values["inference request"]["tool_calls"] = []
        tool_values["tenant policy"]["allowed_tools"] = []
        tool_values["tenant policy"]["tool_schemas"] = {}
        tool_result = self._execute("tool-call-schema-and-policy-check", tool_values)
        tool_outputs = self._assert_local_success(
            "tool-call-schema-and-policy-check", tool_result
        )
        self.assertEqual(tool_outputs["serving evidence"]["validated_call_count"], 0)
        self.assertEqual(tool_outputs["serving evidence"]["tool_call_violations"], [])

        for skill_name in (
            "health-warmup-and-readiness",
            "complexity-risk-cost-latency-routing",
            "model-version-pinning-determinism",
        ):
            for missing_field in ("candidate_id", "artifact_digest"):
                with self.subTest(skill_name=skill_name, missing_field=missing_field):
                    values = self._serving_inputs()
                    candidate = values["model registry"]["candidates"][0]
                    del candidate[missing_field]
                    candidate["provider_secret"] = raw_secret
                    result = self._execute(skill_name, values)
                    outputs = self._assert_local_success(skill_name, result)
                    self.assertEqual(outputs["routed request"]["decision"], "BLOCKED")
                    self.assertIsNone(outputs["routed request"]["selected_candidate"])
                    self.assertNotIn(raw_secret, str(outputs))
                    self.assertEqual(outputs["usage record"]["provider_calls"], 0)


if __name__ == "__main__":
    unittest.main()
