from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
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
    cases: dict[str, dict[str, object]] = {
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
    future = (
        (datetime.now(timezone.utc) + timedelta(days=365))
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    operation = {
        "operationId": "get-account",
        "method": "GET",
        "path": "/v1/accounts/{id}",
        "requestSchemaHash": "d" * 64,
        "responseSchemaHash": "e" * 64,
        "authorizationPolicy": "account-reader",
        "transactionBoundary": "READ_ONLY",
    }
    column = {"name": "amount", "type": "DECIMAL", "precision": 18}
    transaction_trace = [{"state": "COMMIT", "effect": "ledger-write"}]
    bounded_result = {
        "runId": "run-acceptance",
        "obligationId": "obl-a",
        "status": "BOUNDED_NO_COUNTEREXAMPLE",
        "assuranceLevel": "A1_BOUNDED",
        "engine": "local-bounded",
        "mode": "BOUNDED",
        "assumptionHash": "a" * 64,
        "tcbHash": "b" * 64,
        "bound": {"samples": 8},
    }
    workflow = {
        "states": ["queued", "done"],
        "transitions": [{"from": "queued", "to": "done"}],
        "initial": "queued",
        "terminalStates": ["done"],
    }
    cases.update(
        {
            "elmos-api-contract-verifier": {
                "sourceOperations": [dict(operation)],
                "targetOperations": [dict(operation)],
            },
            "elmos-architecture-constraint-checker": {
                "edges": [{"from": "api", "to": "domain"}],
                "forbiddenEdges": [{"from": "domain", "to": "infrastructure"}],
            },
            "elmos-assumption-ledger": {
                "assumptions": [
                    {
                        "id": "assumption-runtime",
                        "status": "ACTIVE",
                        "risk": "MEDIUM",
                        "owner": "operator-a",
                        "monitor": "monitor-runtime",
                        "expiresAt": future,
                    }
                ]
            },
            "elmos-credit-billing-invariant-model": {
                "ledgerEvents": [
                    {"id": "usage-reserve", "type": "RESERVE", "amount": 100},
                    {"id": "usage-consume", "type": "CONSUME", "amount": 60},
                    {"id": "usage-refund", "type": "REFUND", "amount": 40},
                ],
                "expectedOutstandingMicros": 0,
            },
            "elmos-cross-language-product-program": {
                "sourceProgram": {"inputs": ["amount"], "operations": ["add"]},
                "targetProgram": {"inputs": ["amount"], "operations": ["add"]},
            },
            "elmos-data-invariant-verifier": {
                "facts": {"balance": 40, "before": 100, "delta": -60, "after": 40}
            },
            "elmos-ddl-constraint-preservation": {
                "sourceColumns": [dict(column)],
                "targetColumns": [dict(column)],
            },
            "elmos-dml-state-equivalence": {
                "beforeRows": [{"id": 1, "state": "ACTIVE"}],
                "afterRows": [{"id": 1, "state": "ACTIVE"}],
                "sourceEffect": "UPDATE_ONE",
                "targetEffect": "UPDATE_ONE",
            },
            "elmos-dynamic-sql-proof-boundary": {
                "templates": ["select amount from ledger where tenant_id = :tenant"],
                "enumerationBound": 1,
            },
            "elmos-effect-exception-trace-refinement": {
                "sourceTrace": [
                    {"effect": "ledger-write", "exceptionKind": None, "committed": True}
                ],
                "targetTrace": [
                    {"effect": "ledger-write", "exceptionKind": None, "committed": True}
                ],
            },
            "elmos-formal-assurance-report": {
                "outcomes": [
                    {
                        "proofStatus": "BOUNDED_NO_COUNTEREXAMPLE",
                        "assuranceLevel": "A1_BOUNDED",
                    }
                ]
            },
            "elmos-formal-release-gate": {
                "obligations": [
                    {
                        **obligation("obl-a"),
                        "criticality": "P0",
                        "requiredAssurance": "A2_SOLVER_PROVED",
                        "allowBounded": False,
                    }
                ],
                "results": [dict(bounded_result)],
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
                    "body": {
                        "nodes": [{"id": "spec-node-return"}],
                        "declaredVariables": ["balance"],
                        "freeVariables": ["balance"],
                        "dynamicBoundaries": [
                            {"id": "clock-read", "coverage": "MONITORED"}
                        ],
                    },
                    "sourceMap": [
                        {"source": "Ledger.java:42", "target": "spec-node-return"}
                    ],
                    "provenance": {
                        "sourceType": "test",
                        "sourceRevision": "r1",
                        "capturedAt": "2026-08-28T00:00:00Z",
                    },
                }
            },
            "elmos-generated-workflow-model-checker": dict(workflow),
            "elmos-language-semantic-profile": {
                "profile": {
                    "language": "python",
                    "version": "3.12",
                    "features": [{"id": "decimal", "status": "SUPPORTED"}],
                },
                "requestedFeatures": ["decimal"],
            },
            "elmos-proof-status-policy": {"results": [dict(bounded_result)]},
            "elmos-legacy-modernization-trace-validator": {
                "source": [{"event": "account-loaded"}],
                "target": [{"event": "account-loaded"}],
                "traceRelation": "EXACT",
            },
            "elmos-observable-behavior-contract": {
                "observationContract": {
                    "dimensions": ["result", "effect"],
                    "normalizers": [{"field": "message", "operation": "CANONICALIZE"}],
                },
                "sourceTrace": [{"result": "ok", "message": "accepted"}],
                "targetTrace": [{"result": "ok", "message": "accepted"}],
            },
            "elmos-routine-contract-verifier": {
                "statements": ["select amount from ledger where id = :id"]
            },
            "elmos-rule-preservation-prover": {
                "sourceRules": [{"when": "balance>=0", "then": "allow"}],
                "targetRules": [{"when": "balance>=0", "then": "allow"}],
            },
            "elmos-schema-losslessness-proof": {
                "sourceColumns": [dict(column)],
                "targetColumns": [dict(column)],
            },
            "elmos-semantic-gap-obligation-generator": {
                "gaps": [
                    {
                        "id": "gap-decimal-rounding",
                        "kind": "NUMERIC_ROUNDING",
                        "source": "HALF_EVEN",
                        "target": "HALF_EVEN",
                    }
                ]
            },
            "elmos-semantic-ir-formal-semantics": {
                "nodes": [
                    {
                        "id": "node-return",
                        "kind": "RETURN",
                        "effects": ["read-ledger"],
                        "source": "Ledger.java:42",
                    }
                ],
                "transitions": [],
            },
            "elmos-spring-exception-mapping-refinement": {
                "mappings": [{"source": "LegacyNotFound", "target": "AccountNotFound"}]
            },
            "elmos-spring-filter-interceptor-order-proof": {
                "orderConstraints": [
                    {"from": "authentication", "to": "authorization"},
                    {"from": "authorization", "to": "business-handler"},
                ]
            },
            "elmos-spring-route-binding-proof": {
                "routes": [
                    {
                        "id": "route-account",
                        "method": "GET",
                        "path": "/accounts/{id}",
                        "order": 10,
                        "auth": "required",
                    }
                ]
            },
            "elmos-spring-security-chain-model": {
                "chains": [
                    {"matcher": "/accounts/**", "authorization": "authenticated"}
                ]
            },
            "elmos-spring-session-state-refinement": {
                "transitions": [
                    {
                        "event": "LOGIN",
                        "sessionIdUnchanged": False,
                        "state": "AUTHENTICATED",
                    }
                ]
            },
            "elmos-spring-transaction-refinement": {
                "sourceTrace": list(transaction_trace),
                "targetTrace": list(transaction_trace),
                "isolationLevel": "READ_COMMITTED",
            },
            "elmos-sql-type-precision-verifier": {
                "values": [{"source": "10.25", "target": "10.25"}],
                "moneyUsesDecimal": True,
            },
            "elmos-sql-query-equivalence": {
                "sourceSql": "select amount from ledger where tenant_id = :tenant",
                "targetSql": "select amount from ledger where tenant_id = :tenant",
                "comparisonDomain": "SAME_FIXTURE_AND_PARAMETERS",
            },
            "elmos-sql-semantic-ir": {
                "sql": "select amount from ledger where tenant_id = :tenant",
                "parameterized": True,
            },
            "elmos-tenant-noninterference-verifier": {
                "observations": [{"tenantId": "tenant-a", "event": "account-read"}]
            },
            "elmos-tla-task-runtime-model": dict(workflow),
            "elmos-trigger-trace-verifier": {
                "triggerDependencies": [{"from": "before-update", "to": "audit-insert"}]
            },
            "elmos-trusted-computing-base-registry": {
                "components": [
                    {
                        "id": "tcb-z3",
                        "version": "4.15.3",
                        "digest": "f" * 64,
                        "role": "SOLVER",
                    }
                ]
            },
            "elmos-verifier-portfolio-router": {
                "propertyKind": "SAFETY",
                "adapters": [
                    {
                        "name": "z3-pinned",
                        "engine": "z3",
                        "supportedProperties": ["SAFETY"],
                        "network": "deny",
                    }
                ],
            },
            "elmos-waiver-governance": {
                "waiver": {
                    "id": "waiver-all",
                    "status": "APPROVED",
                    "approvals": ["approver-a", "approver-b"],
                    "compensatingControls": ["runtime-monitor"],
                    "expiresAt": future,
                }
            },
            "elmos-concurrency-async-refinement": {
                "schedules": [
                    {
                        "id": "schedule-a",
                        "events": ["read", "compare", "write"],
                        "outcomes": ["SERIALIZABLE"],
                    }
                ],
                "forbiddenOutcomes": ["LOST_UPDATE"],
            },
            "elmos-liveness-fairness-verifier": {
                "states": ["queued", "done"],
                "transitions": [{"from": "queued", "to": "done"}],
                "acceptingStates": ["done"],
                "fairness": ["queued tasks are eventually scheduled"],
            },
            "elmos-proof-carrying-conversion": {
                "artifacts": [{"sha256": "a" * 64, "uri": "cas://tenant-a/proof"}]
            },
            "elmos-proof-drift-monitor": {
                "baseline": {"solver": "sha256:old"},
                "current": {"solver": "sha256:new"},
            },
            "elmos-proof-evidence-bundle": {
                "files": [
                    {"path": "proof/result.json", "content": '{"status":"bounded"}'}
                ]
            },
            "elmos-spring-data-migration-refinement": {
                "sourceColumns": [dict(column)],
                "targetColumns": [dict(column)],
            },
            "elmos-spring-proxy-aop-semantic-checker": {
                "pointcuts": [
                    {"target": "AccountService.transfer", "advice": "Transactional"}
                ]
            },
            "elmos-sql-transaction-exception-refinement": {
                "sourceTrace": list(transaction_trace),
                "targetTrace": list(transaction_trace),
                "isolationLevel": "READ_COMMITTED",
            },
            "elmos-formal-observability-slo": {
                "metrics": [
                    {"name": "proof_duration_ms", "labels": ["skillId", "status"]}
                ],
                "objectives": {
                    "minimumSuccessRateMicros": 0,
                    "maximumP95DurationMicros": 10_000_000,
                    "minimumSampleCount": 1,
                },
            },
            "elmos-reflection-ffi-boundary-verifier": {
                "symbols": ["ledger_read"],
                "declaredSymbols": ["ledger_read"],
            },
        }
    )
    return cases


EXPECTED_OUTPUT_KEYS = {
    "elmos-api-contract-verifier": "consumerDriven",
    "elmos-architecture-constraint-checker": "architectureDigest",
    "elmos-assumption-ledger": "assumptionDigest",
    "elmos-counterexample-to-test": "pytestSource",
    "elmos-credit-billing-invariant-model": "reconciled",
    "elmos-cross-language-product-program": "selfComposition",
    "elmos-data-invariant-verifier": "violations",
    "elmos-ddl-constraint-preservation": "precisionMismatches",
    "elmos-dml-state-equivalence": "stateEquivalentUnderDeclaredFixture",
    "elmos-dynamic-sql-proof-boundary": "parameterBindingRequired",
    "elmos-effect-exception-trace-refinement": "effectAndExceptionEquivalent",
    "elmos-formal-assurance-orchestrator": "events",
    "elmos-formal-assurance-report": "reportDigest",
    "elmos-formal-release-gate": "gateDecision",
    "elmos-formal-spec-ir": "specDigest",
    "elmos-generated-workflow-model-checker": "violations",
    "elmos-java-jml-contract-verifier": "nativeOpenJml",
    "elmos-language-semantic-profile": "profileDigest",
    "elmos-lease-fencing-verifier": "fencingEnforced",
    "elmos-legacy-modernization-trace-validator": "traceRelation",
    "elmos-observable-behavior-contract": "comparison",
    "elmos-proof-artifact-store": "artifact",
    "elmos-proof-cache-invalidation": "cacheStatus",
    "elmos-proof-obligation-planner": "dependenciesChecked",
    "elmos-proof-status-policy": "statusLattice",
    "elmos-repository-refinement-composer": "sccHandling",
    "elmos-requirement-to-formal-spec": "candidateProperties",
    "elmos-resource-termination-verifier": "rankingFunction",
    "elmos-routine-contract-verifier": "cfgBuilt",
    "elmos-rule-preservation-prover": "relationalCheck",
    "elmos-schema-losslessness-proof": "precisionMismatches",
    "elmos-semantic-gap-obligation-generator": "obligations",
    "elmos-semantic-ir-formal-semantics": "semanticIr",
    "elmos-spring-exception-mapping-refinement": "decisionTableComplete",
    "elmos-spring-filter-interceptor-order-proof": "happensBeforeGraph",
    "elmos-spring-route-binding-proof": "precedenceExplicit",
    "elmos-spring-security-chain-model": "authorizationDominanceChecked",
    "elmos-spring-session-state-refinement": "sessionFixationChecked",
    "elmos-spring-transaction-refinement": "isolationLevelCompared",
    "elmos-sql-query-equivalence": "canonicalTokensEqual",
    "elmos-sql-semantic-ir": "irDigest",
    "elmos-sql-type-precision-verifier": "moneyUsesDecimal",
    "elmos-tenant-noninterference-verifier": "noninterference",
    "elmos-tla-task-runtime-model": "reachable",
    "elmos-trigger-trace-verifier": "terminationStatus",
    "elmos-trusted-computing-base-registry": "tcbDigest",
    "elmos-verifier-portfolio-router": "candidates",
    "elmos-waiver-governance": "fourEyes",
    "elmos-concurrency-async-refinement": "schedulesReplayable",
    "elmos-formal-model-versioning": "modelDigest",
    "elmos-liveness-fairness-verifier": "livenessStatus",
    "elmos-proof-carrying-conversion": "signatureVerification",
    "elmos-proof-drift-monitor": "staleRequired",
    "elmos-proof-evidence-bundle": "manifest",
    "elmos-spring-data-migration-refinement": "precisionMismatches",
    "elmos-spring-proxy-aop-semantic-checker": "proxyReachability",
    "elmos-sql-transaction-exception-refinement": "errorMappingCompared",
    "elmos-verified-core-generator": "candidateDigest",
    "elmos-formal-observability-slo": "runtimeSnapshot",
    "elmos-reflection-ffi-boundary-verifier": "closedWorldEnumeration",
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
            self.assertEqual(
                set(cases), {item["skillId"] for item in runtime.list_skills()}
            )
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
                    self.assertEqual(
                        result["implementationState"], "PRODUCTION_CODE_COMPLETE"
                    )
                    self.assertEqual(result["externalEvidenceStatus"], "NOT_RUN")
                    self.assertEqual(result["certificationStatus"], "NOT_CERTIFIED")
                    self.assertIsInstance(result["output"], dict)
                    self.assertTrue(result["requestDigest"].startswith("sha256:"))
        finally:
            store.close()
            temporary.cleanup()


if __name__ == "__main__":
    unittest.main()
