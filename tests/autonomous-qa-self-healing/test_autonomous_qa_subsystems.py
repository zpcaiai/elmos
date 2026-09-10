"""Test suite for Autonomous QA Subsystems."""

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
ENGINE_PATH = ROOT / "engines/autonomous-qa-engine/src"
if str(ENGINE_PATH) not in sys.path:
    sys.path.insert(0, str(ENGINE_PATH))

from elmos_autonomous_qa.subsystems.spec_normalization_engine import SpecNormalizationEngine
from elmos_autonomous_qa.subsystems.traceability_matrix_engine import TraceabilityMatrixEngine
from elmos_autonomous_qa.subsystems.test_dsl_compiler import TestDSLCompiler
from elmos_autonomous_qa.subsystems.functional_test_engine import FunctionalTestEngine
from elmos_autonomous_qa.subsystems.api_contract_testing_engine import APIContractTestingEngine
from elmos_autonomous_qa.subsystems.database_test_engine import DatabaseTestEngine
from elmos_autonomous_qa.subsystems.workflow_message_test_engine import WorkflowMessageTestEngine
from elmos_autonomous_qa.subsystems.ui_e2e_testing_engine import UIE2ETestingEngine
from elmos_autonomous_qa.subsystems.visual_regression_engine import VisualRegressionEngine
from elmos_autonomous_qa.subsystems.a11y_compliance_engine import A11yComplianceEngine
from elmos_autonomous_qa.subsystems.performance_stress_engine import PerformanceStressEngine
from elmos_autonomous_qa.subsystems.security_abuse_fuzz_engine import SecurityAbuseFuzzEngine
from elmos_autonomous_qa.subsystems.chaos_fault_injection_engine import ChaosFaultInjectionEngine
from elmos_autonomous_qa.subsystems.test_data_synthesis_engine import TestDataSynthesisEngine
from elmos_autonomous_qa.subsystems.distributed_runner_engine import DistributedRunnerEngine
from elmos_autonomous_qa.subsystems.flaky_test_bisect_engine import FlakyTestBisectEngine
from elmos_autonomous_qa.subsystems.ast_mutation_testing_engine import ASTMutationTestingEngine


class AutonomousQASubsystemsTests(unittest.TestCase):
    def test_spec_normalization_engine(self) -> None:
        engine = SpecNormalizationEngine("tenant-qa-01")
        rec = engine.process_domain_slice_1({"id": "SPEC-01", "name": "OpenAPI_Users", "score": 9.5})
        self.assertEqual(rec.status, "ACTIVE")
        self.assertTrue(rec.is_valid)
        self.assertTrue(engine.get_audit_merkle_root().startswith("sha256:"))

    def test_traceability_and_test_dsl(self) -> None:
        trace_eng = TraceabilityMatrixEngine("tenant-qa-01")
        dsl_eng = TestDSLCompiler("tenant-qa-01")
        t_rec = trace_eng.process_domain_slice_2({"id": "REQ-02", "name": "AuthRequirement"})
        d_rec = dsl_eng.process_domain_slice_3({"id": "DSL-03", "name": "LoginScenario"})
        self.assertTrue(t_rec.is_valid)
        self.assertTrue(d_rec.is_valid)

    def test_functional_and_api_contract_engines(self) -> None:
        fn_eng = FunctionalTestEngine("tenant-qa-01")
        api_eng = APIContractTestingEngine("tenant-qa-01")
        fn_rec = fn_eng.process_domain_slice_4({"id": "FN-04", "name": "BoundaryTest"})
        api_rec = api_eng.process_domain_slice_5({"id": "API-05", "name": "PactContract"})
        self.assertTrue(fn_rec.is_valid)
        self.assertTrue(api_rec.is_valid)

    def test_security_and_chaos_engines(self) -> None:
        sec_eng = SecurityAbuseFuzzEngine("tenant-qa-01")
        chaos_eng = ChaosFaultInjectionEngine("tenant-qa-01")
        s_rec = sec_eng.process_domain_slice_12({"id": "SEC-12", "name": "SQLi_Payload"})
        c_rec = chaos_eng.process_domain_slice_13({"id": "CHAOS-13", "name": "PartitionTest"})
        self.assertTrue(s_rec.is_valid)
        self.assertTrue(c_rec.is_valid)

    def test_database_and_workflow_engines(self) -> None:
        db_eng = DatabaseTestEngine("tenant-qa-01")
        wf_eng = WorkflowMessageTestEngine("tenant-qa-01")
        db_rec = db_eng.process_domain_slice_6({"id": "DB-06", "name": "MigrationRollback"})
        wf_rec = wf_eng.process_domain_slice_7({"id": "WF-07", "name": "KafkaOrderTopic"})
        self.assertTrue(db_rec.is_valid)
        self.assertTrue(wf_rec.is_valid)


if __name__ == "__main__":
    unittest.main()
