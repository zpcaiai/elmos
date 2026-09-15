"""Comprehensive unit test suite for the ELMOS Composite Modernization Engine."""

import pytest
from elmos_composite_engine.models import (
    CompatibilityWindow,
    ContractConsumer,
    ContractConsumerMatrix,
    DependencyEdge,
    SystemNode,
)
from elmos_composite_engine.topology import DependencyGraphAnalyzer
from elmos_composite_engine.contract_governance import ContractGovernanceEngine
from elmos_composite_engine.shadow_differential import ShadowTrafficValidator
from elmos_composite_engine.cutover_engine import SystemCutoverOrchestrator
from elmos_composite_engine.wave_planner import MigrationWavePlanner


def test_topology_cycle_detection():
    # Setup circular dependency A -> B -> C -> A
    nodes = [
        SystemNode(nodeId="node-a", organizationId="org1", nodeType="SERVICE", name="A", language="JAVA", repositoryId="rA", deployableId="dA", environment="PROD"),
        SystemNode(nodeId="node-b", organizationId="org1", nodeType="SERVICE", name="B", language="CSHARP", repositoryId="rB", deployableId="dB", environment="PROD"),
        SystemNode(nodeId="node-c", organizationId="org1", nodeType="SERVICE", name="C", language="PYTHON", repositoryId="rC", deployableId="dC", environment="PROD"),
        SystemNode(nodeId="node-d", organizationId="org1", nodeType="SERVICE", name="D", language="GO", repositoryId="rD", deployableId="dD", environment="PROD"),
    ]
    edges = [
        DependencyEdge(edgeId="e1", organizationId="org1", sourceNodeId="node-a", targetNodeId="node-b", edgeType="CALLS_HTTP", environment="PROD"),
        DependencyEdge(edgeId="e2", organizationId="org1", sourceNodeId="node-b", targetNodeId="node-c", edgeType="CALLS_HTTP", environment="PROD"),
        DependencyEdge(edgeId="e3", organizationId="org1", sourceNodeId="node-c", targetNodeId="node-a", edgeType="CALLS_HTTP", environment="PROD"),
        DependencyEdge(edgeId="e4", organizationId="org1", sourceNodeId="node-d", targetNodeId="node-a", edgeType="CALLS_HTTP", environment="PROD"),
    ]

    analyzer = DependencyGraphAnalyzer(nodes, edges)
    sccs = analyzer.find_strongly_connected_components()
    assert len(sccs) == 1
    assert sorted(sccs[0]) == ["node-a", "node-b", "node-c"]

    # Blast radius test: node-c impacts node-b, node-a, and node-d
    blast_radius = analyzer.get_blast_radius("node-c")
    assert "node-b" in blast_radius
    assert "node-a" in blast_radius
    assert "node-d" in blast_radius


def test_shared_database_coupling():
    nodes = [
        SystemNode(nodeId="service-1", organizationId="org1", nodeType="SERVICE", name="S1", language="JAVA", repositoryId="r1", deployableId="d1", environment="PROD"),
        SystemNode(nodeId="service-2", organizationId="org1", nodeType="SERVICE", name="S2", language="CSHARP", repositoryId="r2", deployableId="d2", environment="PROD"),
        SystemNode(nodeId="db-shared", organizationId="org1", nodeType="DATABASE", name="SharedDB", language="SQL", repositoryId="rdb", deployableId="ddb", environment="PROD"),
    ]
    edges = [
        DependencyEdge(edgeId="e1", organizationId="org1", sourceNodeId="service-1", targetNodeId="db-shared", edgeType="WRITES_DB", environment="PROD"),
        DependencyEdge(edgeId="e2", organizationId="org1", sourceNodeId="service-2", targetNodeId="db-shared", edgeType="WRITES_DB", environment="PROD"),
    ]

    analyzer = DependencyGraphAnalyzer(nodes, edges)
    shared_dbs = analyzer.detect_shared_database_couplings()
    assert "db-shared" in shared_dbs
    assert sorted(shared_dbs["db-shared"]) == ["service-1", "service-2"]


def test_contract_governance_scenarios():
    engine = ContractGovernanceEngine()
    matrix = ContractConsumerMatrix(
        contractId="orders-api",
        producerNodeId="order-service",
        currentVersion="v1",
        protocol="HTTP",
        consumers=[
            ContractConsumer("billing-service", "v1"),
            ContractConsumer("shipping-service", "v2"),
        ]
    )

    # 1. Single consumer breaking
    res1 = engine.evaluate_contract_change(matrix, "BREAKING_FIELD_REMOVED", target_version="v2")
    assert res1["verdict"] == "CONTRACT_BREAKING"
    assert "billing-service" in res1["affected_consumers"]

    # 2. Multi consumer breaking
    matrix.consumers.append(ContractConsumer("analytics-service", "v1"))
    res2 = engine.evaluate_contract_change(matrix, "BREAKING_FIELD_REMOVED", target_version="v2")
    assert res2["verdict"] == "MULTI_CONSUMER_BREAKING"
    assert len(res2["affected_consumers"]) == 2

    # 3. Protobuf wire breaking
    res3 = engine.evaluate_contract_change(matrix, "PROTOBUF_FIELD_TAG_ALTERED", target_version="v1")
    assert res3["verdict"] == "WIRE_BREAKING"

    # 4. Unknown consumer blocker
    res4 = engine.evaluate_contract_change(matrix, "ANY", target_version="v1", unregistered_traffic_detected=True)
    assert res4["verdict"] == "UNKNOWN_CONSUMER_BLOCKER"


def test_compatibility_window():
    engine = ContractGovernanceEngine()
    window = CompatibilityWindow(
        windowId="w1",
        organizationId="org1",
        contractId="c1",
        oldVersion="v1",
        newVersion="v2",
        startsAt="2026-01-01T00:00:00Z",
        expiresAt="2026-06-01T00:00:00Z",
        owner="team-core",
        status="ACTIVE",
        oldVersionUsage=10
    )

    # Expired with active usage
    res = engine.check_compatibility_window(window, current_time_iso="2026-07-01T00:00:00Z")
    assert res["status"] == "EXPIRED_WITH_USAGE"
    assert res["removal_blocked"] is True

    # Expired without usage
    window.oldVersionUsage = 0
    res2 = engine.check_compatibility_window(window, current_time_iso="2026-07-01T00:00:00Z")
    assert res2["status"] == "SAFE_FOR_DECOMMISSION"
    assert res2["removal_blocked"] is False


def test_shadow_differential_validation():
    validator = ShadowTrafficValidator()

    # 1. Shadow write blocked
    safe_check = validator.validate_shadow_safety(http_method="POST", is_mutating=True)
    assert safe_check["verdict"] == "SHADOW_WRITE_BLOCKED"
    assert safe_check["safe"] is False

    # 2. Dynamic response normalization
    resp1 = {"id": "123", "timestamp": "2026-09-01T10:00:00Z", "amount": 100}
    resp2 = {"id": "456", "timestamp": "2026-09-01T10:00:01Z", "amount": 100}
    diff = validator.compare_responses(resp1, resp2)
    assert diff["verdict"] == "EXACT_AFTER_NORMALIZATION"
    assert diff["match"] is True

    # 3. Isolation on shadow failure
    impact = validator.evaluate_shadow_failure_impact(primary_status=200, shadow_failed=True)
    assert impact["verdict"] == "PRIMARY_UNAFFECTED"

    # 4. CDC lag
    cdc = validator.evaluate_cdc_lag(lag_ms=1500.0, max_allowed_ms=1000.0)
    assert cdc["verdict"] == "CDC_LAG_EXCEEDED"

    # 5. Dual write partial failure
    dual = validator.evaluate_dual_write_atomicity(primary_write_ok=True, secondary_write_ok=False)
    assert dual["verdict"] == "PARTIAL_WRITE"


def test_cutover_orchestration():
    orchestrator = SystemCutoverOrchestrator()

    # Read cutover approved
    read_decision = orchestrator.evaluate_cutover_request(
        plan_id="plan-01",
        current_state="SHADOW_RUN",
        requested_state="READ_CUTOVER",
        read_differential_pass_rate=1.0,
        write_idempotency_verified=False
    )
    assert read_decision.decision == "APPROVED"
    assert read_decision.rollbackClassification == "AUTOMATIC_REVERSIBLE"

    # Write cutover blocked without idempotency
    write_decision = orchestrator.evaluate_cutover_request(
        plan_id="plan-01",
        current_state="READ_CUTOVER",
        requested_state="WRITE_CUTOVER",
        read_differential_pass_rate=1.0,
        write_idempotency_verified=False,
        has_incompatible_new_writes=True
    )
    assert write_decision.decision == "BLOCKED"
    assert "NEW_WRITE_IDEMPOTENCY_FAILED" in write_decision.blockers
    assert write_decision.rollbackClassification == "FORWARD_FIX_ONLY"

    # Canary rollback
    canary = orchestrator.evaluate_canary_health(error_rate_bps=100, latency_p95_ms=50.0, max_error_rate_bps=50)
    assert canary["decision"] == "ROLLBACK"

    # Decommission blocked with active traffic
    decom = orchestrator.evaluate_decommission_readiness("legacy-orders", active_traffic_rpm=5.0, active_batch_jobs=[])
    assert decom["verdict"] == "LEGACY_DECOMMISSION_BLOCKED"

    # Idempotency duplicate suppressed
    cache = set()
    first = orchestrator.verify_message_idempotency("msg-101", cache)
    assert first["verdict"] == "PROCESSED"
    dup = orchestrator.verify_message_idempotency("msg-101", cache)
    assert dup["verdict"] == "DUPLICATE_SUPPRESSED"


def test_migration_wave_planning():
    nodes = [
        SystemNode(nodeId="service-ui", organizationId="org1", nodeType="SERVICE", name="UI", language="TS", repositoryId="rUI", deployableId="dUI", environment="PROD"),
        SystemNode(nodeId="service-api", organizationId="org1", nodeType="SERVICE", name="API", language="JAVA", repositoryId="rAPI", deployableId="dAPI", environment="PROD"),
        SystemNode(nodeId="service-db", organizationId="org1", nodeType="DATABASE", name="DB", language="SQL", repositoryId="rDB", deployableId="dDB", environment="PROD"),
    ]
    edges = [
        DependencyEdge(edgeId="e1", organizationId="org1", sourceNodeId="service-ui", targetNodeId="service-api", edgeType="CALLS_HTTP", environment="PROD"),
        DependencyEdge(edgeId="e2", organizationId="org1", sourceNodeId="service-api", targetNodeId="service-db", edgeType="WRITES_DB", environment="PROD"),
    ]

    planner = MigrationWavePlanner()
    waves = planner.plan_waves(nodes, edges)

    assert len(waves) >= 2
    # Leaf dependency (DB) should be in earliest wave
    assert "service-db" in waves[0].nodes
