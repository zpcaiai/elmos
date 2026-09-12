import sys
from pathlib import Path
import unittest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from elmos_mature_platform.cross_region_simulation import CrossRegionSimulationEnvironment
from elmos_mature_platform.chaos_fault_engine import EnterpriseChaosEngine
from elmos_mature_platform.kms_service import EnterpriseKmsService
from elmos_mature_platform.slo_telemetry_pipeline import EnterpriseSloCollector
from elmos_mature_platform.disaster_recovery_runner import DisasterRecoveryRunner
from elmos_mature_platform.oidc_service import EnterpriseOidcProvider
from elmos_mature_platform.scenarios.batch38_deployment import execute_batch38_case
from elmos_mature_platform.scenarios.batch39_sre import execute_batch39_case
from elmos_mature_platform.types import RegionId, FaultType, FaultDescriptor


class TestBatch38DeploymentScenarios(unittest.TestCase):
    """Integration tests for Batch 38 Deployment & Upgrade Matrix Scenarios."""

    def setUp(self) -> None:
        self.sim = CrossRegionSimulationEnvironment()
        self.oidc = EnterpriseOidcProvider()
        self.kms = EnterpriseKmsService()
        self.dr = DisasterRecoveryRunner(self.sim)
        self.trace_log: list[str] = []

    def _trace(self, msg: str) -> None:
        self.trace_log.append(msg)

    def _run(self, case_id: str, category: str) -> list:
        meta = {"case_id": case_id, "category": category}
        assertions, _ = execute_batch38_case(
            meta, self.sim, self.oidc, self.kms, self.dr, self._trace
        )
        return assertions

    def test_b38_001_multi_tenant_saas(self) -> None:
        assertions = self._run("B38-001", "success")
        self.assertTrue(any("Multi-tenant isolation verified" in a.details for a in assertions))
        for a in assertions:
            self.assertTrue(a.passed)
        self.assertTrue(any("Cluster control plane bound to active leader:" in msg for msg in self.trace_log))

    def test_b38_002_air_gapped_deployment(self) -> None:
        assertions = self._run("B38-002", "success")
        self.assertTrue(any("Offline bundle signature verified" in a.details for a in assertions))
        for a in assertions:
            self.assertTrue(a.passed)
            
    def test_b38_003_expand_contract_migration(self) -> None:
        assertions = self._run("B38-003", "success")
        self.assertTrue(any("Database schema transitioned" in a.details for a in assertions))
        for a in assertions:
            self.assertTrue(a.passed)
        self.assertTrue(any("Migration Phase" in msg for msg in self.trace_log))

    def test_b38_004_canary_upgrade(self) -> None:
        assertions = self._run("B38-004", "success")
        for a in assertions:
            self.assertTrue(a.passed)

    def test_b38_005_canary_rollback(self) -> None:
        assertions = self._run("B38-005", "success")
        for a in assertions:
            self.assertTrue(a.passed)

    def test_b38_006_edge_sync(self) -> None:
        assertions = self._run("B38-006", "success")
        for a in assertions:
            self.assertTrue(a.passed)

    def test_b38_007_mixed_version_compat(self) -> None:
        assertions = self._run("B38-007", "success")
        for a in assertions:
            self.assertTrue(a.passed)
            
    def test_b38_008_fallback_case(self) -> None:
        assertions = self._run("B38-008", "success")
        for a in assertions:
            self.assertTrue(a.passed)

    def test_b38_009_multi_tenant_saas(self) -> None:
        assertions = self._run("B38-009", "success")
        for a in assertions:
            self.assertTrue(a.passed)

    def test_b38_010_air_gapped_deployment(self) -> None:
        assertions = self._run("B38-010", "success")
        for a in assertions:
            self.assertTrue(a.passed)


class TestBatch39SreScenarios(unittest.TestCase):
    """Integration tests for Batch 39 Global SRE & Operations Scenarios."""

    def setUp(self) -> None:
        self.sim = CrossRegionSimulationEnvironment()
        self.chaos = EnterpriseChaosEngine(self.sim)
        self.dr = DisasterRecoveryRunner(self.sim)
        self.slo = EnterpriseSloCollector()
        self.trace_log: list[str] = []

    def _trace(self, msg: str) -> None:
        self.trace_log.append(msg)

    def _run(self, case_id: str, category: str) -> list:
        meta = {"case_id": case_id, "category": category}
        assertions, _ = execute_batch39_case(
            meta, self.sim, self.chaos, self.slo, self.dr, self._trace
        )
        return assertions

    def test_b39_001_chaos_failover(self) -> None:
        assertions = self._run("B39-001", "success")
        for a in assertions:
            self.assertTrue(a.passed)
        self.assertTrue(any("Chaos Injected:" in msg for msg in self.trace_log))
        self.assertTrue(any("Secondary region promoted to leader" in a.details for a in assertions))

    def test_b39_002_pitr_reconciliation(self) -> None:
        assertions = self._run("B39-002", "success")
        self.assertTrue(any("Restored state matches snapshot" in a.details for a in assertions))
        for a in assertions:
            self.assertTrue(a.passed)

    def test_b39_003_slo_burn_rate(self) -> None:
        assertions = self._run("B39-003", "success")
        for a in assertions:
            self.assertTrue(a.passed)
        self.assertTrue(any("SLO Status" in msg for msg in self.trace_log))

    def test_b39_004_autoscaling(self) -> None:
        assertions = self._run("B39-004", "success")
        for a in assertions:
            self.assertTrue(a.passed)

    def test_b39_005_oncall_pager(self) -> None:
        assertions = self._run("B39-005", "success")
        for a in assertions:
            self.assertTrue(a.passed)

    def test_b39_006_fallback_case(self) -> None:
        assertions = self._run("B39-006", "success")
        for a in assertions:
            self.assertTrue(a.passed)

    def test_b39_009_chaos_failover(self) -> None:
        assertions = self._run("B39-009", "success")
        for a in assertions:
            self.assertTrue(a.passed)

    def test_b39_010_pitr_reconciliation(self) -> None:
        assertions = self._run("B39-010", "success")
        for a in assertions:
            self.assertTrue(a.passed)

    def test_b39_011_slo_burn_rate(self) -> None:
        assertions = self._run("B39-011", "success")
        for a in assertions:
            self.assertTrue(a.passed)

    def test_b39_012_autoscaling(self) -> None:
        assertions = self._run("B39-012", "success")
        for a in assertions:
            self.assertTrue(a.passed)

    def test_b39_013_oncall_pager(self) -> None:
        assertions = self._run("B39-013", "success")
        for a in assertions:
            self.assertTrue(a.passed)

if __name__ == "__main__":
    unittest.main()
