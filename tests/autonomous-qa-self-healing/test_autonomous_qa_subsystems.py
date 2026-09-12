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
- Requirement traceability graph, transitive closure, gap analysis, and Mermaid export
- Declarative Test DSL lexer, parser, and polyglot code generation (unittest, pytest, Go)
- Functional Boundary Value Analysis (BVA 7-point) and Decision Table completeness
- Distributed message ordering validation and Saga compensating state machines
- UI E2E Page Object Model resilient multi-tier selector resolution
- Visual regression geometry IoU bounding box diffing and layout shift scoring
- Performance stress latency percentiles, Little's Law, and OLS memory leak regression
- OWASP Top 10 security mutation payloads and sanitizer audit
- Relational schema topological DAG dependency ordering and PII pseudonymization
- Consistent hash ring sharding and Longest Processing Time (LPT) makespan scheduling
"""

import ast
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
    TraceabilityMatrixEngine,
    TestDSLCompiler,
    FunctionalTestEngine,
    DecisionRule,
    WorkflowMessageTestEngine,
    MessageEvent,
    SagaStep,
    UIE2ETestingEngine,
    UIElementSelector,
    UIJourneyStep,
    VisualRegressionEngine,
    BoundingBox,
    PerformanceStressEngine,
    SecurityAbuseFuzzEngine,
    TestDataSynthesisEngine,
    TableSchema,
    ForeignKeyConstraint,
    DistributedRunnerEngine,
    ConsistentHashRing,
    TestJob,
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
        self.assertLessEqual(len(covering_array.test_cases), 12)
        self.assertEqual(covering_array.coverage_ratio, 100.0)
        self.assertEqual(covering_array.covered_pairs, covering_array.total_pairs)

        for tc in covering_array.test_cases:
            self.assertIn("OS", tc)
            self.assertIn("Browser", tc)
            self.assertIn("Env", tc)

    def test_pairwise_with_constraints(self) -> None:
        parameters = {
            "OS": ["Linux", "Windows"],
            "Browser": ["Chrome", "Safari"],
        }
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
        self.assertGreaterEqual(len(mutants), 3)

        operators = {m.operator_kind for m in mutants}
        self.assertIn("ROR", operators)
        self.assertIn("COR", operators)
        self.assertIn("AOR", operators)

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

        val_res = APIContractTestingEngine.validate_instance(schema, {"username": "bob", "age": 30})
        self.assertTrue(val_res.is_valid)

        invalid_res = APIContractTestingEngine.validate_instance(schema, {"age": 25})
        self.assertFalse(invalid_res.is_valid)
        self.assertIn("Missing required field: username", invalid_res.errors)

    def test_wcag_contrast_ratio_evaluation(self) -> None:
        black = (0, 0, 0)
        white = (255, 255, 255)
        res_bw = WCAGA11yComplianceEngine.calculate_contrast_ratio(black, white)
        self.assertEqual(res_bw.contrast_ratio, 21.0)
        self.assertTrue(res_bw.passes_aa_normal)
        self.assertTrue(res_bw.passes_aaa_normal)

        res_ww = WCAGA11yComplianceEngine.calculate_contrast_ratio(white, white)
        self.assertEqual(res_ww.contrast_ratio, 1.0)
        self.assertFalse(res_ww.passes_aa_normal)

        skipped_headings = [1, 2, 4]
        heading_violations = WCAGA11yComplianceEngine.audit_headings(skipped_headings)
        self.assertEqual(len(heading_violations), 1)
        self.assertIn("Skipped heading level: h2 -> h4", heading_violations[0])

        bad_elements = [
            {"tag": "div", "role": "super_button"},
            {"tag": "button", "role": "button"},
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
            {"id": 2, "name": "Beta", "balance": 999.0},
            {"id": 3, "name": "Gamma", "balance": 50.0},
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
        results = [True, True, False, True, True, False, True, True, False, True]
        report = FlakyTestBisectEngine.evaluate_test_flakiness("test_payment_checkout", results)
        self.assertTrue(report.is_flaky)
        self.assertEqual(report.pass_count, 7)
        self.assertEqual(report.fail_count, 3)
        self.assertEqual(report.flakiness_ratio, 0.3)
        self.assertGreater(report.confidence_interval[1], report.confidence_interval[0])

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

    def test_traceability_matrix_graph_and_gap_analysis(self) -> None:
        engine = TraceabilityMatrixEngine()
        engine.add_node("REQ-101", "REQUIREMENT", "User Authentication")
        engine.add_node("REQ-102", "REQUIREMENT", "Password Reset")
        engine.add_node("ARCH-201", "ARCHITECTURE", "OAuth2 Flow")
        engine.add_node("CODE-301", "CODE", "auth_controller.py")
        engine.add_node("TEST-401", "TEST", "test_oauth_login.py")

        engine.add_edge("REQ-101", "ARCH-201", "SATISFIES")
        engine.add_edge("ARCH-201", "CODE-301", "IMPLEMENTS")
        engine.add_edge("TEST-401", "CODE-301", "TESTS")

        forward = engine.get_forward_reachability("REQ-101")
        self.assertIn("ARCH-201", forward)
        self.assertIn("CODE-301", forward)

        untraced = engine.find_untraced_requirements()
        self.assertEqual(untraced, ["REQ-102"])

        report = engine.generate_report()
        self.assertEqual(report.total_requirements, 2)
        self.assertEqual(report.covered_requirements, 1)
        self.assertEqual(report.coverage_ratio, 50.0)
        self.assertEqual(len(report.merkle_root), 64)

        mermaid = engine.export_mermaid()
        self.assertIn("flowchart TD", mermaid)
        self.assertIn("REQ-101", mermaid)
        self.assertIn("-->|SATISFIES|", mermaid)

    def test_test_dsl_compiler_polyglot(self) -> None:
        dsl_source = """
        SCENARIO: Submit Payment Order
        GIVEN Customer account with balance 500
        WHEN POST /orders WITH {"amount": 100}
        THEN ASSERT_STATUS 201
        THEN ASSERT_JSON order.status == "PENDING"
        THEN ASSERT_LATENCY_MS <= 300
        """
        scenario = TestDSLCompiler.parse_dsl(dsl_source)
        self.assertEqual(scenario.name, "Submit Payment Order")
        self.assertEqual(len(scenario.steps), 5)

        # Unittest compilation and python syntax validation
        py_unittest = TestDSLCompiler.compile_to_python_unittest(scenario)
        self.assertIn("class TestSubmitPaymentOrder", py_unittest)
        ast.parse(py_unittest)

        # Pytest compilation and python syntax validation
        py_pytest = TestDSLCompiler.compile_to_pytest(scenario)
        self.assertIn("def test_submit_payment_order():", py_pytest)
        ast.parse(py_pytest)

        # Go compilation validation
        go_code = TestDSLCompiler.compile_to_go(scenario)
        self.assertIn("func TestSubmitPaymentOrder(t *testing.T)", go_code)
        self.assertIn("time.Now()", go_code)

    def test_functional_test_engine_bva_and_decision_tables(self) -> None:
        bva = FunctionalTestEngine.generate_7point_bva("user_age", min_val=18.0, max_val=65.0, nominal_val=40.0)
        self.assertEqual(len(bva.test_points), 7)
        self.assertEqual(bva.test_points, [17.0, 18.0, 19.0, 40.0, 64.0, 65.0, 66.0])
        self.assertEqual(bva.test_labels[0], "MIN_MINUS_1_INVALID")
        self.assertEqual(bva.test_labels[5], "MAX_BOUNDARY_VALID")

        partitions = FunctionalTestEngine.partition_numeric_range(0.0, 100.0)
        self.assertEqual(len(partitions), 3)
        self.assertFalse(partitions[0].is_valid)
        self.assertTrue(partitions[1].is_valid)
        self.assertFalse(partitions[2].is_valid)

        rules = [
            DecisionRule("R1", {"is_admin": True, "has_mfa": True}, {"grant_access": True}),
            DecisionRule("R2", {"is_admin": True, "has_mfa": False}, {"grant_access": False}),
            DecisionRule("R3", {"is_admin": False, "has_mfa": True}, {"grant_access": True}),
            DecisionRule("R4", {"is_admin": False, "has_mfa": False}, {"grant_access": False}),
        ]
        action = FunctionalTestEngine.evaluate_decision_table(rules, {"is_admin": True, "has_mfa": True})
        self.assertEqual(action, {"grant_access": True})

        is_complete, uncovered = FunctionalTestEngine.verify_decision_table_completeness(["is_admin", "has_mfa"], rules)
        self.assertTrue(is_complete)
        self.assertEqual(len(uncovered), 0)

    def test_workflow_message_stream_and_saga(self) -> None:
        events = [
            MessageEvent("msg-1", "orders", 1, {"item": "A"}, "key-1", 100.0),
            MessageEvent("msg-2", "orders", 2, {"item": "B"}, "key-2", 101.0),
            MessageEvent("msg-3", "orders", 3, {"item": "C"}, "key-3", 102.0),
        ]
        rep = WorkflowMessageTestEngine.verify_stream_ordering(events)
        self.assertTrue(rep.is_strictly_ordered)
        self.assertEqual(rep.duplicate_count, 0)
        self.assertEqual(rep.out_of_order_count, 0)

        # Detect out of order and duplicate
        bad_events = [
            MessageEvent("msg-1", "orders", 1, {"item": "A"}, "key-1", 100.0),
            MessageEvent("msg-2", "orders", 3, {"item": "C"}, "key-3", 102.0),
            MessageEvent("msg-1", "orders", 1, {"item": "A"}, "key-1", 100.0),
        ]
        bad_rep = WorkflowMessageTestEngine.verify_stream_ordering(bad_events)
        self.assertFalse(bad_rep.is_strictly_ordered)
        self.assertEqual(bad_rep.duplicate_count, 1)

        # Saga with compensation
        audit_log = []
        steps = [
            SagaStep("ReserveInventory", lambda ctx: audit_log.append("INV_RESERVED") or True, lambda ctx: audit_log.append("INV_RELEASED") or True),
            SagaStep("ChargePayment", lambda ctx: False, lambda ctx: audit_log.append("PAYMENT_REFUNDED") or True),
        ]
        res = WorkflowMessageTestEngine.execute_saga(steps, {})
        self.assertFalse(res.is_success)
        self.assertEqual(res.failed_step, "ChargePayment")
        self.assertEqual(res.compensated_steps, ["ReserveInventory"])
        self.assertTrue(res.compensation_consistent)
        self.assertIn("INV_RELEASED", audit_log)

    def test_ui_e2e_resilient_selector_journey(self) -> None:
        dom = {
            "testids": {"login-btn": True},
            "roles": {"main": True},
            "labels": {"Submit": True},
            "css": {".btn-primary": True},
            "texts": {"login-btn": "Sign In"},
        }
        selector = UIElementSelector(element_id="submit_btn", data_testid="login-btn", css_selector=".btn-primary")
        target, tier = selector.resolve_selector(dom)
        self.assertEqual(tier, "DATA_TESTID")
        self.assertEqual(target, "login-btn")

        steps = [
            UIJourneyStep(step_id="s1", action_type="CLICK", selector=selector),
            UIJourneyStep(step_id="s2", action_type="ASSERT_TEXT", selector=selector, expected_value="Sign In"),
        ]
        journey_rep = UIE2ETestingEngine.execute_journey("UserLoginJourney", steps, dom)
        self.assertTrue(journey_rep.passed)
        self.assertEqual(journey_rep.executed_steps, 2)
        self.assertEqual(len(journey_rep.session_merkle), 64)

    def test_visual_regression_geometry_diff(self) -> None:
        box_a = BoundingBox(10.0, 10.0, 100.0, 50.0)
        box_b = BoundingBox(10.0, 10.0, 100.0, 50.0)
        self.assertEqual(box_a.iou(box_b), 1.0)

        box_shifted = BoundingBox(60.0, 10.0, 100.0, 50.0)  # 50px overlap
        self.assertLess(box_a.iou(box_shifted), 1.0)
        self.assertGreater(box_a.iou(box_shifted), 0.0)

        baseline = {"card-1": (box_a, {"color": "red", "font-size": "14px"})}
        candidate = {"card-1": (box_shifted, {"color": "blue", "font-size": "14px"})}

        diff = VisualRegressionEngine.diff_layouts(baseline, candidate)
        self.assertFalse(diff.is_identical)
        self.assertIn("card-1", diff.css_mismatches)
        self.assertEqual(diff.css_mismatches["card-1"]["color"], ("red", "blue"))

    def test_performance_stress_percentiles_and_memory_leak(self) -> None:
        latencies = [10.0, 12.0, 15.0, 18.0, 20.0, 25.0, 30.0, 45.0, 100.0, 200.0]
        p = PerformanceStressEngine.calculate_percentiles(latencies)
        self.assertEqual(p.min_ms, 10.0)
        self.assertEqual(p.max_ms, 200.0)
        self.assertLessEqual(p.p50_ms, p.p90_ms)
        self.assertLessEqual(p.p90_ms, p.p99_ms)

        # Little's Law: L = 10, lambda = 100 req/s, W = 0.1s -> 10 = 100 * 0.1
        ok, err = PerformanceStressEngine.verify_littles_law(10.0, 100.0, 0.1)
        self.assertTrue(ok)
        self.assertEqual(err, 0.0)

        # Memory leak detection
        timestamps = [0.0, 10.0, 20.0, 30.0, 40.0, 50.0]
        leaking_mem = [1000.0, 25000.0, 50000.0, 75000.0, 100000.0, 125000.0]
        leak_rep = PerformanceStressEngine.detect_memory_leak(timestamps, leaking_mem, leak_threshold_bytes_sec=100.0)
        self.assertTrue(leak_rep.has_memory_leak)
        self.assertGreater(leak_rep.slope_bytes_per_sec, 2000.0)
        self.assertGreater(leak_rep.r_squared, 0.95)

    def test_security_abuse_owasp_payloads_and_sanitizer(self) -> None:
        sqli_payloads = SecurityAbuseFuzzEngine.get_payloads("SQL_INJECTION")
        self.assertGreaterEqual(len(sqli_payloads), 4)

        # Flawed sanitizer that leaves SQL OR unescaped
        def flawed_sanitizer(input_str: str) -> str:
            return input_str.replace("<script>", "")

        vuln_reports = SecurityAbuseFuzzEngine.audit_input_sanitization("test", flawed_sanitizer)
        self.assertGreater(len(vuln_reports), 0)
        found_cats = {v.attack_category for v in vuln_reports}
        self.assertIn("SQL_INJECTION", found_cats)

    def test_test_data_synthesis_relational_dag_and_pii(self) -> None:
        t_users = TableSchema("users", "id", {"id": "int", "email": "str"})
        t_orders = TableSchema(
            "orders",
            "id",
            {"id": "int", "user_id": "int"},
            [ForeignKeyConstraint("user_id", "users", "id")],
        )
        t_items = TableSchema(
            "order_items",
            "id",
            {"id": "int", "order_id": "int"},
            [ForeignKeyConstraint("order_id", "orders", "id")],
        )

        order = TestDataSynthesisEngine.solve_insertion_order([t_items, t_orders, t_users])
        self.assertEqual(order, ["users", "orders", "order_items"])

        # PII Masking
        sensitive = "User alice@example.com with phone 555-123-4567 and card 4111-2222-3333-4444"
        masked = TestDataSynthesisEngine.mask_pii(sensitive)
        self.assertNotIn("alice@example.com", masked)
        self.assertIn("@example.com", masked)
        self.assertIn("user_", masked)
        self.assertNotIn("4111-2222-3333-4444", masked)
        self.assertIn("4444", masked)

    def test_distributed_runner_consistent_hash_and_lpt(self) -> None:
        ring = ConsistentHashRing(replicas=50)
        ring.add_node("worker-1")
        ring.add_node("worker-2")
        ring.add_node("worker-3")

        node_a = ring.get_node("test_auth_login")
        node_b = ring.get_node("test_checkout_flow")
        self.assertIn(node_a, {"worker-1", "worker-2", "worker-3"})
        self.assertIn(node_b, {"worker-1", "worker-2", "worker-3"})

        # LPT greedy scheduling
        jobs = [
            TestJob("test_fast_1", 1.0),
            TestJob("test_slow_1", 10.0),
            TestJob("test_mid_1", 5.0),
            TestJob("test_mid_2", 4.0),
        ]
        queues, loads = DistributedRunnerEngine.schedule_lpt(jobs, worker_count=2)
        self.assertEqual(len(queues), 2)
        self.assertEqual(sum(loads), 20.0)
        # Difference between worker loads should be at most 2.0
        self.assertLessEqual(abs(loads[0] - loads[1]), 2.0)


if __name__ == "__main__":
    unittest.main()
