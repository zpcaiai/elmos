"""Root-level DAG and dual-root installation validation tests for Foundry v3.0.0."""

from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class SkillCatalogDagTests(unittest.TestCase):
    def test_dual_root_installation_parity(self) -> None:
        ws_skills = ROOT / ".agents/skills"
        rt_skills = ROOT / "agent-skills/runtime"

        # Check all 41 meta-skills exist in both roots
        pack_names = [
            "00-foundation-contracts", "01-knowledge-ingestion-governance", "02-repository-semantic-intelligence",
            "03-retrieval-context-engineering", "04-memory-experience-flywheel", "05-skill-foundry-runtime",
            "06-dataset-foundry", "07-private-model-foundry", "08-agentic-training-rl",
            "09-evaluation-proof-certification", "10-serving-routing-inference", "11-security-privacy-compliance",
            "12-observability-lineage-finops", "13-commercial-multitenant-platform", "14-human-governance-operations",
            "15-domain-engineering-packs", "16-self-evolution-release-engineering", "17-repository-execution-os",
            "18-java-spring-enterprise-modernization", "19-cross-language-semantic-conversion",
            "20-sql-database-modernization", "21-project-generation-product-engineering",
            "22-frontend-mobile-miniapp-modernization", "23-repository-refactoring-technical-debt",
            "24-api-event-integration-modernization", "25-data-engineering-lakehouse-analytics",
            "26-cloud-native-devops-platform-engineering", "27-test-quality-assurance-factory",
            "28-security-compliance-supply-chain", "29-performance-reliability-cost-engineering",
            "30-architecture-documentation-ide", "31-ai-agent-rag-ml-engineering",
            "32-legacy-mainframe-enterprise-modernization", "33-industrial-iot-edge-robotics",
            "34-language-runtime-adapters", "35-database-engine-adapters",
            "36-framework-runtime-adapters", "37-cloud-platform-adapters",
            "38-golden-route-customer-delivery", "39-product-commercialization-marketplace",
            "40-regulated-industry-assurance",
        ]
        for pack_name in pack_names:
            meta_name = f"elmos-{pack_name}"
            ws_target = ws_skills / meta_name / "SKILL.md"
            rt_target = rt_skills / meta_name / "SKILL.md"
            self.assertTrue(ws_target.is_file(), f"Missing {ws_target}")
            self.assertTrue(rt_target.is_file(), f"Missing {rt_target}")
            self.assertEqual(ws_target.read_bytes(), rt_target.read_bytes(), f"Parity mismatch on {meta_name}")

    def test_atomic_skills_dual_root_installed(self) -> None:
        ws_skills = ROOT / ".agents/skills"
        rt_skills = ROOT / "agent-skills/runtime"
        
        # Test representative sample of atomic skills installed by foundry v3.0.0
        sample_skills = [
            "elmos-capability-taxonomy-governance",
            "elmos-source-freshness-and-expiry",
            "elmos-symbol-aware-retrieval",
            "elmos-episodic-memory-store",
            "elmos-dataset-contract-and-schema",
            "elmos-lora-qlora-adapter-training",
            "elmos-router-and-risk-dataset",
            "elmos-cross-tenant-data-separation",
            "elmos-long-task-checkpoint-and-resume",
            "elmos-consumer-driven-compatibility",
            "elmos-consumer-driven-contract-test",
        ]
        for skill in sample_skills:
            self.assertTrue((ws_skills / skill / "SKILL.md").is_file(), f"Missing in workspace: {skill}")
            self.assertTrue((rt_skills / skill / "SKILL.md").is_file(), f"Missing in runtime: {skill}")


if __name__ == "__main__":
    unittest.main()
