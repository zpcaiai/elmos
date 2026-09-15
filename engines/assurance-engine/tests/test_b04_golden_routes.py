"""Tests for B04 Golden Routes: sql-conversion, spring-modernization, and repository-conversion."""

from elmos_assurance_engine.contracts import GateDecision
from elmos_assurance_engine.dispatcher import dispatch_assurance_skill
from elmos_assurance_engine.orchestrator import AssuranceOrchestrator
from elmos_assurance_engine.repository_domain import (
    RepositoryConversionRouteRunner,
    RepositoryRequirementOracle,
)
from elmos_assurance_engine.spring_domain import (
    SpringModernizationRouteRunner,
    SpringRequirementOracle,
)
from elmos_assurance_engine.sql_domain import (
    SqlConversionRouteRunner,
    SqlRequirementOracle,
)


def test_sql_conversion_route_passes_all_cases():
    res = SqlConversionRouteRunner.run_all()
    assert res["domain"] == "sql-conversion"
    assert res["golden_route"] == "golden-sql-conversion"
    assert res["overall_decision"] == GateDecision.PASS
    assert len(res["cases"]) == 6
    for case_id, case_result in res["cases"].items():
        assert case_result["decision"] == GateDecision.PASS, f"Failed case: {case_id}"


def test_sql_requirement_oracle_rejects_counterexamples():
    oracle = SqlRequirementOracle()

    # Lossy float rejection
    dec, msg = oracle.evaluate_sql_conversion(
        source_dialect="oracle",
        target_dialect="postgresql",
        source_ast={},
        target_ast={
            "columns": [{"name": "price", "source_type": "DECIMAL", "target_type": "FLOAT"}]
        },
        source_output=[],
        target_output=[],
    )
    assert dec == GateDecision.FAIL
    assert "LOSSY_TYPE_MAPPING" in msg

    # Dropped constraint rejection
    dec2, msg2 = oracle.evaluate_sql_conversion(
        source_dialect="oracle",
        target_dialect="postgresql",
        source_ast={"constraints": ["fk_customer_id"]},
        target_ast={"constraints": []},
        source_output=[],
        target_output=[],
    )
    assert dec2 == GateDecision.FAIL
    assert "DROPPED_CONSTRAINTS" in msg2

    # Unsupported function rejection
    dec3, msg3 = oracle.evaluate_sql_conversion(
        source_dialect="oracle",
        target_dialect="postgresql",
        source_ast={},
        target_ast={"unsupported_functions": ["ORACLE_SPATIAL_SDO_FILTER"]},
        source_output=[],
        target_output=[],
    )
    assert dec3 == GateDecision.FAIL
    assert "UNSUPPORTED_VENDOR_FUNCTIONS" in msg3


def test_spring_modernization_route_passes_all_cases():
    res = SpringModernizationRouteRunner.run_all()
    assert res["domain"] == "spring-modernization"
    assert res["golden_route"] == "golden-spring-modernization"
    assert res["overall_decision"] == GateDecision.PASS
    assert len(res["cases"]) == 6
    for case_id, case_result in res["cases"].items():
        assert case_result["decision"] == GateDecision.PASS, f"Failed case: {case_id}"


def test_spring_requirement_oracle_rejects_counterexamples():
    oracle = SpringRequirementOracle()

    # Self-invocation transaction bypass rejection
    dec, msg = oracle.evaluate_spring_migration(
        source_security={},
        target_security={},
        proxy_mode="RAW_THIS_INVOCATION",
        session_preserved=True,
        behavioral_tests_passed=True,
        target_build_passed=True,
    )
    assert dec == GateDecision.FAIL
    assert "TRANSACTION_BYPASS_SELF_INVOCATION" in msg

    # Lost returnUrl session rejection
    dec2, msg2 = oracle.evaluate_spring_migration(
        source_security={},
        target_security={},
        proxy_mode="ASPECTJ_WEAVING",
        session_preserved=False,
        behavioral_tests_passed=True,
        target_build_passed=True,
    )
    assert dec2 == GateDecision.FAIL
    assert "SESSION_RETURN_URL_LOST" in msg2

    # Target build alone without behavioral tests rejection
    dec3, msg3 = oracle.evaluate_spring_migration(
        source_security={},
        target_security={},
        proxy_mode="ASPECTJ_WEAVING",
        session_preserved=True,
        behavioral_tests_passed=False,
        target_build_passed=True,
    )
    assert dec3 == GateDecision.FAIL
    assert "TARGET_BUILD_PASSED_BUT_BEHAVIOR_NOT_CERTIFIED" in msg3

    # Security loosening rejection
    dec4, msg4 = oracle.evaluate_spring_migration(
        source_security={"/api/secure": ["ROLE_ADMIN"]},
        target_security={"/api/secure": ["ROLE_ANONYMOUS"]},
        proxy_mode="ASPECTJ_WEAVING",
        session_preserved=True,
        behavioral_tests_passed=True,
        target_build_passed=True,
    )
    assert dec4 == GateDecision.FAIL
    assert "SECURITY_LOOSENED" in msg4


def test_repository_conversion_route_passes_all_cases():
    res = RepositoryConversionRouteRunner.run_all()
    assert res["domain"] == "repository-conversion"
    assert res["golden_route"] == "golden-repository-conversion"
    assert res["overall_decision"] == GateDecision.PASS
    assert len(res["cases"]) == 6
    for case_id, case_result in res["cases"].items():
        assert case_result["decision"] == GateDecision.PASS, f"Failed case: {case_id}"


def test_repository_requirement_oracle_rejects_counterexamples():
    oracle = RepositoryRequirementOracle()

    # BigDecimal to float64 lossy mapping rejection
    dec, msg = oracle.evaluate_repository_conversion(
        source_language="java",
        target_language="go",
        type_mappings={"java.math.BigDecimal": "float64"},
        unit_tests_passed=True,
        dependency_assembly_passed=True,
        unsupported_native_semantics=[],
    )
    assert dec == GateDecision.FAIL
    assert "LOSSY_DECIMAL_OBLIGATION_VIOLATION" in msg

    # Assembly failure rejection
    dec2, msg2 = oracle.evaluate_repository_conversion(
        source_language="java",
        target_language="go",
        type_mappings={},
        unit_tests_passed=True,
        dependency_assembly_passed=False,
        unsupported_native_semantics=[],
    )
    assert dec2 == GateDecision.FAIL
    assert "REPOSITORY_ASSEMBLY_FAILED" in msg2

    # Unsupported native FFI rejection
    dec3, msg3 = oracle.evaluate_repository_conversion(
        source_language="c",
        target_language="rust",
        type_mappings={},
        unit_tests_passed=True,
        dependency_assembly_passed=True,
        unsupported_native_semantics=["unsupported_ioctl_syscall"],
    )
    assert dec3 == GateDecision.FAIL
    assert "UNSUPPORTED_SEMANTICS" in msg3

    # Permissive types rejection
    dec4, msg4 = oracle.evaluate_repository_conversion(
        source_language="java",
        target_language="typescript",
        type_mappings={},
        unit_tests_passed=True,
        dependency_assembly_passed=True,
        unsupported_native_semantics=[],
        has_permissive_types=True,
    )
    assert dec4 == GateDecision.FAIL
    assert "PERMISSIVE_TYPES_PROHIBITED" in msg4


def test_dispatcher_b04_skills():
    for skill_name in (
        "elmos-assurance-sql-domain",
        "elmos-assurance-spring-domain",
        "elmos-assurance-repository-domain",
    ):
        res = dispatch_assurance_skill(skill_name, {})
        assert res["status"] == "PASS"
        assert "results" in res
        assert res["results"]["overall_decision"] == GateDecision.PASS


def test_orchestrator_vertical_slice_includes_b04():
    orch = AssuranceOrchestrator()
    report = orch.run_vertical_slice({
        "tenant_id": "tenant-test",
        "project_id": "proj-test",
        "run_id": "run-test-b04",
    })
    assert report["overall_status"] == "PASS"
    assert report["slice"] == "B00-B04"
    assert "B00" in report["batches"]
    assert "B01" in report["batches"]
    assert "B02" in report["batches"]
    assert "B03" in report["batches"]
    assert "B04" in report["batches"]
    assert report["batches"]["B04"]["status"] == "PASS"
    assert report["batches"]["B04"]["routes"]["sql-conversion"]["status"] == "PASS"
    assert report["batches"]["B04"]["routes"]["spring-modernization"]["status"] == "PASS"
    assert report["batches"]["B04"]["routes"]["repository-conversion"]["status"] == "PASS"
