"""End-to-end tests for the compiled 132-Skill registry and exact dispatcher."""

from __future__ import annotations

import unittest
from collections import Counter
from copy import deepcopy
from typing import Any

from elmos_semantic_assurance.canonical import digest_value
from elmos_semantic_assurance.contracts import (
    AssuranceScope,
    CapabilityState,
    EvidenceStatus,
    Operation,
    TrustedIdentity,
)
from elmos_semantic_assurance.registry import (
    COLLISION_ALIASES,
    EXPECTED_BATCH_COUNTS,
    SkillBinding,
    SkillRegistry,
)
from elmos_semantic_assurance.runtime import (
    EXECUTE_ROLE,
    AuthorizationError,
    SemanticAssuranceRuntime,
)
from elmos_semantic_assurance.store import IdempotencyConflict, SemanticAssuranceStore


def _sha(character: str) -> str:
    return "sha256:" + character * 64


def _scope_document(
    *,
    tenant: str = "tenant-a",
    project: str = "project-a",
    run: str = "run-registry",
) -> dict[str, str]:
    return {
        "tenantId": tenant,
        "projectId": project,
        "runId": run,
        "snapshotId": "snapshot-registry",
        "snapshotDigest": _sha("1"),
        "sourceDigest": _sha("2"),
        "targetDigest": _sha("3"),
        "environmentDigest": _sha("4"),
        "semanticProfileDigest": _sha("5"),
        "toolchainDigest": _sha("6"),
        "corpusDigest": _sha("7"),
        "assumptionsDigest": _sha("8"),
        "routeId": "java-to-csharp-v1",
        "sourceTechnology": "java",
        "sourceDialect": "java-21",
        "sourceRuntime": "openjdk-21.0.2",
        "targetTechnology": "csharp",
        "targetDialect": "csharp-12",
        "targetRuntime": "dotnet-8.0.2",
    }


def _identity(
    *,
    actor: str = "actor-a",
    tenant: str = "tenant-a",
    project: str = "project-a",
    roles: tuple[str, ...] = (EXECUTE_ROLE,),
) -> TrustedIdentity:
    return TrustedIdentity(
        tenant_id=tenant,
        project_id=project,
        actor_id=actor,
        roles=roles,
        authorization_ref="authorization-registry",
    )


def _assurance_scope() -> AssuranceScope:
    value = _scope_document()
    return AssuranceScope(
        tenant_id=value["tenantId"],
        project_id=value["projectId"],
        run_id=value["runId"],
        snapshot_id=value["snapshotId"],
        snapshot_digest=value["snapshotDigest"],
        source_digest=value["sourceDigest"],
        target_digest=value["targetDigest"],
        environment_digest=value["environmentDigest"],
        semantic_profile_digest=value["semanticProfileDigest"],
        toolchain_digest=value["toolchainDigest"],
        corpus_digest=value["corpusDigest"],
        assumptions_digest=value["assumptionsDigest"],
        route_id=value["routeId"],
        source_technology=value["sourceTechnology"],
        source_dialect=value["sourceDialect"],
        source_runtime=value["sourceRuntime"],
        target_technology=value["targetTechnology"],
        target_dialect=value["targetDialect"],
        target_runtime=value["targetRuntime"],
    )


def _evidence(scope: dict[str, str], state: str) -> dict[str, Any]:
    return {
        "state": state,
        "subjectDigest": scope["sourceDigest"],
        "snapshotDigest": scope["snapshotDigest"],
        "environmentDigest": scope["environmentDigest"],
        "toolchainDigest": scope["toolchainDigest"],
        "corpusDigest": scope["corpusDigest"],
        "assumptionsDigest": scope["assumptionsDigest"],
        "executorId": "executor-registry",
    }


def _payload(binding: SkillBinding, scope: dict[str, str]) -> dict[str, Any]:
    operation = binding.operation
    if operation is Operation.MODEL_NORMALIZATION:
        return {
            "items": [
                {
                    "id": "item-registry",
                    "kind": "semantic-item",
                    "state": "KNOWN",
                    "sourceSpan": {
                        "artifactDigest": scope["sourceDigest"],
                        "start": 0,
                        "end": 1,
                    },
                    "provenance": {"source": "registry-test"},
                }
            ]
        }
    if operation is Operation.SEMANTIC_COMPARISON:
        return {
            "source": {"observable": 1},
            "target": {"observable": 1},
            "relation": "EXACT",
        }
    if operation is Operation.GRAPH_ANALYSIS:
        return {
            "graph": {
                "nodes": [
                    {"id": "entry", "entry": True},
                    {"id": "exit", "exit": True},
                ],
                "edges": [{"from": "entry", "to": "exit", "kind": "flow"}],
            },
            "acyclicRequired": True,
            "singleEntryRequired": True,
            "exitRequired": True,
        }
    if operation is Operation.COVERAGE_ANALYSIS:
        return {
            "dimensions": [
                {
                    "id": "declared-feature-denominator",
                    "numerator": 1,
                    "denominator": 1,
                    "thresholdNumerator": 1,
                    "thresholdDenominator": 1,
                }
            ]
        }
    if operation is Operation.CORPUS_GOVERNANCE:
        return {
            "fixtures": [
                {
                    "id": "fixture-registry",
                    "contentDigest": _sha("a"),
                    "partition": "development",
                    "license": {
                        "spdx": "Apache-2.0",
                        "reviewStatus": "APPROVED",
                        "provenanceDigest": _sha("b"),
                    },
                }
            ]
        }
    if operation is Operation.EVIDENCE_VALIDATION:
        return {
            "evidence": [
                _evidence(scope, EvidenceStatus.LOCAL_EXECUTED_SELF_ATTESTED.value)
            ]
        }
    if operation in {
        Operation.NATIVE_EXECUTION,
        Operation.FORMAL_EXECUTION,
        Operation.FUZZ_EXECUTION,
    }:
        arguments = {"iterations": 1} if operation is Operation.FUZZ_EXECUTION else {}
        return {
            "plan": {
                "adapterId": "unconfigured-trusted-adapter",
                "action": "bounded-operation",
                "arguments": arguments,
            }
        }
    if operation is Operation.GATE_EVALUATION:
        return {
            "dependencyEvidence": {
                dependency: _evidence(
                    scope, EvidenceStatus.LOCAL_EXECUTED_SELF_ATTESTED.value
                )
                for dependency in binding.dependencies
            },
            "routeProfile": {
                "profileDigest": scope["semanticProfileDigest"],
                "source": "trusted-host",
            },
        }
    if operation is Operation.CACHE_INVALIDATION:
        return {
            "cacheIdentity": {
                "formulaDigest": _sha("9"),
                "semanticModelDigest": _sha("a"),
                "assumptionsDigest": scope["assumptionsDigest"],
                "toolchainDigest": scope["toolchainDigest"],
                "sourceDigest": scope["sourceDigest"],
                "targetDigest": scope["targetDigest"],
                "environmentDigest": scope["environmentDigest"],
                "corpusDigest": scope["corpusDigest"],
            },
            "result": {"status": "NOT_RUN"},
        }
    if operation is Operation.COUNTEREXAMPLE_REPLAY:
        source_trace = {"stdout": "source", "exitCode": 0}
        target_trace = {"stdout": "target", "exitCode": 0}
        return {
            "counterexample": {
                "id": "counterexample-registry",
                "sourceTraceDigest": digest_value(source_trace),
                "targetTraceDigest": digest_value(target_trace),
            },
            "replay": {
                "sourceTrace": source_trace,
                "targetTrace": target_trace,
            },
        }
    raise AssertionError(f"test payload missing for operation {operation}")


def _request(
    binding: SkillBinding,
    *,
    idempotency_key: str | None = None,
    scope: dict[str, str] | None = None,
) -> dict[str, Any]:
    scope_value = scope or _scope_document()
    return {
        "schemaVersion": "1.0",
        "subjectId": f"subject-{binding.source_skill_id.lower()}",
        "idempotencyKey": idempotency_key
        or f"idem-{binding.source_skill_id.lower()}",
        "scope": scope_value,
        "payload": _payload(binding, scope_value),
        "allowedEffects": ["artifact-write"],
    }


class TestRegistryRuntime(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = SkillRegistry()
        self.store = SemanticAssuranceStore()
        self.runtime = SemanticAssuranceRuntime(registry=self.registry, store=self.store)
        self.addCleanup(self.store.close)

    def test_compiled_registry_has_132_exact_non_generic_bindings(self) -> None:
        records = self.registry.list()
        self.assertEqual(self.registry.count, 132)
        self.assertEqual(len(records), 132)
        self.assertEqual(Counter(record["batch"] for record in records), EXPECTED_BATCH_COUNTS)
        self.assertEqual(len({record["sourceSkillId"] for record in records}), 132)
        self.assertEqual(len({record["sourceName"] for record in records}), 132)
        self.assertEqual(len({record["installedName"] for record in records}), 132)
        self.assertEqual(len({record["handlerId"] for record in records}), 132)
        self.assertEqual(
            {record["operation"] for record in records},
            {operation.value for operation in Operation},
        )
        self.assertTrue(all(record["risk"] == "critical" for record in records))
        self.assertTrue(all(record["implementationState"] == "RUNTIME_CODE_COMPLETE" for record in records))
        self.assertTrue(all(record["externalEvidenceStatus"] == "NOT_RUN" for record in records))
        self.assertTrue(all(record["certificationStatus"] == "NOT_CERTIFIED" for record in records))
        self.assertEqual(
            tuple(sorted(record["installedName"] for record in records)),
            self.runtime.handler_names,
        )
        self.assertEqual(len(self.runtime.handler_names), 132)
        self.assertTrue(all(record["operation"] != "GENERIC" for record in records))

    def test_registry_capability_mapping_is_conservative(self) -> None:
        for record in self.registry.list():
            operation = Operation(record["operation"])
            capability = CapabilityState(record["capabilityState"])
            if operation in {
                Operation.NATIVE_EXECUTION,
                Operation.FORMAL_EXECUTION,
                Operation.FUZZ_EXECUTION,
            }:
                self.assertIs(capability, CapabilityState.CODE_COMPLETE_ADAPTER_REQUIRED)
            elif operation is Operation.GATE_EVALUATION:
                self.assertIs(capability, CapabilityState.CODE_COMPLETE_EXTERNAL_GATE_REQUIRED)
            else:
                self.assertIs(capability, CapabilityState.CODE_COMPLETE_LOCAL_BOUNDED)

    def test_unknown_registry_and_runtime_names_fail_without_fallback(self) -> None:
        with self.assertRaisesRegex(KeyError, "unknown semantic-assurance Skill"):
            self.registry.get("elmos-does-not-exist")
        with self.assertRaisesRegex(KeyError, "unknown installed semantic-assurance Skill"):
            self.runtime.dispatch("elmos-does-not-exist", {}, _identity())

    def test_collision_aliases_dispatch_incoming_bindings_without_owning_original_names(self) -> None:
        for source_name, alias in COLLISION_ALIASES.items():
            with self.subTest(source_name=source_name, alias=alias):
                binding = self.registry.get(source_name)
                self.assertEqual(binding.installed_name, alias)
                self.assertIn(alias, self.runtime.handler_names)
                self.assertNotIn(source_name, self.runtime.handler_names)

                response = self.runtime.dispatch(alias, _request(binding), _identity())
                self.assertEqual(response["skillName"], source_name)
                self.assertEqual(response["installedName"], alias)
                self.assertEqual(response["handlerId"], binding.handler_id)
                self.assertEqual(response["certificationStatus"], "NOT_CERTIFIED")

                with self.assertRaisesRegex(KeyError, "unknown installed semantic-assurance Skill"):
                    self.runtime.dispatch(source_name, _request(binding), _identity())

    def test_all_132_installed_names_dispatch_exact_operation_without_external_runtime(self) -> None:
        identity = _identity()
        responses: list[dict[str, Any]] = []
        for record in self.registry.list():
            binding = self.registry.get(record["sourceName"])
            response = self.runtime.dispatch(
                binding.installed_name,
                _request(binding),
                identity,
            )
            responses.append(response)
            self.assertEqual(response["sourceSkillId"], binding.source_skill_id)
            self.assertEqual(response["skillName"], binding.source_name)
            self.assertEqual(response["installedName"], binding.installed_name)
            self.assertEqual(response["handlerId"], binding.handler_id)
            self.assertEqual(response["operation"], binding.operation.value)
            self.assertEqual(response["trustedActorId"], identity.actor_id)
            self.assertEqual(response["certificationStatus"], "NOT_CERTIFIED")
            self.assertEqual(response["externalEvidenceStatus"], "NOT_RUN")
            self.assertEqual(len(response["artifacts"]), 3)
            if binding.operation in {
                Operation.NATIVE_EXECUTION,
                Operation.FORMAL_EXECUTION,
                Operation.FUZZ_EXECUTION,
            }:
                self.assertEqual(response["executionStatus"], "REQUIRES_ADAPTER")
                self.assertEqual(response["evidenceStatus"], "NOT_RUN")
            if binding.operation is Operation.GATE_EVALUATION:
                self.assertEqual(response["result"]["readiness"], "READY_FOR_EXTERNAL_GATE")
                self.assertEqual(response["result"]["certification"], "NOT_CERTIFIED")

        self.assertEqual(len(responses), 132)
        self.assertEqual(len({response["handlerId"] for response in responses}), 132)
        registry_scope = _assurance_scope()
        chain = self.runtime.store.verify_event_chain(registry_scope)
        self.assertEqual(registry_scope.run_id, "run-registry")
        self.assertTrue(chain["verified"])
        self.assertEqual(chain["eventCount"], 132)

    def test_runtime_role_scope_actor_and_idempotency_are_bound(self) -> None:
        binding = next(
            self.registry.get(record["sourceName"])
            for record in self.registry.list()
            if record["operation"] == Operation.MODEL_NORMALIZATION.value
        )
        document = _request(binding, idempotency_key="idem-runtime-replay")
        identity = _identity(actor="actor-a")

        first = self.runtime.dispatch(binding.installed_name, document, identity)
        replay = self.runtime.dispatch(binding.installed_name, deepcopy(document), identity)
        self.assertEqual(replay, first)
        self.assertEqual(first["trustedActorId"], "actor-a")

        with self.assertRaisesRegex(AuthorizationError, "required role"):
            self.runtime.dispatch(
                binding.installed_name,
                _request(binding, idempotency_key="idem-no-role"),
                _identity(roles=("viewer",)),
            )

        identity_without_authorization = TrustedIdentity(
            tenant_id="tenant-a",
            project_id="project-a",
            actor_id="actor-a",
            roles=(EXECUTE_ROLE,),
            authorization_ref=None,
        )
        with self.assertRaisesRegex(AuthorizationError, "authorization reference"):
            self.runtime.dispatch(
                binding.installed_name,
                _request(binding, idempotency_key="idem-no-authorization"),
                identity_without_authorization,
            )

        missing_effect = _request(binding, idempotency_key="idem-no-effect")
        missing_effect["allowedEffects"] = []
        with self.assertRaisesRegex(AuthorizationError, "artifact-write"):
            self.runtime.dispatch(binding.installed_name, missing_effect, identity)

        wrong_scope = _request(binding, idempotency_key="idem-wrong-scope")
        wrong_scope["scope"]["projectId"] = "project-b"
        with self.assertRaisesRegex(PermissionError, "trusted identity"):
            self.runtime.dispatch(binding.installed_name, wrong_scope, identity)

        changed_payload = deepcopy(document)
        changed_payload["payload"]["items"][0]["kind"] = "different-kind"
        with self.assertRaises(IdempotencyConflict):
            self.runtime.dispatch(binding.installed_name, changed_payload, identity)

        with self.assertRaises(IdempotencyConflict):
            self.runtime.dispatch(
                binding.installed_name,
                deepcopy(document),
                _identity(actor="actor-b"),
            )

    def test_runtime_status_never_claims_external_evidence_or_certification(self) -> None:
        status = self.runtime.status().to_dict()
        self.assertEqual(status["registeredSkills"], 132)
        self.assertEqual(status["exactHandlers"], 132)
        self.assertEqual(status["implementationState"], "RUNTIME_CODE_COMPLETE")
        self.assertEqual(status["externalEvidenceStatus"], "NOT_RUN")
        self.assertEqual(status["certificationStatus"], "NOT_CERTIFIED")
        self.assertEqual(status["readiness"], "BLOCKED_EXTERNAL_EVIDENCE_REQUIRED")


if __name__ == "__main__":
    unittest.main()
