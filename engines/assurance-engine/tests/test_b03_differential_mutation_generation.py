"""Tests for B03: Differential runtime, mutation auditor, and first Golden Route (project-generation)."""


from elmos_assurance_engine.contracts import GateDecision
from elmos_assurance_engine.differential import TypedDifferentialComparator
from elmos_assurance_engine.generation_domain import (
    ProjectGenerationRouteRunner,
)
from elmos_assurance_engine.mutation_auditor import Mutant, MutationAuditor
from elmos_assurance_engine.property_fuzz import PropertyVerifier


def test_b03_typed_differential_strictness():
    # Exact match
    left = [{"id": "1", "qty": 10, "code": "A"}]
    right = [{"id": "1", "qty": 10, "code": "A"}]
    dec, reasons = TypedDifferentialComparator.compare_rows(left, right, "id")
    assert dec == GateDecision.PASS

    # Prohibit floats in comparison
    left_float = [{"id": "1", "amount": 10.5}]
    right_float = [{"id": "1", "amount": 10.5}]
    dec_float, reasons_float = TypedDifferentialComparator.compare_rows(left_float, right_float, "id")
    assert dec_float == GateDecision.FAIL
    assert any("FLOAT_PROHIBITED" in r for r in reasons_float)

    # Row count mismatch
    dec_count, reasons_count = TypedDifferentialComparator.compare_rows(left, [], "id")
    assert dec_count == GateDecision.FAIL
    assert any("ROW_COUNT_MISMATCH" in r for r in reasons_count)


def test_b03_mutation_auditor_flags_surviving_mutants():
    mutants = [
        Mutant("m-killed", "rule-1", "test mutant", lambda x: True),
        Mutant("m-survived", "rule-2", "critical bypass", lambda x: True),
    ]
    # Test suite kills m-killed but fails to catch m-survived
    report = MutationAuditor.audit_test_suite(mutants, test_evaluator=lambda m: m.mutant_id == "m-killed")
    assert report.verdict == GateDecision.FAIL
    assert "m-survived" in report.survived_mutant_ids
    assert report.killed_mutants == 1
    assert report.total_mutants == 2


def test_b03_property_verifier_conservation_and_idempotency():
    # Idempotency
    dec, _ = PropertyVerifier.verify_idempotency(lambda x: x.strip().lower(), ["  HELLO  ", "world "])
    assert dec == GateDecision.PASS

    # Conservation
    def transfer(accts, src, dst, amt):
        new_a = dict(accts)
        new_a[src] -= amt
        new_a[dst] += amt
        return new_a

    accounts = {"user-1": 1000, "user-2": 500}
    dec_cons, _ = PropertyVerifier.verify_conservation(transfer, accounts, "user-1", "user-2", 200)
    assert dec_cons == GateDecision.PASS


def test_b03_native_golden_route_project_generation_gen_001_to_006():
    """Validates complete native execution of project-generation Golden Route."""
    res = ProjectGenerationRouteRunner.run_all()
    assert res["domain"] == "project-generation"
    assert res["golden_route"] == "golden-project-generation"
    assert res["overall_decision"] == GateDecision.PASS

    # Check all 6 cases
    for case_id in ["GEN-001", "GEN-002", "GEN-003", "GEN-004", "GEN-005", "GEN-006"]:
        assert case_id in res["cases"]
        assert res["cases"][case_id]["decision"] == GateDecision.PASS

    # Crucial rule: other 3 domains must remain strictly NOT_RUN, never falsely claimed
    assert res["other_domains_status"]["sql-conversion"] == "NOT_RUN"
    assert res["other_domains_status"]["spring-modernization"] == "NOT_RUN"
    assert res["other_domains_status"]["repository-conversion"] == "NOT_RUN"
