"""Comprehensive test suite for Project Intelligence Subsystems."""

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
ENGINE_SOURCE = ROOT / "engines/project-intelligence-engine/src"
if str(ENGINE_SOURCE) not in sys.path:
    sys.path.insert(0, str(ENGINE_SOURCE))

from elmos_project_intelligence.subsystems.universal_source_ingestor import UniversalSourceIngestor
from elmos_project_intelligence.subsystems.framework_fingerprint_engine import FrameworkFingerprintEngine
from elmos_project_intelligence.subsystems.universal_symbol_table import UniversalSymbolTable
from elmos_project_intelligence.subsystems.cst_ast_parser_adapters import CSTASTParserAdapters
from elmos_project_intelligence.subsystems.interprocedural_cfg_engine import InterproceduralCFGEngine
from elmos_project_intelligence.subsystems.static_taint_dataflow_engine import StaticTaintDataflowEngine
from elmos_project_intelligence.subsystems.clean_architecture_auditor import CleanArchitectureAuditor
from elmos_project_intelligence.subsystems.threat_modeling_stride_engine import ThreatModelingSTRIDEEngine
from elmos_project_intelligence.subsystems.semantic_clone_detector import SemanticCloneDetector
from elmos_project_intelligence.subsystems.contract_miner_engine import ContractMinerEngine
from elmos_project_intelligence.subsystems.db_schema_graph_miner import DBSchemaGraphMiner
from elmos_project_intelligence.subsystems.automated_doc_generator import AutomatedDocGenerator
from elmos_project_intelligence.subsystems.technical_debt_quantifier import TechnicalDebtQuantifier
from elmos_project_intelligence.subsystems.pr_change_risk_classifier import PRChangeRiskClassifier


class ProjectIntelligenceSubsystemsTests(unittest.TestCase):
    def test_source_ingestor_and_fingerprint(self) -> None:
        ingestor = UniversalSourceIngestor("/mock/workspace")
        fingerprint = FrameworkFingerprintEngine("/mock/workspace")

        i_node = ingestor.analyze_intelligence_node_1({"id": "ING-01", "symbol": "src/main.py", "confidence": 0.98})
        f_node = fingerprint.analyze_intelligence_node_2({"id": "FNG-02", "symbol": "pom.xml", "confidence": 0.99})

        self.assertTrue(i_node.is_active)
        self.assertTrue(f_node.is_active)
        self.assertEqual(i_node.node_id, "ING-01")
        self.assertEqual(f_node.node_id, "FNG-02")
        self.assertTrue(ingestor.compute_ledger_merkle_root().startswith("sha256:"))
        self.assertTrue(fingerprint.compute_ledger_merkle_root().startswith("sha256:"))

    def test_symbol_table_and_cfg_engine(self) -> None:
        sym_tbl = UniversalSymbolTable("/mock/workspace")
        cfg_eng = InterproceduralCFGEngine("/mock/workspace")

        s_node = sym_tbl.analyze_intelligence_node_3({"id": "SYM-03", "symbol": "OrderService.placeOrder"})
        c_node = cfg_eng.analyze_intelligence_node_5({"id": "CFG-05", "symbol": "order_cfg_block_0"})

        self.assertTrue(s_node.is_active)
        self.assertTrue(c_node.is_active)
        self.assertTrue(sym_tbl.compute_ledger_merkle_root().startswith("sha256:"))
        self.assertTrue(cfg_eng.compute_ledger_merkle_root().startswith("sha256:"))

    def test_clean_architecture_and_threat_modeling(self) -> None:
        arch_aud = CleanArchitectureAuditor("/mock/workspace")
        threat_eng = ThreatModelingSTRIDEEngine("/mock/workspace")

        a_node = arch_aud.analyze_intelligence_node_7({"id": "ARCH-07", "symbol": "src/domain/model"})
        t_node = threat_eng.analyze_intelligence_node_8({"id": "THREAT-08", "symbol": "Gateway -> Auth"})

        self.assertTrue(a_node.is_active)
        self.assertTrue(t_node.is_active)
        self.assertTrue(arch_aud.compute_ledger_merkle_root().startswith("sha256:"))
        self.assertTrue(threat_eng.compute_ledger_merkle_root().startswith("sha256:"))

    def test_tech_debt_and_risk_classifier(self) -> None:
        debt_eng = TechnicalDebtQuantifier("/mock/workspace")
        risk_clf = PRChangeRiskClassifier("/mock/workspace")

        d_node = debt_eng.analyze_intelligence_node_13({"id": "DEBT-13", "symbol": "LegacyGodClass"})
        r_node = risk_clf.analyze_intelligence_node_14({"id": "RISK-14", "symbol": "PR-452-AuthModule"})

        self.assertTrue(d_node.is_active)
        self.assertTrue(r_node.is_active)
        self.assertTrue(debt_eng.compute_ledger_merkle_root().startswith("sha256:"))
        self.assertTrue(risk_clf.compute_ledger_merkle_root().startswith("sha256:"))

    def test_clone_contracts_schema_doc_engines(self) -> None:
        clone_eng = SemanticCloneDetector("/mock/workspace")
        contract_eng = ContractMinerEngine("/mock/workspace")
        schema_eng = DBSchemaGraphMiner("/mock/workspace")
        doc_eng = AutomatedDocGenerator("/mock/workspace")

        cl_node = clone_eng.analyze_intelligence_node_9({"id": "CLONE-09", "symbol": "auth_token_hash"})
        co_node = contract_eng.analyze_intelligence_node_10({"id": "CONTRACT-10", "symbol": "user.balance >= 0"})
        sc_node = schema_eng.analyze_intelligence_node_11({"id": "SCHEMA-11", "symbol": "orders.customer_id -> customers.id"})
        dc_node = doc_eng.analyze_intelligence_node_12({"id": "DOC-12", "symbol": "docs/architecture/c4_model.md"})

        self.assertTrue(cl_node.is_active)
        self.assertTrue(co_node.is_active)
        self.assertTrue(sc_node.is_active)
        self.assertTrue(dc_node.is_active)
        self.assertTrue(clone_eng.compute_ledger_merkle_root().startswith("sha256:"))
        self.assertTrue(contract_eng.compute_ledger_merkle_root().startswith("sha256:"))
        self.assertTrue(schema_eng.compute_ledger_merkle_root().startswith("sha256:"))
        self.assertTrue(doc_eng.compute_ledger_merkle_root().startswith("sha256:"))


if __name__ == "__main__":
    unittest.main()
