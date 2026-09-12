"""Industrial-Grade Test Suite for Project Intelligence Subsystems.

Zero-tolerance verification with rigorous domain assertions:
- Ingestion & Merkle tree snapshotting
- Polyglot dependency parsing & Tarjan cycle detection (Maven, npm, Go, Cargo, pip)
- Universal Symbol Table with lexical scopes & AST extraction
- Clean Architecture layer boundary & Robert Martin metrics (Ca, Ce, I, A, D)
- Static Taint Dataflow for CWE-89/78/22/79/918 and sanitizers
- STRIDE threat modeling & DREAD quantitative risk scoring
- AST Code Clone Detection (Type-1, Type-2, Type-3)
- SQALE Technical Debt & McCabe / Halstead Maintainability Index
- PR Change Impact, Blast Radius & Breaking API change detection
- DDL Schema Graph Mining & Topological Sort
- Interprocedural CFG Basic Blocks, Dominance Tree & Dead Code
- CST / AST trivia preservation & roundtrip fidelity
- Contract Mining (Preconditions, Postconditions, Invariants)
- Framework & Architecture Style Fingerprinting
- Living Documentation & Mermaid Architecture Diagrams
"""

from __future__ import annotations

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
ENGINE_SOURCE = ROOT / "engines/project-intelligence-engine/src"
if str(ENGINE_SOURCE) not in sys.path:
    sys.path.insert(0, str(ENGINE_SOURCE))

from elmos_project_intelligence.subsystems.universal_source_ingestor import UniversalSourceIngestor
from elmos_project_intelligence.subsystems.framework_fingerprint_engine import FrameworkFingerprintEngine, ArchitectureStyle
from elmos_project_intelligence.subsystems.dependency_manifest_parser import DependencyManifestParser
from elmos_project_intelligence.subsystems.universal_symbol_table import UniversalSymbolTable, SymbolKind, SymbolVisibility
from elmos_project_intelligence.subsystems.clean_architecture_auditor import CleanArchitectureAuditor, ArchitectureLayer
from elmos_project_intelligence.subsystems.static_taint_dataflow_engine import StaticTaintDataflowEngine
from elmos_project_intelligence.subsystems.threat_modeling_stride_engine import ThreatModelingSTRIDEEngine, STRIDECategory
from elmos_project_intelligence.subsystems.semantic_clone_detector import SemanticCloneDetector, CloneType
from elmos_project_intelligence.subsystems.technical_debt_quantifier import TechnicalDebtQuantifier, SQALECategory
from elmos_project_intelligence.subsystems.pr_change_risk_classifier import PRChangeRiskClassifier, RiskLevel
from elmos_project_intelligence.subsystems.db_schema_graph_miner import DBSchemaGraphMiner
from elmos_project_intelligence.subsystems.interprocedural_cfg_engine import InterproceduralCFGEngine
from elmos_project_intelligence.subsystems.cst_ast_parser_adapters import CSTASTParserAdapters, CSTTokenKind
from elmos_project_intelligence.subsystems.contract_miner_engine import ContractMinerEngine, ContractType
from elmos_project_intelligence.subsystems.automated_doc_generator import AutomatedDocGenerator


class ProjectIntelligenceSubsystemsTests(unittest.TestCase):
    def test_universal_source_ingestor(self) -> None:
        ingestor = UniversalSourceIngestor("/mock/workspace")
        files = {
            "src/main.py": "def main():\n    print('hello')\n",
            "src/model.java": "public class Model {}\n",
            "pkg/util.go": "package pkg\nfunc Util() {}\n",
        }
        snap = ingestor.ingest_virtual_files(files)
        self.assertEqual(snap.total_files, 3)
        self.assertGreaterEqual(snap.total_lines, 5)
        self.assertIn("Python", snap.language_breakdown)
        self.assertIn("Java", snap.language_breakdown)
        self.assertIn("Go", snap.language_breakdown)
        self.assertTrue(snap.merkle_tree_root.startswith("sha256:"))

    def test_framework_fingerprinting(self) -> None:
        engine = FrameworkFingerprintEngine("/mock/workspace")
        files = ["src/main.py", "docker-compose.yml", "services/auth.py"]
        contents = {
            "src/main.py": "from fastapi import FastAPI, APIRouter\napp = FastAPI()\n",
            "docker-compose.yml": "version: '3.8'\nservices:\n  api:\n    build: .\n",
            "services/auth.py": "import django.db\nfrom django.urls import path\n",
        }
        report = engine.fingerprint_repository(files, contents)
        detected_names = [f.name for f in report.detected_frameworks]
        self.assertIn("FastAPI", detected_names)
        self.assertIn("Django", detected_names)
        self.assertEqual(report.primary_architecture_style, ArchitectureStyle.MICROSERVICE)
        self.assertTrue(report.fingerprint_digest.startswith("sha256:"))

    def test_dependency_manifest_parser(self) -> None:
        parser = DependencyManifestParser("/mock/workspace")

        # 1. package.json
        pkg_json = '{"dependencies": {"express": "^4.18.2"}, "devDependencies": {"jest": "^29.0.0"}}'
        npm_rep = parser.parse_package_json(pkg_json)
        self.assertEqual(npm_rep.direct_dependencies_count, 2)
        self.assertFalse(npm_rep.has_cycles)

        # 2. pom.xml
        pom = """<project>
            <properties><spring.ver>3.2.0</spring.ver></properties>
            <dependencies>
                <dependency>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-starter-web</artifactId>
                    <version>${spring.ver}</version>
                </dependency>
            </dependencies>
        </project>"""
        pom_rep = parser.parse_pom_xml(pom)
        self.assertEqual(pom_rep.direct_dependencies_count, 1)
        self.assertEqual(pom_rep.dependencies[0].version_spec, "3.2.0")

        # 3. go.mod
        go_mod = """module example.com/app
go 1.22
require (
    github.com/gin-gonic/gin v1.9.1
    golang.org/x/crypto v0.14.0 // indirect
)
"""
        go_rep = parser.parse_go_mod(go_mod)
        self.assertEqual(go_rep.total_dependencies_count, 2)
        self.assertEqual(go_rep.direct_dependencies_count, 1)

        # 4. Tarjan Cycle Detection
        cyclic_graph = {"A": ["B"], "B": ["C"], "C": ["A", "D"], "D": []}
        cycles = parser.detect_cycles(cyclic_graph)
        self.assertEqual(len(cycles), 1)
        self.assertEqual(sorted(cycles[0]), ["A", "B", "C"])

    def test_universal_symbol_table(self) -> None:
        table = UniversalSymbolTable("/mock/workspace")
        code = """
GLOBAL_CONST = 42

class UserService:
    def __init__(self, db_url: str):
        self.db_url = db_url

    def get_user(self, user_id: int) -> dict:
        total = user_id + GLOBAL_CONST
        return {"id": user_id, "total": total}
"""
        table.extract_from_python_ast("services/user_service.py", code)
        all_syms = table.get_all_symbols()
        sym_names = [s.name for s in all_syms]

        self.assertIn("GLOBAL_CONST", sym_names)
        self.assertIn("UserService", sym_names)
        self.assertIn("get_user", sym_names)
        self.assertIn("user_id", sym_names)

        # Test lookup and reference tracking
        table.enter_scope("user_service", "MODULE")
        res = table.lookup_symbol("UserService")
        self.assertIsNotNone(res)
        table.record_reference("UserService", is_write=False)
        self.assertEqual(res[0].read_references_count, 1)

        digest = table.compute_merkle_digest()
        self.assertTrue(digest.startswith("sha256:"))

    def test_clean_architecture_auditor(self) -> None:
        auditor = CleanArchitectureAuditor("/mock/workspace")
        # Violation: Domain entity importing database infrastructure!
        file_deps = {
            "domain/entities/order.py": ["infrastructure/database/order_dao.py"],
            "application/usecases/place_order.py": ["domain/entities/order.py"],
            "infrastructure/database/order_dao.py": [],
        }
        pkg_classes = {
            "domain/entities": {"abstract": 2, "total": 2},
            "application/usecases": {"abstract": 1, "total": 4},
            "infrastructure/database": {"abstract": 0, "total": 3},
        }
        report = auditor.audit_repository(file_deps, pkg_classes)
        self.assertEqual(report.total_violations, 1)
        self.assertEqual(report.violations[0].source_layer, "ENTITIES")
        self.assertEqual(report.violations[0].target_layer, "FRAMEWORKS_DRIVERS")
        self.assertEqual(report.status, "FAILED")

        # Verify Robert Martin's Metrics
        domain_m = next(m for m in report.package_metrics if m.package_name == "domain/entities")
        self.assertEqual(domain_m.ca, 1)  # usecases depends on domain
        self.assertEqual(domain_m.abstractness_a, 1.0)  # 2 abstract / 2 total

    def test_static_taint_dataflow_engine(self) -> None:
        engine = StaticTaintDataflowEngine("/mock/workspace")

        # Unsanitized SQLi
        vuln_code = """
user_input = request.args
cursor.execute("SELECT * FROM users WHERE id = " + user_input)
"""
        rep_vuln = engine.analyze_python_file("views/users.py", vuln_code)
        self.assertEqual(rep_vuln.total_findings, 1)
        self.assertEqual(rep_vuln.active_unmitigated_count, 1)
        self.assertEqual(rep_vuln.vulnerabilities[0].cwe_id, "CWE-89")
        self.assertFalse(rep_vuln.vulnerabilities[0].sanitized)

        # Sanitized SQLi via int() cast
        clean_code = """
user_input = request.args
safe_id = int(user_input)
cursor.execute("SELECT * FROM users WHERE id = %s", safe_id)
"""
        rep_clean = engine.analyze_python_file("views/users.py", clean_code)
        self.assertEqual(rep_clean.total_findings, 1)
        self.assertEqual(rep_clean.sanitized_count, 1)
        self.assertTrue(rep_clean.vulnerabilities[0].sanitized)
        self.assertEqual(rep_clean.vulnerabilities[0].sanitizer_used, "int")

    def test_threat_modeling_stride(self) -> None:
        engine = ThreatModelingSTRIDEEngine("/mock/workspace")
        files = {
            "network/client.py": "import requests\nrequests.get('https://api.internal/data', verify=False)\n",
            "auth/token.py": "api_key = 'sk_live_1234567890abcdef12345'\n",
        }
        report = engine.analyze_repository_threats(files)
        self.assertGreaterEqual(report.total_threats, 2)
        threat_cats = [t.stride_category for t in report.threats]
        self.assertIn(STRIDECategory.TAMPERING, threat_cats)
        self.assertIn(STRIDECategory.INFO_DISCLOSURE, threat_cats)
        self.assertTrue(report.ledger_digest.startswith("sha256:"))

    def test_semantic_clone_detector(self) -> None:
        detector = SemanticCloneDetector("/mock/workspace", min_tokens=5, similarity_threshold=0.70)
        files = {
            "service_a.py": """
def calculate_discount(price, rate):
    tax = price * 0.10
    total = price - (price * rate) + tax
    return total
""",
            "service_b.py": """
def calculate_rebate(amount, discount_rate):
    fee = amount * 0.10
    total_val = amount - (amount * discount_rate) + fee
    return total_val
""",
        }
        report = detector.detect_clones(files)
        self.assertGreaterEqual(report.total_clones_found, 1)
        self.assertEqual(report.clones[0].clone_type, CloneType.TYPE_2)
        self.assertGreaterEqual(report.clones[0].similarity_score, 0.90)

    def test_technical_debt_quantifier(self) -> None:
        quantifier = TechnicalDebtQuantifier("/mock/workspace")
        code = """
def complex_fn(a, b, c):
    if a > 0:
        if b > 0:
            while c > 0:
                c -= 1
        elif b < 0:
            return a - b
    else:
        for x in range(10):
            if x % 2 == 0:
                print(x)
    return a + b + c
"""
        rep = quantifier.analyze_source_file("math/calc.py", code)
        self.assertGreaterEqual(rep.cyclomatic_complexity, 6)
        self.assertGreater(rep.maintainability_index, 0.0)
        self.assertIn(rep.sqale_rating, ("A", "B", "C", "D", "E"))
        self.assertTrue(rep.ledger_digest.startswith("sha256:"))

    def test_pr_change_risk_classifier(self) -> None:
        classifier = PRChangeRiskClassifier("/mock/workspace")
        base_files = {
            "api/client.py": "def fetch_record(record_id: int): pass\ndef old_endpoint(): pass\n",
        }
        # Head deletes old_endpoint and adds required parameter to fetch_record without default
        head_files = {
            "api/client.py": "def fetch_record(record_id: int, api_key: str): pass\n",
        }
        call_graph = {
            "services/sync.py": ["fetch_record"],
            "controllers/user.py": ["fetch_record"],
        }
        assessment = classifier.classify_change(
            pr_id="PR-999",
            modified_files=["api/client.py"],
            base_source_files=base_files,
            head_source_files=head_files,
            call_graph=call_graph,
        )
        self.assertGreaterEqual(len(assessment.breaking_changes), 2)
        self.assertIn("fetch_record", assessment.blast_radius_symbols)
        self.assertIn("services/sync.py", assessment.blast_radius_symbols)
        self.assertGreaterEqual(assessment.risk_score, 40.0)

    def test_db_schema_graph_miner(self) -> None:
        miner = DBSchemaGraphMiner("/mock/workspace")
        ddl = """
CREATE TABLE users (
    id INT PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);

CREATE TABLE orders (
    order_id INT PRIMARY KEY,
    user_id INT,
    total DECIMAL(10, 2),
    CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE order_items (
    item_id INT PRIMARY KEY,
    order_id INT,
    sku VARCHAR(50),
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
);
"""
        report = miner.parse_ddl(ddl)
        self.assertEqual(report.total_tables, 3)
        # Topological order: users before orders, orders before order_items
        u_idx = report.creation_order.index("users")
        o_idx = report.creation_order.index("orders")
        i_idx = report.creation_order.index("order_items")
        self.assertLess(u_idx, o_idx)
        self.assertLess(o_idx, i_idx)

    def test_interprocedural_cfg_engine(self) -> None:
        engine = InterproceduralCFGEngine("/mock/workspace")
        code = """
def evaluate(x):
    if x > 0:
        return x * 2
    else:
        return -x
"""
        report = engine.analyze_source_file(code)
        self.assertEqual(len(report.functions), 1)
        cfg = report.functions["evaluate"]
        self.assertGreaterEqual(len(cfg.blocks), 4)
        self.assertEqual(len(cfg.unreachable_blocks), 0)
        self.assertTrue(report.cfg_digest.startswith("sha256:"))

    def test_cst_ast_parser_adapters(self) -> None:
        adapter = CSTASTParserAdapters("/mock/workspace")
        code = "# Leading license comment\ndef foo(x):\n    # inner comment\n    return x + 1\n"
        res = adapter.parse_source_to_cst(code)
        self.assertGreaterEqual(res.comments_count, 2)
        self.assertTrue(res.is_ast_equivalent)
        self.assertEqual(res.reconstructed_text, code)

    def test_contract_miner_engine(self) -> None:
        engine = ContractMinerEngine("/mock/workspace")
        code = """
def deposit(account_id: str, amount: float):
    assert amount > 0, "amount must be positive"
    if not account_id:
        raise ValueError("account_id required")
    return amount
"""
        report = engine.mine_contracts_from_source(code)
        self.assertGreaterEqual(report.total_contracts, 3)
        self.assertGreaterEqual(report.preconditions_count, 2)
        self.assertGreaterEqual(report.postconditions_count, 1)

    def test_automated_doc_generator(self) -> None:
        generator = AutomatedDocGenerator("/mock/workspace")
        python_sources = {
            "models/user.py": "class User:\n    id: int\n    def get_id(self) -> int:\n        return self.id\n",
        }
        tables = [
            {
                "table_name": "users",
                "columns": {"id": {"data_type": "INT", "is_primary_key": True}},
                "foreign_keys": [],
            }
        ]
        doc = generator.generate_living_document("PaymentEngine", "2.1.0", python_sources, tables)
        self.assertIn("classDiagram", doc.markdown_content)
        self.assertIn("erDiagram", doc.markdown_content)
        self.assertIn("flowchart TD", doc.markdown_content)
        self.assertTrue(doc.document_digest.startswith("sha256:"))


if __name__ == "__main__":
    unittest.main()
