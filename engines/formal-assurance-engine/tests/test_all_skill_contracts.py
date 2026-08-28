from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from elmos_formal_assurance.canonical import digest_value
from elmos_formal_assurance.contracts import TrustedIdentity
from elmos_formal_assurance.runtime import FormalAssuranceRuntime, RuntimeConfig
from elmos_formal_assurance.store import StateStore


def scope() -> dict[str, object]:
    return {
        "tenantId": "tenant-a",
        "accountId": "account-a",
        "projectId": "project-a",
        "sourceArtifactDigest": "a" * 64,
        "targetArtifactDigest": "b" * 64,
        "environmentDigest": "c" * 64,
        "workloadKey": "all-skill-contracts",
    }


def obligation(identifier: str = "obl-a") -> dict[str, object]:
    formula = "x = x"
    return {
        "id": identifier,
        "criticality": "P2",
        "propertyKind": "FUNCTIONAL_CORRECTNESS",
        "requiredAssurance": "A1_BOUNDED",
        "formula": formula,
        "formulaHash": digest_value(formula),
        "allowBounded": True,
    }


def fixtures() -> dict[str, dict[str, object]]:
    workflow = {
        "states": ["done"],
        "transitions": [],
        "initial": "done",
        "terminalStates": ["done"],
    }
    schema = {"sourceColumns": [], "targetColumns": []}
    trace = {"sourceTrace": [], "targetTrace": []}
    return {
        "elmos-api-contract-verifier": {"sourceOperations": [], "targetOperations": []},
        "elmos-architecture-constraint-checker": {"edges": []},
        "elmos-assumption-ledger": {"assumptions": []},
        "elmos-counterexample-to-test": {
            "counterexample": {
                "id": "cex-all",
                "obligationId": "obl-all",
                "kind": "INPUT",
                "witness": {"value": 1},
                "violatedProperty": "value remains valid",
                "replay": {"command": "pytest -k cex_all"},
            }
        },
        "elmos-credit-billing-invariant-model": {"ledgerEvents": []},
        "elmos-cross-language-product-program": {
            "sourceProgram": {"inputs": []},
            "targetProgram": {"inputs": []},
        },
        "elmos-data-invariant-verifier": {"facts": {"balance": 0}},
        "elmos-ddl-constraint-preservation": dict(schema),
        "elmos-dml-state-equivalence": {
            "beforeRows": [],
            "afterRows": [],
            "sourceEffect": "none",
            "targetEffect": "none",
        },
        "elmos-dynamic-sql-proof-boundary": {"templates": [], "enumerationBound": 1},
        "elmos-effect-exception-trace-refinement": dict(trace),
        "elmos-formal-assurance-orchestrator": {
            "action": "submit",
            "runId": "run-all",
            "obligationId": "obl-run-all",
        },
        "elmos-formal-assurance-report": {"outcomes": []},
        "elmos-formal-release-gate": {
            "obligations": [],
            "results": [],
            "requiredGate": "E2_MODEL",
        },
        "elmos-formal-spec-ir": {
            "formalSpec": {
                "id": "spec-all",
                "tenant": {"tenantId": "tenant-a", "accountId": "account-a"},
                "businessLine": "core",
                "specKind": "FUNCTION",
                "version": "1.0.0",
                "sourceHash": "d" * 64,
                "semanticProfile": "python-3.12",
                "status": "FROZEN",
                "body": {"declaredVariables": [], "freeVariables": []},
                "provenance": {
                    "sourceType": "test",
                    "sourceRevision": "r1",
                    "capturedAt": "2026-08-28T00:00:00Z",
                },
            }
        },
        "elmos-generated-workflow-model-checker": dict(workflow),
        "elmos-java-jml-contract-verifier": {
            "source": "//@ requires true; //@ ensures true;"
        },
        "elmos-language-semantic-profile": {
            "profile": {"language": "python", "version": "3.12", "features": []},
            "requestedFeatures": [],
        },
        "elmos-lease-fencing-verifier": {"fencingTokens": [1, 2], "staleCommits": []},
        "elmos-legacy-modernization-trace-validator": {"source": [], "target": []},
        "elmos-observable-behavior-contract": {
            "observationContract": {"dimensions": [], "normalizers": []},
            **trace,
        },
        "elmos-proof-artifact-store": {"artifactContent": "all-skill-evidence"},
        "elmos-proof-cache-invalidation": {"dependencyId": "dependency-all"},
        "elmos-proof-obligation-planner": {"obligations": [obligation()]},
        "elmos-proof-status-policy": {"results": []},
        "elmos-repository-refinement-composer": {"obligations": [obligation()]},
        "elmos-requirement-to-formal-spec": {
            "requirements": "The route must preserve tenant isolation"
        },
        "elmos-resource-termination-verifier": {"steps": 1, "resourceBudget": 1},
        "elmos-routine-contract-verifier": {"statements": []},
        "elmos-rule-preservation-prover": {"sourceRules": [], "targetRules": []},
        "elmos-schema-losslessness-proof": dict(schema),
        "elmos-semantic-gap-obligation-generator": {"gaps": []},
        "elmos-semantic-ir-formal-semantics": {"nodes": [], "transitions": []},
        "elmos-spring-exception-mapping-refinement": {"mappings": []},
        "elmos-spring-filter-interceptor-order-proof": {"orderConstraints": []},
        "elmos-spring-route-binding-proof": {"routes": []},
        "elmos-spring-security-chain-model": {"chains": []},
        "elmos-spring-session-state-refinement": {"transitions": []},
        "elmos-spring-transaction-refinement": dict(trace),
        "elmos-sql-query-equivalence": {
            "sourceSql": "select 1",
            "targetSql": "select 1",
        },
        "elmos-sql-semantic-ir": {"sql": "select 1"},
        "elmos-sql-type-precision-verifier": {"values": [], "moneyUsesDecimal": True},
        "elmos-tenant-noninterference-verifier": {"observations": []},
        "elmos-tla-task-runtime-model": dict(workflow),
        "elmos-trigger-trace-verifier": {"triggerDependencies": []},
        "elmos-trusted-computing-base-registry": {"components": []},
        "elmos-verifier-portfolio-router": {
            "propertyKind": "SAFETY",
            "adapters": [],
        },
        "elmos-waiver-governance": {
            "waiver": {
                "id": "waiver-all",
                "status": "APPROVED",
                "approvals": ["approver-a", "approver-b"],
                "compensatingControls": ["control-a"],
                "expiresAt": "2027-08-28T00:00:00Z",
            }
        },
        "elmos-concurrency-async-refinement": {
            "schedules": [],
            "forbiddenOutcomes": [],
        },
        "elmos-formal-model-versioning": {"fromVersion": "1.0.0", "toVersion": "1.0.1"},
        "elmos-liveness-fairness-verifier": {
            "states": ["done"],
            "transitions": [],
            "acceptingStates": ["done"],
        },
        "elmos-proof-carrying-conversion": {"artifacts": []},
        "elmos-proof-drift-monitor": {"baseline": {}, "current": {}},
        "elmos-proof-evidence-bundle": {"files": []},
        "elmos-spring-data-migration-refinement": dict(schema),
        "elmos-spring-proxy-aop-semantic-checker": {"pointcuts": []},
        "elmos-sql-transaction-exception-refinement": dict(trace),
        "elmos-verified-core-generator": {
            "functionName": "identity",
            "parameters": ["value"],
            "expression": "value",
        },
        "elmos-formal-observability-slo": {"metrics": [], "objectives": {}},
        "elmos-reflection-ffi-boundary-verifier": {
            "symbols": [],
            "declaredSymbols": [],
        },
    }


class AllSkillContractTests(unittest.TestCase):
    def test_every_exact_skill_executes_its_typed_local_contract(self) -> None:
        cases = fixtures()
        self.assertEqual(len(cases), 60)
        temporary = tempfile.TemporaryDirectory()
        store = StateStore()
        try:
            runtime = FormalAssuranceRuntime(
                store=store,
                config=RuntimeConfig(
                    artifact_root=Path(temporary.name) / "artifacts",
                    execution_root=Path(temporary.name) / "executions",
                ),
            )
            identity = TrustedIdentity("tenant-a", "operator-a", "project-a")
            self.assertEqual(set(cases), {item["skillId"] for item in runtime.list_skills()})
            for index, (skill_id, payload) in enumerate(cases.items()):
                with self.subTest(skill_id=skill_id):
                    result = runtime.dispatch(
                        skill_id,
                        {
                            "scope": scope(),
                            "subjectId": f"subject-{index}",
                            "idempotencyKey": f"all-skill-{index}",
                            **payload,
                        },
                        identity,
                    )
                    self.assertEqual(result["skillId"], skill_id)
                    self.assertEqual(result["implementationState"], "PRODUCTION_CODE_COMPLETE")
                    self.assertEqual(result["externalEvidenceStatus"], "NOT_RUN")
                    self.assertEqual(result["certificationStatus"], "NOT_CERTIFIED")
                    self.assertIsInstance(result["output"], dict)
                    self.assertTrue(result["requestDigest"].startswith("sha256:"))
        finally:
            store.close()
            temporary.cleanup()


if __name__ == "__main__":
    unittest.main()
