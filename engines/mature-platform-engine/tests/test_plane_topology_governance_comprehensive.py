import unittest
from typing import List

from elmos_mature_platform.types import (
    PlaneFunction,
    PlaneIsolation,
    PlaneDefinition,
    PlaneGovernanceTopology as PlaneTopology,
    PlaneViolation
)
from elmos_mature_platform.plane_topology_governance_engine import PlaneTopologyGovernanceEngine

class TestPlaneTopologyGovernanceComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = PlaneTopologyGovernanceEngine()

    def _create_basic_topology(self, plane_ids: List[str] = None):
        if not plane_ids:
            plane_ids = []
        topology = PlaneTopology(
            topology_id="topo-1",
            name="Basic Topo",
            plane_ids=plane_ids
        )
        return self.engine.create_topology(topology)

    def test_01_define_plane_success(self):
        plane = PlaneDefinition(plane_id="p1", name="Plane 1", function=PlaneFunction.CONTROL)
        res = self.engine.define_plane(plane)
        self.assertEqual(res, "p1")
        self.assertIn("p1", self.engine.planes)

    def test_02_create_topology_success(self):
        topo = PlaneTopology(topology_id="t1", name="Topo 1")
        res = self.engine.create_topology(topo)
        self.assertEqual(res, "t1")
        self.assertIn("t1", self.engine.topologies)

    def test_03_add_plane_to_topology(self):
        self.engine.define_plane(PlaneDefinition(plane_id="p1", name="P1", function=PlaneFunction.DATA))
        t_id = self._create_basic_topology()
        self.engine.add_plane_to_topology(t_id, "p1")
        self.assertIn("p1", self.engine.topologies[t_id].plane_ids)

    def test_04_add_plane_to_topology_duplicate(self):
        self.engine.define_plane(PlaneDefinition(plane_id="p1", name="P1", function=PlaneFunction.DATA))
        t_id = self._create_basic_topology()
        self.engine.add_plane_to_topology(t_id, "p1")
        self.engine.add_plane_to_topology(t_id, "p1")
        self.assertEqual(self.engine.topologies[t_id].plane_ids.count("p1"), 1)

    def test_05_add_plane_to_missing_topology(self):
        self.engine.define_plane(PlaneDefinition(plane_id="p1", name="P1", function=PlaneFunction.DATA))
        with self.assertRaises(ValueError):
            self.engine.add_plane_to_topology("invalid-t", "p1")

    def test_06_add_missing_plane_to_topology(self):
        t_id = self._create_basic_topology()
        with self.assertRaises(ValueError):
            self.engine.add_plane_to_topology(t_id, "invalid-p")

    def test_07_validate_dependencies_no_violations(self):
        self.engine.define_plane(PlaneDefinition(plane_id="p1", name="P1", function=PlaneFunction.DATA, allowed_dependencies=["p2"]))
        self.engine.define_plane(PlaneDefinition(plane_id="p2", name="P2", function=PlaneFunction.DATA))
        t_id = self._create_basic_topology(["p1", "p2"])
        violations = self.engine.validate_dependencies(t_id)
        self.assertEqual(len(violations), 0)

    def test_08_validate_dependencies_forbidden(self):
        self.engine.define_plane(PlaneDefinition(plane_id="p1", name="P1", function=PlaneFunction.DATA, allowed_dependencies=["p2"], forbidden_dependencies=["p2"]))
        self.engine.define_plane(PlaneDefinition(plane_id="p2", name="P2", function=PlaneFunction.DATA))
        t_id = self._create_basic_topology(["p1", "p2"])
        violations = self.engine.validate_dependencies(t_id)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].rule, "forbidden_dependency")

    def test_09_validate_dependencies_missing_target(self):
        self.engine.define_plane(PlaneDefinition(plane_id="p1", name="P1", function=PlaneFunction.DATA, allowed_dependencies=["p2"]))
        t_id = self._create_basic_topology(["p1"])
        violations = self.engine.validate_dependencies(t_id)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].rule, "missing_dependency")

    def test_10_detect_circular_dependencies_none(self):
        self.engine.define_plane(PlaneDefinition(plane_id="p1", name="P1", function=PlaneFunction.DATA, allowed_dependencies=["p2"]))
        self.engine.define_plane(PlaneDefinition(plane_id="p2", name="P2", function=PlaneFunction.DATA))
        t_id = self._create_basic_topology(["p1", "p2"])
        violations = self.engine.detect_circular_dependencies(t_id)
        self.assertEqual(len(violations), 0)

    def test_11_detect_circular_dependencies_cycle(self):
        self.engine.define_plane(PlaneDefinition(plane_id="p1", name="P1", function=PlaneFunction.DATA, allowed_dependencies=["p2"]))
        self.engine.define_plane(PlaneDefinition(plane_id="p2", name="P2", function=PlaneFunction.DATA, allowed_dependencies=["p3"]))
        self.engine.define_plane(PlaneDefinition(plane_id="p3", name="P3", function=PlaneFunction.DATA, allowed_dependencies=["p1"]))
        t_id = self._create_basic_topology(["p1", "p2", "p3"])
        violations = self.engine.detect_circular_dependencies(t_id)
        self.assertTrue(len(violations) >= 1)
        self.assertEqual(violations[0].rule, "circular_dependency")

    def test_12_detect_circular_dependencies_self_loop(self):
        self.engine.define_plane(PlaneDefinition(plane_id="p1", name="P1", function=PlaneFunction.DATA, allowed_dependencies=["p1"]))
        t_id = self._create_basic_topology(["p1"])
        violations = self.engine.detect_circular_dependencies(t_id)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].rule, "circular_dependency")

    def test_13_check_isolation_compliance_pass(self):
        self.engine.define_plane(PlaneDefinition(plane_id="p1", name="P1", function=PlaneFunction.DATA, allowed_dependencies=["p2"]))
        self.engine.define_plane(PlaneDefinition(plane_id="p2", name="P2", function=PlaneFunction.DATA, isolation=PlaneIsolation.DEDICATED))
        t_id = self._create_basic_topology(["p1", "p2"])
        violations = self.engine.check_isolation_compliance(t_id)
        self.assertEqual(len(violations), 0)

    def test_14_check_isolation_compliance_fail(self):
        self.engine.define_plane(PlaneDefinition(plane_id="p1", name="P1", function=PlaneFunction.CONTROL, allowed_dependencies=["p2"]))
        self.engine.define_plane(PlaneDefinition(plane_id="p2", name="P2", function=PlaneFunction.DATA, isolation=PlaneIsolation.DEDICATED))
        t_id = self._create_basic_topology(["p1", "p2"])
        violations = self.engine.check_isolation_compliance(t_id)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].rule, "isolation_violation")

    def test_15_check_isolation_compliance_shared(self):
        self.engine.define_plane(PlaneDefinition(plane_id="p1", name="P1", function=PlaneFunction.CONTROL, allowed_dependencies=["p2"]))
        self.engine.define_plane(PlaneDefinition(plane_id="p2", name="P2", function=PlaneFunction.DATA, isolation=PlaneIsolation.SHARED))
        t_id = self._create_basic_topology(["p1", "p2"])
        violations = self.engine.check_isolation_compliance(t_id)
        self.assertEqual(len(violations), 0)

    def test_16_check_mtls_compliance_pass(self):
        self.engine.define_plane(PlaneDefinition(plane_id="p1", name="P1", function=PlaneFunction.DATA, allowed_dependencies=["p2"], requires_mtls=True))
        self.engine.define_plane(PlaneDefinition(plane_id="p2", name="P2", function=PlaneFunction.DATA, requires_mtls=True))
        t_id = self._create_basic_topology(["p1", "p2"])
        violations = self.engine.check_mtls_compliance(t_id)
        self.assertEqual(len(violations), 0)

    def test_17_check_mtls_compliance_fail(self):
        self.engine.define_plane(PlaneDefinition(plane_id="p1", name="P1", function=PlaneFunction.DATA, allowed_dependencies=["p2"], requires_mtls=False))
        self.engine.define_plane(PlaneDefinition(plane_id="p2", name="P2", function=PlaneFunction.DATA, requires_mtls=True))
        t_id = self._create_basic_topology(["p1", "p2"])
        violations = self.engine.check_mtls_compliance(t_id)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].rule, "mtls_violation")

    def test_18_evaluate_topology_compliant(self):
        self.engine.define_plane(PlaneDefinition(plane_id="p1", name="P1", function=PlaneFunction.DATA, allowed_dependencies=["p2"], requires_mtls=True))
        self.engine.define_plane(PlaneDefinition(plane_id="p2", name="P2", function=PlaneFunction.DATA, requires_mtls=True, isolation=PlaneIsolation.SHARED))
        t_id = self._create_basic_topology(["p1", "p2"])
        topo = self.engine.evaluate_topology(t_id)
        self.assertTrue(topo.compliant)
        self.assertEqual(len(topo.violations), 0)
        self.assertNotEqual(topo.evaluated_at, "")

    def test_19_evaluate_topology_non_compliant(self):
        self.engine.define_plane(PlaneDefinition(plane_id="p1", name="P1", function=PlaneFunction.CONTROL, allowed_dependencies=["p2"], requires_mtls=False))
        self.engine.define_plane(PlaneDefinition(plane_id="p2", name="P2", function=PlaneFunction.DATA, requires_mtls=True, isolation=PlaneIsolation.DEDICATED))
        t_id = self._create_basic_topology(["p1", "p2"])
        topo = self.engine.evaluate_topology(t_id)
        self.assertFalse(topo.compliant)
        self.assertEqual(len(topo.violations), 2)  # isolation & mtls

    def test_20_get_plane_graph_success(self):
        self.engine.define_plane(PlaneDefinition(plane_id="p1", name="P1", function=PlaneFunction.CONTROL, allowed_dependencies=["p2"]))
        self.engine.define_plane(PlaneDefinition(plane_id="p2", name="P2", function=PlaneFunction.DATA))
        t_id = self._create_basic_topology(["p1", "p2"])
        graph = self.engine.get_plane_graph(t_id)
        self.assertEqual(graph["topology_id"], t_id)
        self.assertIn("p1", graph["nodes"])
        self.assertEqual(graph["nodes"]["p1"]["dependencies"], ["p2"])

    def test_21_get_plane_graph_invalid_topo(self):
        with self.assertRaises(ValueError):
            self.engine.get_plane_graph("nonexistent")

    def test_22_get_compliance_report_success(self):
        self.engine.define_plane(PlaneDefinition(plane_id="p1", name="P1", function=PlaneFunction.CONTROL, allowed_dependencies=["p2"]))
        self.engine.define_plane(PlaneDefinition(plane_id="p2", name="P2", function=PlaneFunction.DATA))
        t_id = self._create_basic_topology(["p1", "p2"])
        self.engine.evaluate_topology(t_id)
        report = self.engine.get_compliance_report(t_id)
        self.assertEqual(report["topology_id"], t_id)
        self.assertEqual(report["plane_count"], 2)

    def test_23_get_compliance_report_invalid_topo(self):
        with self.assertRaises(ValueError):
            self.engine.get_compliance_report("invalid")

    def test_24_validate_dependencies_invalid_topo(self):
        with self.assertRaises(ValueError):
            self.engine.validate_dependencies("invalid")

    def test_25_detect_circular_invalid_topo(self):
        with self.assertRaises(ValueError):
            self.engine.detect_circular_dependencies("invalid")

    def test_26_check_isolation_invalid_topo(self):
        with self.assertRaises(ValueError):
            self.engine.check_isolation_compliance("invalid")

    def test_27_check_mtls_invalid_topo(self):
        with self.assertRaises(ValueError):
            self.engine.check_mtls_compliance("invalid")

    def test_28_evaluate_topology_invalid_topo(self):
        with self.assertRaises(ValueError):
            self.engine.evaluate_topology("invalid")

    def test_29_complex_circular_graph(self):
        self.engine.define_plane(PlaneDefinition(plane_id="p1", name="P1", function=PlaneFunction.DATA, allowed_dependencies=["p2", "p3"]))
        self.engine.define_plane(PlaneDefinition(plane_id="p2", name="P2", function=PlaneFunction.DATA, allowed_dependencies=["p4"]))
        self.engine.define_plane(PlaneDefinition(plane_id="p3", name="P3", function=PlaneFunction.DATA, allowed_dependencies=["p5"]))
        self.engine.define_plane(PlaneDefinition(plane_id="p4", name="P4", function=PlaneFunction.DATA, allowed_dependencies=["p1"]))
        self.engine.define_plane(PlaneDefinition(plane_id="p5", name="P5", function=PlaneFunction.DATA, allowed_dependencies=[]))
        t_id = self._create_basic_topology(["p1", "p2", "p3", "p4", "p5"])
        violations = self.engine.detect_circular_dependencies(t_id)
        self.assertTrue(len(violations) >= 1)

    def test_30_hybrid_isolation_compliance(self):
        self.engine.define_plane(PlaneDefinition(plane_id="p1", name="P1", function=PlaneFunction.CONTROL, allowed_dependencies=["p2"]))
        self.engine.define_plane(PlaneDefinition(plane_id="p2", name="P2", function=PlaneFunction.DATA, isolation=PlaneIsolation.HYBRID))
        t_id = self._create_basic_topology(["p1", "p2"])
        violations = self.engine.check_isolation_compliance(t_id)
        self.assertEqual(len(violations), 0)

    def test_31_multiple_mtls_violations(self):
        self.engine.define_plane(PlaneDefinition(plane_id="p1", name="P1", function=PlaneFunction.DATA, allowed_dependencies=["p2", "p3"], requires_mtls=False))
        self.engine.define_plane(PlaneDefinition(plane_id="p2", name="P2", function=PlaneFunction.DATA, requires_mtls=True))
        self.engine.define_plane(PlaneDefinition(plane_id="p3", name="P3", function=PlaneFunction.DATA, requires_mtls=True))
        t_id = self._create_basic_topology(["p1", "p2", "p3"])
        violations = self.engine.check_mtls_compliance(t_id)
        self.assertEqual(len(violations), 2)

    def test_32_missing_planes_in_dependencies(self):
        self.engine.define_plane(PlaneDefinition(plane_id="p1", name="P1", function=PlaneFunction.DATA, allowed_dependencies=["p2"]))
        t_id = self._create_basic_topology(["p1"]) # p2 is missing in topo and planes
        violations = self.engine.validate_dependencies(t_id)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].rule, "missing_dependency")
        
        # Test isolation and mtls shouldn't crash when missing targets
        iso_violations = self.engine.check_isolation_compliance(t_id)
        self.assertEqual(len(iso_violations), 0)
        
        mtls_violations = self.engine.check_mtls_compliance(t_id)
        self.assertEqual(len(mtls_violations), 0)

if __name__ == '__main__':
    unittest.main()
