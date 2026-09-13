"""Positive, negative and boundary tests for all twelve bounded operations."""

from __future__ import annotations

import unittest
from dataclasses import replace
from typing import Any

from elmos_semantic_assurance.adapters import AdapterError, AdapterReceipt
from elmos_semantic_assurance.canonical import digest_value
from elmos_semantic_assurance.contracts import (
    CapabilityState,
    EvidenceStatus,
    ExecutionStatus,
    Operation,
    SkillRequest,
    TrustedIdentity,
)
from elmos_semantic_assurance.handlers import (
    OPERATION_HANDLERS,
    HandlerContext,
    HandlerError,
    execute_binding,
)
from elmos_semantic_assurance.registry import COLLISION_ALIASES, SkillBinding
from elmos_semantic_assurance.store import SemanticAssuranceStore


def _sha(character: str) -> str:
    return "sha256:" + character * 64


def _scope_document() -> dict[str, str]:
    return {
        "tenantId": "tenant-a",
        "projectId": "project-a",
        "runId": "run-operations",
        "snapshotId": "snapshot-operations",
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


def _capability(operation: Operation) -> CapabilityState:
    if operation in {
        Operation.NATIVE_EXECUTION,
        Operation.FORMAL_EXECUTION,
        Operation.FUZZ_EXECUTION,
    }:
        return CapabilityState.CODE_COMPLETE_ADAPTER_REQUIRED
    if operation is Operation.GATE_EVALUATION:
        return CapabilityState.CODE_COMPLETE_EXTERNAL_GATE_REQUIRED
    return CapabilityState.CODE_COMPLETE_LOCAL_BOUNDED


def _context(
    operation: Operation,
    payload: dict[str, Any],
    store: SemanticAssuranceStore,
    *,
    dependencies: tuple[str, ...] = (),
    actor_id: str = "actor-a",
    source_name: str | None = None,
) -> HandlerContext:
    name = source_name or f"elmos-test-{operation.value.lower().replace('_', '-')}"
    identity = TrustedIdentity(
        tenant_id="tenant-a",
        project_id="project-a",
        actor_id=actor_id,
        roles=("semantic-assurance-runner",),
        authorization_ref="authorization-001",
    )
    document = {
        "schemaVersion": "1.0",
        "subjectId": "subject-operations",
        "idempotencyKey": f"idem-{operation.value.lower().replace('_', '-')}",
        "scope": _scope_document(),
        "payload": payload,
        "allowedEffects": ["artifact-write"],
    }
    request = SkillRequest.parse(document, identity)
    binding = SkillBinding(
        source_skill_id="ELMOS-POLY-169",
        source_name=name,
        installed_name=COLLISION_ALIASES.get(name, name),
        batch="J",
        layer="test",
        risk="critical",
        description="Test-only exact operation binding for production negative controls.",
        dependencies=dependencies,
        outputs=(
            f"semantic-assurance/{name}/model.json",
            f"semantic-assurance/{name}/evidence.json",
            f"semantic-assurance/{name}/diagnostics.json",
        ),
        handler_id=f"execute_{name.replace('-', '_')}",
        operation=operation,
        capability_state=_capability(operation),
    )
    request_digest = digest_value(request.to_digest_document(name))
    return HandlerContext(binding, request, identity, request_digest, store)


def _matching_evidence(ctx: HandlerContext, state: str) -> dict[str, Any]:
    scope = ctx.request.scope
    return {
        "state": state,
        "subjectDigest": scope.source_digest,
        "snapshotDigest": scope.snapshot_digest,
        "environmentDigest": scope.environment_digest,
        "toolchainDigest": scope.toolchain_digest,
        "corpusDigest": scope.corpus_digest,
        "assumptionsDigest": scope.assumptions_digest,
        "executorId": "executor-a",
    }


class _BoundedAdapter:
    adapter_id = "trusted-adapter-001"
    supported_actions = frozenset({"execute-bounded-plan"})

    def __init__(
        self,
        status: str,
        *,
        forge_request_digest: bool = False,
        forge_evidence_digest: bool = False,
    ) -> None:
        self.status = status
        self.forge_request_digest = forge_request_digest
        self.forge_evidence_digest = forge_evidence_digest
        self.calls = 0

    def execute(self, plan, scope) -> AdapterReceipt:
        self.calls += 1
        output = {"boundedObservation": True}
        return AdapterReceipt(
            adapter_id=self.adapter_id,
            execution_id=f"execution-{self.calls}",
            request_digest=(
                _sha("f") if self.forge_request_digest else digest_value(plan)
            ),
            scope_digest=digest_value(scope.to_dict()),
            status=self.status,
            evidence_digest=(
                _sha("e")
                if self.forge_evidence_digest
                else digest_value(output)
            ),
            executor_id="executor-a",
            output=output,
        )


class TestOperationHandlers(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SemanticAssuranceStore()
        self.addCleanup(self.store.close)

    def test_operation_handler_table_is_exact_and_has_no_generic_fallback(self) -> None:
        self.assertEqual(len(Operation), 12)
        self.assertEqual(set(OPERATION_HANDLERS), set(Operation))
        self.assertTrue(all(callable(handler) for handler in OPERATION_HANDLERS.values()))
        self.assertNotIn("GENERIC", {operation.value for operation in Operation})

    def test_collision_aliases_preserve_both_incoming_identities(self) -> None:
        self.assertEqual(
            COLLISION_ALIASES,
            {
                "elmos-proof-obligation-generator": (
                    "elmos-semantic-assurance-proof-obligation-generator"
                ),
                "elmos-proof-cache-invalidation": (
                    "elmos-semantic-assurance-proof-cache-invalidation"
                ),
            },
        )

    def test_model_normalization_preserves_provenance_and_blocks_unknowns(self) -> None:
        item = {
            "id": "node-a",
            "kind": "integer-type",
            "state": "KNOWN",
            "sourceSpan": {"artifactDigest": _sha("2"), "start": 0, "end": 8},
            "semantics": {"bits": 32, "signed": True},
            "provenance": {"parser": "trusted-java-parser"},
        }
        outcome, artifacts = execute_binding(
            _context(Operation.MODEL_NORMALIZATION, {"items": [item]}, self.store)
        )

        self.assertIs(outcome.execution_status, ExecutionStatus.LOCAL_EXECUTED)
        self.assertEqual(outcome.result["readiness"], "LOCAL_MODEL_READY")
        self.assertEqual(outcome.result["items"][0]["sourceSpan"]["artifactDigest"], _sha("2"))
        self.assertEqual(len(artifacts), 3)

        uncertain = {**item, "state": "UNSUPPORTED"}
        blocked, _ = execute_binding(
            _context(Operation.MODEL_NORMALIZATION, {"items": [uncertain]}, self.store)
        )
        self.assertIs(blocked.execution_status, ExecutionStatus.BLOCKED)
        self.assertIs(blocked.evidence_status, EvidenceStatus.INCONCLUSIVE)
        self.assertEqual(blocked.result["blockingItemIds"], ["node-a"])

    def test_model_normalization_rejects_duplicate_identity(self) -> None:
        item = {
            "id": "node-a",
            "kind": "integer-type",
            "sourceSpan": {"artifactDigest": _sha("2"), "start": 0, "end": 1},
        }
        with self.assertRaisesRegex(HandlerError, "duplicate identifier"):
            execute_binding(
                _context(Operation.MODEL_NORMALIZATION, {"items": [item, item]}, self.store)
            )

    def test_semantic_comparison_emits_bounded_match_or_counterexample(self) -> None:
        match, _ = execute_binding(
            _context(
                Operation.SEMANTIC_COMPARISON,
                {"source": {"value": 1}, "target": {"value": 1}, "relation": "EXACT"},
                self.store,
            )
        )
        self.assertEqual(match.result["verdict"], "MATCH_WITHIN_DECLARED_SCOPE")
        self.assertFalse(match.result["universalEquivalenceClaimed"])

        mismatch, _ = execute_binding(
            _context(
                Operation.SEMANTIC_COMPARISON,
                {"source": {"value": 1}, "target": {"value": 2}, "relation": "EXACT"},
                self.store,
            )
        )
        self.assertIs(mismatch.evidence_status, EvidenceStatus.COUNTEREXAMPLE)
        self.assertEqual(mismatch.result["verdict"], "MISMATCH")
        self.assertTrue(mismatch.result["counterexampleDigest"].startswith("sha256:"))

    def test_semantic_comparison_rejects_unbounded_observable_paths(self) -> None:
        paths = [f"/path-{index}" for index in range(257)]
        with self.assertRaisesRegex(HandlerError, "exceeds 256"):
            execute_binding(
                _context(
                    Operation.SEMANTIC_COMPARISON,
                    {
                        "source": {},
                        "target": {},
                        "relation": "OBSERVATIONAL",
                        "observablePaths": paths,
                    },
                    self.store,
                )
            )

    def test_graph_analysis_validates_edges_and_required_shape(self) -> None:
        graph = {
            "nodes": [
                {"id": "entry", "entry": True},
                {"id": "exit", "exit": True},
            ],
            "edges": [{"from": "entry", "to": "exit", "kind": "flow"}],
        }
        valid, _ = execute_binding(
            _context(
                Operation.GRAPH_ANALYSIS,
                {
                    "graph": graph,
                    "acyclicRequired": True,
                    "singleEntryRequired": True,
                    "exitRequired": True,
                },
                self.store,
            )
        )
        self.assertEqual(valid.result["verdict"], "VALID_WITHIN_DECLARED_RULES")

        graph["edges"].append({"from": "entry", "to": "missing", "kind": "flow"})
        invalid, _ = execute_binding(
            _context(Operation.GRAPH_ANALYSIS, {"graph": graph}, self.store)
        )
        self.assertEqual(invalid.result["verdict"], "MALFORMED")
        self.assertIs(invalid.evidence_status, EvidenceStatus.COUNTEREXAMPLE)

    def test_coverage_analysis_uses_explicit_nonzero_denominators(self) -> None:
        outcome, _ = execute_binding(
            _context(
                Operation.COVERAGE_ANALYSIS,
                {
                    "dimensions": [
                        {
                            "id": "syntax-features",
                            "numerator": 9,
                            "denominator": 10,
                            "thresholdNumerator": 9,
                            "thresholdDenominator": 10,
                        }
                    ]
                },
                self.store,
            )
        )
        self.assertEqual(outcome.result["verdict"], "LOCAL_THRESHOLD_MET")
        self.assertFalse(outcome.result["certifiable"])

        blocked, _ = execute_binding(
            _context(Operation.COVERAGE_ANALYSIS, {"dimensions": []}, self.store)
        )
        self.assertIs(blocked.execution_status, ExecutionStatus.BLOCKED)

        with self.assertRaisesRegex(HandlerError, "outside denominator"):
            execute_binding(
                _context(
                    Operation.COVERAGE_ANALYSIS,
                    {
                        "dimensions": [
                            {"id": "invalid", "numerator": 2, "denominator": 1}
                        ]
                    },
                    self.store,
                )
            )

    def test_corpus_governance_enforces_provenance_and_partition_independence(self) -> None:
        fixture = {
            "id": "fixture-development",
            "contentDigest": _sha("a"),
            "partition": "development",
            "license": {
                "spdx": "Apache-2.0",
                "reviewStatus": "APPROVED",
                "provenanceDigest": _sha("b"),
            },
        }
        valid, _ = execute_binding(
            _context(Operation.CORPUS_GOVERNANCE, {"fixtures": [fixture]}, self.store)
        )
        self.assertEqual(valid.result["verdict"], "LOCAL_CORPUS_REGISTERED")
        self.assertEqual(valid.result["externalCorpusEvidence"], "NOT_RUN")

        leaked = {
            **fixture,
            "id": "fixture-holdout",
            "partition": "holdout",
        }
        blocked, _ = execute_binding(
            _context(
                Operation.CORPUS_GOVERNANCE,
                {"fixtures": [fixture, leaked]},
                self.store,
            )
        )
        self.assertIs(blocked.execution_status, ExecutionStatus.BLOCKED)
        self.assertEqual(blocked.result["crossPartitionDuplicateDigests"], [_sha("a")])

    def test_evidence_validation_rejects_not_run_stale_and_self_verified(self) -> None:
        base_ctx = _context(Operation.EVIDENCE_VALIDATION, {"evidence": []}, self.store)
        not_run = _matching_evidence(base_ctx, EvidenceStatus.NOT_RUN.value)
        blocked, _ = execute_binding(
            replace(base_ctx, request=replace(base_ctx.request, payload={"evidence": [not_run]}))
        )
        self.assertIs(blocked.execution_status, ExecutionStatus.BLOCKED)
        self.assertTrue(
            any(
                item["reason"] == "non-success-evidence-state"
                for item in blocked.result["blockers"]
            )
        )

        stale = _matching_evidence(base_ctx, EvidenceStatus.LOCAL_EXECUTED_SELF_ATTESTED.value)
        stale["toolchainDigest"] = _sha("f")
        stale_outcome, _ = execute_binding(
            replace(base_ctx, request=replace(base_ctx.request, payload={"evidence": [stale]}))
        )
        self.assertIs(stale_outcome.execution_status, ExecutionStatus.BLOCKED)

        self_verified = _matching_evidence(base_ctx, EvidenceStatus.INDEPENDENTLY_VERIFIED.value)
        self_verified.update(
            verifierId="executor-a",
            signed=True,
            trustStoreDigest=_sha("d"),
            revocationChecked=True,
        )
        self_outcome, _ = execute_binding(
            replace(
                base_ctx,
                request=replace(base_ctx.request, payload={"evidence": [self_verified]}),
            )
        )
        self.assertIs(self_outcome.execution_status, ExecutionStatus.BLOCKED)
        self.assertTrue(
            any(
                item["reason"] == "independent-verifier-missing"
                for item in self_outcome.result["blockers"]
            )
        )

    def test_native_formal_and_fuzz_never_simulate_success_without_adapter(self) -> None:
        for operation in [Operation.NATIVE_EXECUTION, Operation.FORMAL_EXECUTION, Operation.FUZZ_EXECUTION]:
            with self.subTest(operation=operation):
                arguments = {"iterations": 10} if operation is Operation.FUZZ_EXECUTION else {}
                outcome, _ = execute_binding(
                    _context(
                        operation,
                        {
                            "plan": {
                                "adapterId": "trusted-adapter-001",
                                "action": "execute-bounded-plan",
                                "arguments": arguments,
                            }
                        },
                        self.store,
                    )
                )

                self.assertIs(outcome.execution_status, ExecutionStatus.REQUIRES_ADAPTER)
                self.assertIs(outcome.evidence_status, EvidenceStatus.NOT_RUN)
                self.assertEqual(outcome.result["verdict"], "REQUIRES_ADAPTER")
                self.assertEqual(outcome.certification_status, "NOT_CERTIFIED")

    def test_execution_plan_rejects_authority_and_fuzz_bounds(self) -> None:
        with self.assertRaisesRegex(HandlerError, "forbidden authority fields"):
            execute_binding(
                _context(
                    Operation.NATIVE_EXECUTION,
                    {
                        "plan": {
                            "adapterId": "trusted-adapter-001",
                            "action": "compile",
                            "arguments": {},
                            "command": "sh -c arbitrary",
                        }
                    },
                    self.store,
                )
            )

        with self.assertRaisesRegex(HandlerError, "forbidden authority fields"):
            execute_binding(
                _context(
                    Operation.FORMAL_EXECUTION,
                    {
                        "plan": {
                            "adapterId": "trusted-adapter-001",
                            "action": "prove",
                            "arguments": {"shell": "sh", "command": "arbitrary"},
                        }
                    },
                    self.store,
                )
            )

        with self.assertRaisesRegex(HandlerError, r"between 1 and 1,000,000"):
            execute_binding(
                _context(
                    Operation.FUZZ_EXECUTION,
                    {
                        "plan": {
                            "adapterId": "trusted-adapter-001",
                            "action": "fuzz",
                            "arguments": {"iterations": 0},
                        }
                    },
                    self.store,
                )
            )

    def test_adapter_action_allowlist_and_receipt_binding_fail_closed(self) -> None:
        payload = {
            "plan": {
                "adapterId": "trusted-adapter-001",
                "action": "execute-bounded-plan",
                "arguments": {},
            }
        }
        context = _context(Operation.NATIVE_EXECUTION, payload, self.store)
        adapter = _BoundedAdapter("UNKNOWN")
        outcome, _ = execute_binding(replace(context, adapter=adapter))
        self.assertEqual(adapter.calls, 1)
        self.assertIs(outcome.execution_status, ExecutionStatus.BLOCKED)
        self.assertIs(outcome.evidence_status, EvidenceStatus.INCONCLUSIVE)
        self.assertEqual(outcome.result["verdict"], "UNKNOWN")

        unsupported = _context(
            Operation.NATIVE_EXECUTION,
            {
                "plan": {
                    "adapterId": "trusted-adapter-001",
                    "action": "unapproved-action",
                    "arguments": {},
                }
            },
            self.store,
        )
        with self.assertRaisesRegex(HandlerError, "does not allow"):
            execute_binding(replace(unsupported, adapter=adapter))
        self.assertEqual(adapter.calls, 1)

        forged = _BoundedAdapter("PASS", forge_request_digest=True)
        with self.assertRaisesRegex(HandlerError, "request digest mismatch"):
            execute_binding(replace(context, adapter=forged))

        forged_evidence = _BoundedAdapter("PASS", forge_evidence_digest=True)
        with self.assertRaisesRegex(HandlerError, "evidence digest mismatch"):
            execute_binding(replace(context, adapter=forged_evidence))

    def test_explicit_adapter_pass_remains_local_and_not_certified(self) -> None:
        context = _context(
            Operation.FORMAL_EXECUTION,
            {
                "plan": {
                    "adapterId": "trusted-adapter-001",
                    "action": "execute-bounded-plan",
                    "arguments": {"obligationId": "obligation-001"},
                }
            },
            self.store,
        )
        outcome, _ = execute_binding(replace(context, adapter=_BoundedAdapter("PASS")))

        self.assertIs(outcome.execution_status, ExecutionStatus.LOCAL_EXECUTED)
        self.assertIs(outcome.evidence_status, EvidenceStatus.LOCAL_EXECUTED_SELF_ATTESTED)
        self.assertFalse(outcome.result["independentEvidenceClaimed"])
        self.assertEqual(outcome.certification_status, "NOT_CERTIFIED")
        self.assertEqual(outcome.external_evidence_status, "NOT_RUN")

    def test_adapter_receipt_rejects_self_verification(self) -> None:
        with self.assertRaisesRegex(AdapterError, "must be independent"):
            AdapterReceipt(
                adapter_id="trusted-adapter-001",
                execution_id="execution-001",
                request_digest=_sha("1"),
                scope_digest=_sha("2"),
                status="PASS",
                evidence_digest=_sha("3"),
                executor_id="same-party",
                verifier_id="same-party",
                signed=True,
                output={},
            )

    def test_gate_blocks_not_run_unknown_and_self_verified_evidence(self) -> None:
        dependency = "elmos-required-dependency"
        seed = _context(
            Operation.GATE_EVALUATION,
            {"dependencyEvidence": {}},
            self.store,
            dependencies=(dependency,),
        )

        for state in (EvidenceStatus.NOT_RUN.value, EvidenceStatus.INCONCLUSIVE.value):
            with self.subTest(state=state):
                evidence = _matching_evidence(seed, state)
                request = replace(
                    seed.request,
                    payload={
                        "dependencyEvidence": {dependency: evidence},
                        "routeProfile": {
                            "profileDigest": seed.request.scope.semantic_profile_digest,
                            "source": "trusted-host",
                        },
                    },
                )
                outcome, _ = execute_binding(replace(seed, request=request))
                self.assertIs(outcome.execution_status, ExecutionStatus.BLOCKED)
                self.assertEqual(outcome.result["readiness"], "BLOCKED")

        unknown = _matching_evidence(seed, EvidenceStatus.NOT_RUN.value)
        unknown["state"] = "UNKNOWN"
        with self.assertRaisesRegex(HandlerError, "state is invalid"):
            execute_binding(
                replace(
                    seed,
                    request=replace(
                        seed.request,
                        payload={
                            "dependencyEvidence": {dependency: unknown},
                            "routeProfile": {
                                "profileDigest": seed.request.scope.semantic_profile_digest,
                                "source": "trusted-host",
                            },
                        },
                    ),
                )
            )

        self_verified = _matching_evidence(seed, EvidenceStatus.INDEPENDENTLY_VERIFIED.value)
        self_verified.update(
            verifierId="executor-a",
            signed=True,
            trustStoreDigest=_sha("d"),
            revocationChecked=True,
        )
        self_outcome, _ = execute_binding(
            replace(
                seed,
                request=replace(
                    seed.request,
                    payload={
                        "dependencyEvidence": {dependency: self_verified},
                        "routeProfile": {
                            "profileDigest": seed.request.scope.semantic_profile_digest,
                            "source": "trusted-host",
                        },
                    },
                ),
            )
        )
        self.assertIs(self_outcome.execution_status, ExecutionStatus.BLOCKED)

    def test_gate_maximum_is_ready_for_external_gate_and_not_certified(self) -> None:
        dependency = "elmos-required-dependency"
        seed = _context(
            Operation.GATE_EVALUATION,
            {"dependencyEvidence": {}},
            self.store,
            dependencies=(dependency,),
        )
        evidence = _matching_evidence(
            seed, EvidenceStatus.LOCAL_EXECUTED_SELF_ATTESTED.value
        )
        request = replace(
            seed.request,
            payload={
                "dependencyEvidence": {dependency: evidence},
                "routeProfile": {
                    "profileDigest": seed.request.scope.semantic_profile_digest,
                    "source": "trusted-host",
                },
            },
        )
        outcome, _ = execute_binding(replace(seed, request=request))
        serialized = outcome.to_dict()

        self.assertEqual(outcome.result["readiness"], "READY_FOR_EXTERNAL_GATE")
        self.assertEqual(outcome.result["certification"], "NOT_CERTIFIED")
        self.assertEqual(serialized["certificationStatus"], "NOT_CERTIFIED")
        self.assertEqual(serialized["externalEvidenceStatus"], "NOT_RUN")
        self.assertNotEqual(serialized["certificationStatus"], "CERTIFIED")
        self.assertNotEqual(outcome.result["certification"], "CERTIFIED")

    def test_cache_identity_binds_all_semantic_dependencies(self) -> None:
        identity = {
            "formulaDigest": _sha("9"),
            "semanticModelDigest": _sha("a"),
            "assumptionsDigest": _sha("8"),
            "toolchainDigest": _sha("6"),
            "sourceDigest": _sha("2"),
            "targetDigest": _sha("3"),
            "environmentDigest": _sha("4"),
            "corpusDigest": _sha("7"),
        }
        outcome, _ = execute_binding(
            _context(
                Operation.CACHE_INVALIDATION,
                {"cacheIdentity": identity, "result": {"status": "NOT_RUN"}},
                self.store,
                source_name="elmos-proof-cache-invalidation",
            )
        )
        self.assertTrue(outcome.result["fullSemanticIdentityBound"])
        self.assertFalse(outcome.result["registration"]["stale"])

        mismatched = {**identity, "assumptionsDigest": _sha("f")}
        blocked, _ = execute_binding(
            _context(
                Operation.CACHE_INVALIDATION,
                {"cacheIdentity": mismatched},
                self.store,
                source_name="elmos-proof-cache-invalidation",
            )
        )
        self.assertIs(blocked.execution_status, ExecutionStatus.BLOCKED)
        self.assertEqual(blocked.result["mismatchedFields"], ["assumptionsDigest"])

    def test_counterexample_replay_never_converts_counterexample_to_success(self) -> None:
        source_trace = {"stdout": "source", "exitCode": 0}
        target_trace = {"stdout": "target", "exitCode": 0}
        counterexample = {
            "id": "counterexample-001",
            "sourceTraceDigest": digest_value(source_trace),
            "targetTraceDigest": digest_value(target_trace),
        }
        reproduced, _ = execute_binding(
            _context(
                Operation.COUNTEREXAMPLE_REPLAY,
                {
                    "counterexample": counterexample,
                    "replay": {
                        "sourceTrace": source_trace,
                        "targetTrace": target_trace,
                    },
                },
                self.store,
            )
        )
        self.assertTrue(reproduced.result["reproduced"])
        self.assertIs(reproduced.evidence_status, EvidenceStatus.COUNTEREXAMPLE)
        self.assertEqual(reproduced.certification_status, "NOT_CERTIFIED")

        not_reproduced, _ = execute_binding(
            _context(
                Operation.COUNTEREXAMPLE_REPLAY,
                {
                    "counterexample": counterexample,
                    "replay": {
                        "sourceTrace": source_trace,
                        "targetTrace": {"stdout": "different", "exitCode": 0},
                    },
                },
                self.store,
            )
        )
        self.assertIs(not_reproduced.execution_status, ExecutionStatus.BLOCKED)
        self.assertIs(not_reproduced.evidence_status, EvidenceStatus.INCONCLUSIVE)

    def test_artifact_provenance_binds_actor_identity(self) -> None:
        payload = {
            "items": [
                {
                    "id": "node-a",
                    "kind": "integer-type",
                    "sourceSpan": {
                        "artifactDigest": _sha("2"),
                        "start": 0,
                        "end": 1,
                    },
                }
            ]
        }
        _, actor_a_artifacts = execute_binding(
            _context(Operation.MODEL_NORMALIZATION, payload, self.store, actor_id="actor-a")
        )
        _, actor_b_artifacts = execute_binding(
            _context(Operation.MODEL_NORMALIZATION, payload, self.store, actor_id="actor-b")
        )

        self.assertEqual(actor_a_artifacts[0][1]["producer"]["actorId"], "actor-a")
        self.assertEqual(actor_b_artifacts[0][1]["producer"]["actorId"], "actor-b")
        self.assertNotEqual(actor_a_artifacts[0][0].content_digest, actor_b_artifacts[0][0].content_digest)


if __name__ == "__main__":
    unittest.main()
