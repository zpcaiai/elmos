from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from elmos_sql_transpiler.cli import main
from elmos_sql_transpiler.commercial import commercial_capabilities
from elmos_sql_transpiler.skill_runtime import (
    HANDLERS,
    MAX_REQUEST_BYTES,
    SKILL_SPECS,
    SKILLS_BY_ID,
    execute_skill,
    parse_skill_request_json,
    skill_capabilities,
)

_DIGEST = "sha256:" + "0" * 64
_SCOPE = {"tenantId": "tenant-1", "projectId": "project-1", "actorId": "actor-1"}
_SNAPSHOT = str(commercial_capabilities()["capabilitySnapshotDigest"])


def _scoped(**parts: object) -> dict[str, object]:
    return {"scope": dict(_SCOPE), **parts}


def _assessment(sql: str) -> dict[str, object]:
    return {
        "schemaVersion": "1.0",
        "queryId": "skill-runtime-assessment",
        "sourceProfile": "oracle-26ai-ee",
        "targetId": "dm8",
        "targetVersion": "8.1.3.140",
        "targetEdition": "enterprise",
        "compatibilityMode": "oracle-compatible-explicit",
        "targetDriver": "dm-jdbc-8.1.3.140",
        "targetCharset": "UTF-8",
        "targetCollation": "BINARY",
        "targetTimeZone": "Asia/Shanghai",
        "capabilitySnapshotDigest": _SNAPSHOT,
        "sql": sql,
        "parameters": [],
    }


def _target_request(target_id: str, *, snapshot: str = _SNAPSHOT) -> dict[str, object]:
    return _scoped(
        target={
            "id": target_id,
            "version": "1.0.0",
            "edition": "enterprise",
            "compatibilityMode": "native-explicit",
            "driver": "jdbc-1.0.0",
            "capabilitySnapshotDigest": snapshot,
        }
    )


def _passing_gates() -> dict[str, dict[str, object]]:
    return {
        gate_id: {"state": "PASSED", "evidenceDigest": _DIGEST, "independent": True}
        for gate_id in ("E1", "E2", "E3", "E4", "E5")
    }


def _minimal_payload(skill_id: str) -> dict[str, object]:
    spec = SKILLS_BY_ID[skill_id]
    handler = spec.handler_id
    if handler == "orchestrate":
        return _scoped(requestedSkills=["01-estate-inventory-assessment"])
    if handler == "inventory":
        return _scoped(objects=[])
    if handler == "semantic-ir":
        return _scoped(nodes=[])
    if handler == "rule-dsl":
        return _scoped(rules=[])
    if handler == "cdc-plan":
        return _scoped(
            sourceSnapshotDigest=_DIGEST,
            chunks=[],
            cdcEvents=[],
            sourceRowDigests=[],
            targetRowDigests=[],
        )
    if handler == "ddl-conversion":
        return _scoped(assessment=_assessment("CREATE TABLE sample_table (id NUMBER(10))"))
    if handler == "sql-conversion":
        return _scoped(assessment=_assessment("SELECT 1 AS value FROM dual"))
    if handler == "procedural-strategy":
        return _scoped(units=[])
    if handler == "application-plan" or handler.startswith("application:"):
        return _scoped(callSites=[], targetDriver="jdbc-1.0.0")
    if handler == "behavior-verify":
        return _scoped(cases=[])
    if handler in {"performance-verify", "benchmark-gate"}:
        return _scoped(cases=[])
    if handler == "repair-plan":
        return _scoped(findings=[])
    if handler == "cutover-gate":
        return _scoped(
            phases=[{"phaseId": "local", "state": "PASSED"}],
            cdcGap=0,
            reconciliationPassed=True,
            rollbackRehearsed=True,
        )
    if handler == "certification-gate":
        return _scoped(gates=_passing_gates())
    if handler == "security-diff":
        return _scoped(sourceGrants=[], targetGrants=[], sourcePolicies=[], targetPolicies=[])
    if handler == "evidence-ledger":
        return _scoped(entries=[])
    if handler == "release-gate":
        return _scoped(checks=[{"checkId": "local", "state": "PASSED"}])
    if handler.startswith("source:"):
        if spec.bound_value in {"db2-luw", "sybase-ase"}:
            return _scoped(catalogObjects=[])
        return _scoped(sql="SELECT 1")
    if handler.startswith("target:"):
        return _target_request(str(spec.bound_value))
    if handler == "route-matrix":
        return _scoped(routeEvidence=[])
    if handler == "mutation-gate":
        return _scoped(mutants=[])
    if handler == "estimate":
        return _scoped(objectCounts={}, weights={})
    if handler == "vendor-bridge":
        return _scoped(
            provider="vendor-1",
            operation="DISCOVER",
            credentialRef="vault-ref-1",
            authorized=False,
        )
    if handler == "observability":
        return _scoped(events=[])
    raise AssertionError(f"no test payload for {skill_id}: {handler}")


def _blocker_codes(result: dict[str, Any]) -> set[str]:
    return {str(item["code"]) for item in result["blockers"]}


def test_capability_matrix_binds_exactly_all_47_skills() -> None:
    value = skill_capabilities()

    assert value["skillCount"] == value["codeImplementedCount"] == 47
    assert value["boundedLocalHandlerCoverage"] == {
        "implemented": 47,
        "total": 47,
        "rate": 1.0,
    }
    assert value["importedSpecificationStatus"] == "SPEC_ONLY"
    assert value["productionDefinitionOfDoneCount"] == 0
    assert value["productionDefinitionOfDone"] == "BLOCKED_EXTERNAL_EVIDENCE"
    assert len(SKILL_SPECS) == len(SKILLS_BY_ID) == len(HANDLERS) == 47
    assert {item["skillId"] for item in value["bindings"]} == set(SKILLS_BY_ID)
    assert all(item["localCodeStatus"] == "CODE_IMPLEMENTED" for item in value["bindings"])
    assert all(callable(handler) for handler in HANDLERS.values())
    assert value["externalExecution"] == "NOT_RUN"
    assert value["independentVerification"] == "NOT_RUN"
    assert value["certification"] == "NOT_CERTIFIED"


@pytest.mark.parametrize("skill_id", sorted(SKILLS_BY_ID))
def test_every_exact_skill_has_an_executable_bounded_handler(skill_id: str) -> None:
    result = execute_skill(skill_id, _minimal_payload(skill_id))

    assert result["skillId"] == skill_id
    assert result["handlerId"] == SKILLS_BY_ID[skill_id].handler_id
    assert result["localCodeStatus"] == "CODE_IMPLEMENTED"
    assert result["state"] in {
        "LOCAL_COMPLETED",
        "LOCAL_FAILED",
        "BLOCKED_EXTERNAL",
        "READY_FOR_HUMAN_DECISION",
        "READY_FOR_EXTERNAL_GATE",
    }
    assert result["effects"]["externalEffectsExecuted"] == []
    assert result["verification"]["externalExecution"] == "NOT_RUN"
    assert result["verification"]["independentVerification"] == "NOT_RUN"
    assert result["certification"] == "NOT_CERTIFIED"
    assert result["requestDigest"].startswith("sha256:")
    assert result["artifactDigest"].startswith("sha256:")
    assert result["resultDigest"].startswith("sha256:")


def test_execution_is_deterministic_and_scope_bound() -> None:
    payload = _scoped(objects=[])

    first = execute_skill("01-estate-inventory-assessment", payload)
    second = execute_skill("01-estate-inventory-assessment", payload)

    assert first == second
    assert first["scope"] == _SCOPE


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"objects": []}, "scope"),
        (_scoped(objects=[], password="raw-secret"), "inline secret"),
        (_scoped(objects=[], nested={"access_token": "raw-secret"}), "inline secret"),
        (
            {
                "scope": {
                    "tenantId": "tenant-1",
                    "projectId": "project-1",
                    "actorId": "actor-1",
                    "organizationId": "org-1",
                },
                "objects": [],
            },
            "accepts exactly",
        ),
    ],
)
def test_requests_fail_closed_on_scope_or_secret_boundary(
    payload: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        execute_skill("01-estate-inventory-assessment", payload)


def test_request_size_and_non_finite_numbers_are_rejected() -> None:
    with pytest.raises(ValueError, match="1 MiB"):
        execute_skill(
            "22-source-postgresql-adapter",
            _scoped(sql="X" * MAX_REQUEST_BYTES),
        )


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b'{"scope":{},"scope":{}}', "duplicate field"),
        (b'{"value":NaN}', "non-finite"),
        (b"\xff", "UTF-8"),
        (b"[]", "JSON object"),
    ],
)
def test_strict_skill_json_decoder_rejects_ambiguous_inputs(payload: bytes, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_skill_request_json(payload)
    with pytest.raises(ValueError, match="finite canonical JSON"):
        execute_skill(
            "63-migration-estimation-commercial-report",
            _scoped(objectCounts={"table": 1}, weights={"table": float("nan")}),
        )


def test_orchestrator_builds_dependency_closed_topological_plan() -> None:
    result = execute_skill(
        "00-migration-program-orchestrator",
        _scoped(requestedSkills=["16-release-ci-quality-gates"]),
    )
    plan = result["artifacts"]["dependencyClosedPlan"]

    assert plan[-1] == "16-release-ci-quality-gates"
    assert set(SKILLS_BY_ID["16-release-ci-quality-gates"].dependencies) < set(plan)
    positions = {skill_id: index for index, skill_id in enumerate(plan)}
    for skill_id in plan:
        assert all(
            positions[dependency] < positions[skill_id]
            for dependency in SKILLS_BY_ID[skill_id].dependencies
        )


def test_inventory_and_canonical_ir_reject_unresolved_references() -> None:
    inventory = execute_skill(
        "01-estate-inventory-assessment",
        _scoped(
            objects=[
                {
                    "objectId": "table-1",
                    "kind": "table",
                    "definitionDigest": _DIGEST,
                    "dependencies": ["missing-table"],
                    "support": "UNKNOWN",
                }
            ]
        ),
    )
    canonical = execute_skill(
        "02-semantic-db-ir",
        _scoped(
            nodes=[
                {
                    "id": "table-1",
                    "kind": "table",
                    "sourceDigest": _DIGEST,
                    "semantics": {"nullable": False},
                    "dependencies": ["missing-type"],
                    "unsupportedExtensions": [],
                }
            ]
        ),
    )

    assert inventory["state"] == canonical["state"] == "LOCAL_FAILED"
    assert _blocker_codes(inventory) == {"INVENTORY_DEPENDENCY_MISSING"}
    assert _blocker_codes(canonical) == {"CANONICAL_IR_REFERENCE_MISSING"}


def test_rule_dsl_detects_semantic_collisions() -> None:
    common = {
        "sourceKind": "TYPE",
        "predicate": {"name": "NUMBER"},
        "priority": 10,
        "risk": "HIGH",
    }
    result = execute_skill(
        "03-rule-mutation-dsl",
        _scoped(
            rules=[
                {"ruleId": "rule-1", "action": "NATIVE", **common},
                {"ruleId": "rule-2", "action": "REWRITE", **common},
            ]
        ),
    )

    assert result["state"] == "LOCAL_FAILED"
    assert _blocker_codes(result) == {"RULE_COLLISION"}


def test_cdc_plan_detects_replay_and_detail_reconciliation_errors() -> None:
    result = execute_skill(
        "04-data-movement-cdc",
        _scoped(
            sourceSnapshotDigest=_DIGEST,
            chunks=[{"chunkId": "c1", "start": 0, "end": 10, "payloadDigest": _DIGEST}],
            cdcEvents=[
                {"eventId": "event-1", "position": 2},
                {"eventId": "event-1", "position": 1},
            ],
            sourceRowDigests=["row-a"],
            targetRowDigests=["row-b"],
        ),
    )

    assert result["state"] == "BLOCKED_EXTERNAL"
    assert _blocker_codes(result) == {
        "CDC_DUPLICATE_EVENT",
        "CDC_POSITION_NOT_MONOTONIC",
        "DETAIL_RECONCILIATION_MISMATCH",
        "EXTERNAL_DATA_MOVEMENT_NOT_RUN",
    }
    assert result["artifacts"]["reconciliationPassed"] is False


@pytest.mark.parametrize(
    ("skill_id", "sql", "expected_kind"),
    [
        ("05-ddl-auto-conversion", "CREATE TABLE sample_table (id NUMBER(10))", "CREATE"),
        ("06-sql-auto-conversion", "SELECT 1 AS value FROM dual", "SELECT"),
    ],
)
def test_conversion_skills_parse_typed_source_but_never_fabricate_target_sql(
    skill_id: str, sql: str, expected_kind: str
) -> None:
    result = execute_skill(skill_id, _scoped(assessment=_assessment(sql)))

    assert result["state"] == "BLOCKED_EXTERNAL"
    assert result["artifacts"]["typedStatementCount"] == 1
    assert result["artifacts"]["assessment"]["statements"][0]["kind"] == expected_kind
    assert result["artifacts"]["targetSql"] is None
    assert result["checks"][1] == {"id": "TARGET_SQL_NOT_FABRICATED", "state": "PASSED"}


def test_conversion_skills_reject_cross_kind_use() -> None:
    result = execute_skill(
        "05-ddl-auto-conversion",
        _scoped(assessment=_assessment("SELECT 1 AS value FROM dual")),
    )

    assert "SKILL_STATEMENT_KIND_MISMATCH" in _blocker_codes(result)


def test_procedural_strategy_is_typed_and_fail_closed() -> None:
    result = execute_skill(
        "07-plsql-tsql-conversion",
        _scoped(
            units=[
                {"unitId": "pure", "language": "plsql", "typedSignature": True},
                {
                    "unitId": "dynamic",
                    "language": "plsql",
                    "typedSignature": True,
                    "dynamicSql": True,
                },
                {
                    "unitId": "stateful",
                    "language": "tsql",
                    "typedSignature": True,
                    "packageState": True,
                },
            ]
        ),
    )
    strategies = {item["unitId"]: item["strategy"] for item in result["artifacts"]["strategies"]}

    assert strategies == {
        "pure": "DIRECT_TARGET_CANDIDATE",
        "dynamic": "UNSUPPORTED",
        "stateful": "LIFT_TO_APP",
    }
    assert result["state"] == "LOCAL_FAILED"


@pytest.mark.parametrize(
    ("skill_id", "language"),
    [
        ("30-app-java-spring-adapter", "java"),
        ("31-app-dotnet-adapter", "dotnet"),
        ("32-app-python-adapter", "python"),
        ("33-app-nodejs-adapter", "nodejs"),
        ("34-app-go-adapter", "go"),
    ],
)
def test_application_adapters_emit_safe_patch_plans_without_writing(
    skill_id: str, language: str
) -> None:
    result = execute_skill(
        skill_id,
        _scoped(
            targetDriver="driver-1",
            callSites=[
                {
                    "callId": "call-1",
                    "language": language,
                    "parameterized": True,
                    "transactionKnown": True,
                    "stableError": "duplicate_key",
                    "sourceDigest": _DIGEST,
                }
            ],
        ),
    )

    assert result["state"] == "LOCAL_COMPLETED"
    assert result["artifacts"]["patchPlans"][0]["safeToApply"] is True
    assert result["artifacts"]["repositoryMutated"] is False


def test_behavior_and_performance_oracles_report_exact_failures() -> None:
    behavior = execute_skill(
        "09-behavior-equivalence-verification",
        _scoped(
            cases=[
                {
                    "caseId": "unordered",
                    "mode": "UNORDERED_ROWS",
                    "source": [1, 2],
                    "target": [2, 1],
                },
                {
                    "caseId": "error",
                    "mode": "STABLE_ERROR",
                    "source": "deadlock",
                    "target": "lock_timeout",
                },
            ]
        ),
    )
    performance = execute_skill(
        "10-performance-equivalence-verification",
        _scoped(
            cases=[
                {
                    "caseId": "latency",
                    "sourceEnvironmentDigest": _DIGEST,
                    "targetEnvironmentDigest": _DIGEST,
                    "sourceP95Ms": 100,
                    "targetP95Ms": 140,
                    "sourceThroughput": 100,
                    "targetThroughput": 75,
                    "maxP95RegressionPct": 20,
                    "minThroughputRatio": 0.9,
                }
            ]
        ),
    )

    assert behavior["artifacts"]["failedCaseIds"] == ["error"]
    assert _blocker_codes(behavior) == {"BEHAVIOR_MISMATCH"}
    assert performance["artifacts"]["failedCaseIds"] == ["latency"]
    assert _blocker_codes(performance) == {"PERFORMANCE_POLICY_FAILED"}


def test_repair_cutover_certification_and_release_never_execute_authority() -> None:
    repair = execute_skill(
        "11-guarded-auto-repair",
        _scoped(findings=[{"findingId": "precision-1", "domain": "PRECISION"}]),
    )
    cutover = execute_skill(
        "12-cutover-rollback",
        _scoped(
            phases=[{"phaseId": "rehearsal", "state": "PASSED"}],
            cdcGap=0,
            reconciliationPassed=True,
            rollbackRehearsed=True,
        ),
    )
    certification = execute_skill(
        "13-production-migration-certification", _scoped(gates=_passing_gates())
    )
    release = execute_skill(
        "16-release-ci-quality-gates",
        _scoped(checks=[{"checkId": "local-suite", "state": "PASSED"}]),
    )

    assert repair["state"] == "READY_FOR_HUMAN_DECISION"
    assert repair["artifacts"]["patchesApplied"] == 0
    assert cutover["state"] == "READY_FOR_HUMAN_DECISION"
    assert cutover["artifacts"]["productionSwitchExecuted"] is False
    assert certification["state"] == "READY_FOR_EXTERNAL_GATE"
    assert certification["artifacts"]["externalCertificateIssued"] is False
    assert certification["artifacts"]["certificationDecision"] == "NOT_CERTIFIED"
    assert release["state"] == "READY_FOR_EXTERNAL_GATE"
    assert release["artifacts"]["released"] is False


def test_security_and_evidence_handlers_enforce_no_broadening_and_separation() -> None:
    security = execute_skill(
        "14-security-governance",
        _scoped(
            sourceGrants=["reader"],
            targetGrants=["reader", "admin"],
            sourcePolicies=["tenant-policy"],
            targetPolicies=[],
        ),
    )

    assert security["state"] == "LOCAL_FAILED"
    assert _blocker_codes(security) == {"PRIVILEGE_BROADENING", "ROW_POLICY_MISSING"}

    with pytest.raises(ValueError, match="self-verified"):
        execute_skill(
            "15-evidence-ledger-reproducibility",
            _scoped(
                entries=[
                    {
                        "evidenceId": "e1",
                        "contentDigest": _DIGEST,
                        "refs": [],
                        "producer": "agent-a",
                        "verifier": "agent-a",
                    }
                ]
            ),
        )


@pytest.mark.parametrize(
    "skill_id",
    [
        "20-source-oracle-adapter",
        "21-source-sqlserver-adapter",
        "22-source-postgresql-adapter",
        "23-source-mysql-adapter",
    ],
)
def test_parser_backed_source_adapters_produce_typed_ast(skill_id: str) -> None:
    result = execute_skill(skill_id, _scoped(sql="SELECT 1"))

    assert result["state"] == "LOCAL_COMPLETED"
    assert result["artifacts"]["mode"] == "TYPED_AST"
    assert result["artifacts"]["statements"][0]["kind"] == "SELECT"


@pytest.mark.parametrize(
    "skill_id",
    ["24-source-db2-adapter", "25-source-sybase-adapter"],
)
def test_catalog_only_source_adapters_reject_raw_sql_and_accept_typed_catalog(
    skill_id: str,
) -> None:
    raw = execute_skill(skill_id, _scoped(sql="SELECT 1"))
    catalog = execute_skill(
        skill_id,
        _scoped(
            catalogObjects=[
                {
                    "objectId": "table-1",
                    "kind": "table",
                    "definitionDigest": _DIGEST,
                }
            ]
        ),
    )

    assert raw["state"] == "LOCAL_FAILED"
    assert _blocker_codes(raw) == {"NATIVE_SOURCE_PARSER_REQUIRED"}
    assert catalog["state"] == "LOCAL_COMPLETED"
    assert catalog["artifacts"]["mode"] == "TYPED_CATALOG"


@pytest.mark.parametrize(
    "skill_id",
    [spec.skill_id for spec in SKILL_SPECS if spec.category == "target-adapter"],
)
def test_all_thirteen_target_adapters_are_exact_and_evidence_gated(skill_id: str) -> None:
    target_id = str(SKILLS_BY_ID[skill_id].bound_value)
    result = execute_skill(skill_id, _target_request(target_id))

    assert result["state"] == "BLOCKED_EXTERNAL"
    assert result["artifacts"]["targetId"] == target_id
    assert result["artifacts"]["targetSql"] is None
    assert result["artifacts"]["adapterProtocol"]["discover"] == "IMPLEMENTED_CONTRACT"
    assert result["effects"]["externalEffectsExecuted"] == []
    assert _blocker_codes(result) == {"TARGET_RUNTIME_AND_CAPABILITY_EVIDENCE_REQUIRED"}


def test_target_adapter_rejects_stale_snapshot_and_wrong_bound_identity() -> None:
    with pytest.raises(ValueError, match="current registry"):
        execute_skill("40-target-dm8", _target_request("dm8", snapshot=_DIGEST))
    with pytest.raises(ValueError, match="handler-bound"):
        execute_skill("40-target-dm8", _target_request("kingbasees"))


def test_route_matrix_mutation_estimate_vendor_and_observability_handlers() -> None:
    matrix = execute_skill("60-route-support-matrix", _scoped(routeEvidence=[]))
    mutation = execute_skill(
        "61-fixture-corpus-and-mutation-tests",
        _scoped(mutants=[{"mutantId": "drop-check", "critical": True, "detected": False}]),
    )
    estimate = execute_skill(
        "63-migration-estimation-commercial-report",
        _scoped(objectCounts={"table": 10, "routine": 2}, weights={"table": "1.5"}),
    )
    bridge = execute_skill(
        "64-vendor-native-tool-bridge",
        _scoped(
            provider="vendor-1",
            operation="DISCOVER",
            credentialRef="vault-ref-1",
            authorized=True,
        ),
    )
    observability = execute_skill(
        "65-observability-migration-control-plane",
        _scoped(
            events=[
                {
                    "eventId": "event-1",
                    "state": "BLOCKED",
                    "severity": "CRITICAL",
                }
            ]
        ),
    )

    assert matrix["artifacts"]["routeCount"] == 78
    assert matrix["artifacts"]["externalPassed"] == 0
    assert mutation["state"] == "LOCAL_FAILED"
    assert _blocker_codes(mutation) == {"CRITICAL_MUTATION_SURVIVED"}
    assert estimate["artifacts"]["estimatePoints"] == "17.0"
    assert estimate["artifacts"]["notACommercialQuote"] is True
    assert bridge["state"] == "BLOCKED_EXTERNAL"
    assert bridge["artifacts"]["providerCalled"] is False
    assert observability["artifacts"]["alerts"] == [
        {"eventId": "event-1", "reason": "BLOCKED_CRITICAL"}
    ]
    assert observability["artifacts"]["externalMetricsPublished"] is False


def test_skill_cli_capabilities_and_execution_are_create_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(_scoped(objects=[])), encoding="utf-8")
    output_path = tmp_path / "result.json"

    assert main(["commercial-skill-capabilities"]) == 0
    capabilities = json.loads(capsys.readouterr().out)
    assert capabilities["skillCount"] == 47

    assert (
        main(
            [
                "commercial-skill-run",
                "01-estate-inventory-assessment",
                str(request_path),
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    assert json.loads(output_path.read_text(encoding="utf-8"))["state"] == "LOCAL_COMPLETED"

    assert (
        main(
            [
                "commercial-skill-run",
                "01-estate-inventory-assessment",
                str(request_path),
                "--output",
                str(output_path),
            ]
        )
        == 2
    )
    error = json.loads(capsys.readouterr().err)
    assert error["status"] == "BLOCKED"
    assert error["certification"] == "NOT_CERTIFIED"
