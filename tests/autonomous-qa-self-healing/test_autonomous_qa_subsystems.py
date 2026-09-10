"""Industrial Unit Test Suite for Autonomous QA Subsystems.

Tests genuine domain algorithms:
- OpenAPI and Gherkin specification normalization
- In-Parameter-Order (IPO) pairwise covering array generation with constraints
- AST operator mutation (AOR, ROR, COR) and mutation score kill evaluation
- API schema validation and boundary fuzz payload synthesis
- WCAG 2.2 relative luminance and color contrast ratio calculations
- ARIA hierarchy and heading level auditing
- Database row-level cryptographic state diffing
- Wilson score interval statistical flakiness detection
- Chaos fault injection and circuit breaker state machines
"""

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
ENGINE_PATH = ROOT / "engines/autonomous-qa-engine/src"
if str(ENGINE_PATH) not in sys.path:
    sys.path.insert(0, str(ENGINE_PATH))

from elmos_autonomous_qa.subsystems import (
    SpecNormalizationEngine,
    PairwiseCombinatorialEngine,
    ASTMutationTestingEngine,
    APIContractTestingEngine,
    WCAGA11yComplianceEngine,
    DBStateVerificationEngine,
    FlakyTestBisectEngine,
    ChaosFaultInjectionEngine,
)


class AutonomousQASubsystemsTests(unittest.TestCase):
    def test_spec_normalization_openapi(self) -> None:
        raw_openapi = {
            "info": {"title": "Order Management API", "version": "2.1.0"},
            "paths": {
                "/orders/{order_id}": {
                    "get": {
                        "operationId": "getOrderById",
                        "summary": "Fetch order by ID",
                        "tags": ["orders"],
                        "parameters": [
                            {
                                "name": "order_id",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "string"},
                            }
                        ],
                        "responses": {
                            "200": {"description": "Success"},
                            "404": {"description": "Not Found"},
                        },
                    },
                    "delete": {
                        "operationId": "deleteOrder",
                        "summary": "Cancel order",
                        "responses": {"204": {"description": "Deleted"}},
                    },
                }
            },
        }
        spec = SpecNormalizationEngine.normalize_openapi(raw_openapi)
        self.assertEqual(spec.source_type, "OPENAPI")
        self.assertEqual(spec.title, "Order Management API")
        self.assertEqual(len(spec.endpoints), 2)

        get_ep = [ep for ep in spec.endpoints if ep.method == "GET"][0]
        self.assertEqual(get_ep.endpoint_id, "getOrderById")
        self.assertEqual(len(get_ep.parameters), 1)
        self.assertTrue(get_ep.parameters[0].required)
        self.assertIn(200, get_ep.responses)
        self.assertGreater(spec.completeness_score, 50.0)
        self.assertEqual(len(spec.compute_merkle_root()), 64)

    def test_spec_normalization_gherkin(self) -> None:
        gherkin_doc = """
        Feature: User Authentication
            Scenario: Successful login with valid credentials
                Given a registered user with email "alice@example.com"
                When the user submits valid password
                Then the response status code should be 200
                And an auth token should be returned
        """
        spec = SpecNormalizationEngine.normalize_gherkin(gherkin_doc)
        self.assertEqual(spec.source_type, "GHERKIN")
        self.assertEqual(spec.title, "User Authentication")
        self.assertEqual(len(spec.scenarios), 1)
        sc = spec.scenarios[0]
        self.assertEqual(sc.scenario_title, "Successful login with valid credentials")
        self.assertEqual(len(sc.given_steps), 1)
        self.assertEqual(len(sc.when_steps), 1)
        self.assertEqual(len(sc.then_steps), 2)
        self.assertTrue(sc.is_executable())

    def test_pairwise_combinatorial_ipo(self) -> None:
        parameters = {
            "OS": ["Linux", "macOS", "Windows"],
            "Browser": ["Chrome", "Firefox", "Safari"],
            "Env": ["Staging", "Production"],
        }
        covering_array = PairwiseCombinatorialEngine.generate_pairwise(parameters)
        self.assertGreater(len(covering_array.test_cases), 0)
        self.assertLessEqual(len(covering_array.test_cases), 12)  # Much smaller than 3x3x2=18
        self.assertEqual(covering_array.coverage_ratio, 100.0)
        self.assertEqual(covering_array.covered_pairs, covering_array.total_pairs)

        # Assert every generated test case has all parameters
        for tc in covering_array.test_cases:
            self.assertIn("OS", tc)
            self.assertIn("Browser", tc)
            self.assertIn("Env", tc)

    def test_pairwise_with_constraints(self) -> None:
        parameters = {
            "OS": ["Linux", "Windows"],
            "Browser": ["Chrome", "Safari"],
        }
        # Constraint: Safari is only allowed on macOS (so never on Linux or Windows)
        constraints = [
            lambda tc: not (tc.get("Browser") == "Safari"),
        ]
        covering_array = PairwiseCombinatorialEngine.generate_pairwise(parameters, constraints)
        for tc in covering_array.test_cases:
            self.assertNotEqual(tc.get("Browser"), "Safari")

    def test_ast_mutation_testing_engine(self) -> None:
        sample_code = """
def compute_discount(price, is_member):
    if price > 100 and is_member:
        return price - 20
    return price
"""
        mutants = ASTMutationTestingEngine.generate_mutants(sample_code)
        self.assertGreaterEqual(len(mutants), 3)  # ROR (price > 100), COR (and), AOR (price - 20)

        operators = {m.operator_kind for m in mutants}
        self.assertIn("ROR", operators)
        self.assertIn("COR", operators)
        self.assertIn("AOR", operators)

        # Test runner that checks if compute_discount(150, True) == 130
        def test_runner(code_str: str) -> bool:
            local_scope = {}
            exec(code_str, {}, local_scope)
            fn = local_scope["compute_discount"]
            try:
                return fn(150, True) == 130 and fn(50, True) == 50
            except Exception:
                return False

        report = ASTMutationTestingEngine.evaluate_mutants(mutants, test_runner)
        self.assertEqual(report.total_mutants, len(mutants))
        self.assertGreater(report.killed_mutants, 0)
        self.assertGreater(report.mutation_score, 0.0)

    def test_api_contract_fuzz_payloads(self) -> None:
        schema = {
            "type": "object",
            "required": ["username", "age"],
            "properties": {
                "username": {"type": "string"},
                "age": {"type": "integer"},
                "active": {"type": "boolean"},
            },
        }
        payloads = APIContractTestingEngine.synthesize_boundary_payloads(schema)
        self.assertGreaterEqual(len(payloads), 6)

        categories = {p.fuzz_category for p in payloads}
        self.assertIn("SQL_INJECTION", categories)
        self.assertIn("BOUNDARY_INTEGER", categories)
        self.assertIn("XSS", categories)

        # Valid instance
        val_res = APIContractTestingEngine.validate_instance(schema, {"username": "bob", "age": 30})
        self.assertTrue(val_res.is_valid)

        # Missing required field
        invalid_res = APIContractTestingEngine.validate_instance(schema, {"age": 25})
        self.assertFalse(invalid_res.is_valid)
        self.assertIn("Missing required field: username", invalid_res.errors)

    def test_wcag_contrast_ratio_evaluation(self) -> None:
        # Black (#000000) on White (#FFFFFF) -> 21.0:1
        black = (0, 0, 0)
        white = (255, 255, 255)
        res_bw = WCAGA11yComplianceEngine.calculate_contrast_ratio(black, white)
        self.assertEqual(res_bw.contrast_ratio, 21.0)
        self.assertTrue(res_bw.passes_aa_normal)
        self.assertTrue(res_bw.passes_aaa_normal)

        # White on White -> 1.0:1
        res_ww = WCAGA11yComplianceEngine.calculate_contrast_ratio(white, white)
        self.assertEqual(res_ww.contrast_ratio, 1.0)
        self.assertFalse(res_ww.passes_aa_normal)

        # Heading audit
        skipped_headings = [1, 2, 4]  # Skipped h3
        heading_violations = WCAGA11yComplianceEngine.audit_headings(skipped_headings)
        self.assertEqual(len(heading_violations), 1)
        self.assertIn("Skipped heading level: h2 -> h4", heading_violations[0])

        # ARIA audit
        bad_elements = [
            {"tag": "div", "role": "super_button"},  # Invalid role
            {"tag": "button", "role": "button"},  # Missing name
        ]
        aria_violations = WCAGA11yComplianceEngine.audit_aria_roles(bad_elements)
        self.assertEqual(len(aria_violations), 2)

    def test_db_state_verification_differential(self) -> None:
        source_rows = [
            {"id": 1, "name": "Alpha", "balance": 100.0},
            {"id": 2, "name": "Beta", "balance": 250.5},
        ]
        target_rows = [
            {"id": 1, "name": "Alpha", "balance": 100.0},
            {"id": 2, "name": "Beta", "balance": 999.0},  # Divergence
            {"id": 3, "name": "Gamma", "balance": 50.0},  # Extra in target
        ]
        diff_res = DBStateVerificationEngine.compare_tables("accounts", "id", source_rows, target_rows)
        self.assertFalse(diff_res.is_bit_identical)
        self.assertEqual(diff_res.source_row_count, 2)
        self.assertEqual(diff_res.target_row_count, 3)
        self.assertEqual(diff_res.divergent_row_count, 2)

        types = {d.divergence_type for d in diff_res.divergences}
        self.assertIn("COLUMN_MISMATCH", types)
        self.assertIn("EXTRA_IN_TARGET", types)

    def test_flaky_test_wilson_score_interval(self) -> None:
        # Flaky test with 7 passes and 3 fails out of 10 runs
        results = [True, True, False, True, True, False, True, True, False, True]
        report = FlakyTestBisectEngine.evaluate_test_flakiness("test_payment_checkout", results)
        self.assertTrue(report.is_flaky)
        self.assertEqual(report.pass_count, 7)
        self.assertEqual(report.fail_count, 3)
        self.assertEqual(report.flakiness_ratio, 0.3)
        self.assertGreater(report.confidence_interval[1], report.confidence_interval[0])

        # Solid passing test
        solid_results = [True] * 20
        solid_report = FlakyTestBisectEngine.evaluate_test_flakiness("test_health_ping", solid_results)
        self.assertFalse(solid_report.is_flaky)
        self.assertEqual(solid_report.fail_count, 0)

    def test_chaos_fault_injection_circuit_breaker(self) -> None:
        calls = 0
        fallback_calls = 0

        def service_call():
            nonlocal calls
            calls += 1
            return "OK"

        def fallback():
            nonlocal fallback_calls
            fallback_calls += 1
            return "DEGRADED"

        res = ChaosFaultInjectionEngine.execute_with_fault_injection(
            total_requests=20,
            fault_rate=0.5,
            target_function=service_call,
            fallback_function=fallback,
        )
        self.assertEqual(res.total_calls, 20)
        self.assertGreater(res.fallback_calls, 0)
        self.assertTrue(res.circuit_breaker_opened)
        self.assertGreater(res.resilience_score, 80.0)


if __name__ == "__main__":
    unittest.main()
