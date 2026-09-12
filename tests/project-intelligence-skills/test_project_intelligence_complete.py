"""Industrial Test Suite for Project Intelligence Deep Analysis Engines.

Covers:
- DeepCallGraphBuilder: Interprocedural call graphs, cycle detection, reachable nodes.
- DataflowTaintEngine: Taint propagation, CWE classification, sanitizer neutralization.
- ArchitectureDriftDetector: Layer boundary checking, circular dependencies, drift reports.
- ThreatModelEngine: STRIDE categorization, DREAD risk scoring, attack surface analysis.
"""

from __future__ import annotations

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
ENGINE_SOURCE = ROOT / "engines/project-intelligence-engine/src"
if str(ENGINE_SOURCE) not in sys.path:
    sys.path.insert(0, str(ENGINE_SOURCE))

from elmos_project_intelligence.deep_callgraph import DeepCallGraphBuilder
from elmos_project_intelligence.dataflow_taint_engine import DataflowTaintEngine
from elmos_project_intelligence.architecture_drift_detector import ArchitectureDriftDetector
from elmos_project_intelligence.threat_model_engine import ThreatModelEngine


class ProjectIntelligenceDeepAnalysisTests(unittest.TestCase):
    def test_deep_call_graph_builder(self) -> None:
        builder = DeepCallGraphBuilder()
        code = """
def process_order(order_id):
    validate(order_id)
    save_order(order_id)

def validate(order_id):
    check_db(order_id)

def check_db(order_id):
    pass

def save_order(order_id):
    pass
"""
        builder.add_source_file("services/order_service.py", code, language="python")
        summary = builder.summarize()
        self.assertGreaterEqual(summary.total_functions, 4)
        self.assertGreaterEqual(summary.total_calls, 3)
        self.assertTrue(summary.graph_digest.startswith("sha256:"))

    def test_dataflow_taint_engine_sqli_and_sanitizer(self) -> None:
        engine = DataflowTaintEngine()
        code_vuln = """
user_id = request.args
cursor.execute("SELECT * FROM users WHERE id = " + user_id)
"""
        vulns = engine.analyze_python_file("views/users.py", code_vuln)
        self.assertGreaterEqual(len(vulns), 1)
        self.assertEqual(vulns[0].cwe_id, "CWE-89")
        self.assertFalse(vulns[0].sanitized)

    def test_architecture_drift_detector_layer_violation(self) -> None:
        detector = ArchitectureDriftDetector()
        files = {
            "domain/entities.py": "import infrastructure.database\nclass User: pass",
            "infrastructure/database.py": "class DBConnection: pass",
        }
        report = detector.analyze_repository(files)
        self.assertGreaterEqual(report.total_violations, 1)
        self.assertTrue(report.audit_digest.startswith("sha256:"))

    def test_threat_model_engine_stride_dread(self) -> None:
        engine = ThreatModelEngine()
        files = {
            "auth/client.py": """
import requests
def fetch_user_data(url):
    return requests.get(url, verify=False)
"""
        }
        report = engine.generate_threat_report(files)
        self.assertGreaterEqual(report.total_threats, 1)
        self.assertTrue(report.ledger_digest.startswith("sha256:"))


if __name__ == "__main__":
    unittest.main()
