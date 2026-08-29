"""Root-level DAG and dual-root installation validation tests."""

from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class SkillCatalogDagTests(unittest.TestCase):
    def test_dual_root_installation_parity(self) -> None:
        ws_skills = ROOT / ".agents/skills"
        rt_skills = ROOT / "agent-skills/runtime"

        # Check all 17 meta-skills exist in both roots
        for i in range(17):
            pack_suffix = [
                "foundation-contracts", "knowledge-ingestion-governance", "repository-semantic-intelligence",
                "retrieval-context-engineering", "memory-experience-flywheel", "skill-foundry-runtime",
                "dataset-foundry", "private-model-foundry", "agentic-training-rl",
                "evaluation-proof-certification", "serving-routing-inference", "security-privacy-compliance",
                "observability-lineage-finops", "commercial-multitenant-platform", "human-governance-operations",
                "domain-engineering-packs", "self-evolution-release-engineering",
            ][i]
            meta_name = f"elmos-{i:02d}-{pack_suffix}"
            ws_target = ws_skills / meta_name / "SKILL.md"
            rt_target = rt_skills / meta_name / "SKILL.md"
            self.assertTrue(ws_target.is_file(), f"Missing {ws_target}")
            self.assertTrue(rt_target.is_file(), f"Missing {rt_target}")
            self.assertEqual(ws_target.read_bytes(), rt_target.read_bytes(), f"Parity mismatch on {meta_name}")

    def test_atomic_skills_dual_root_installed(self) -> None:
        ws_skills = ROOT / ".agents/skills"
        rt_skills = ROOT / "agent-skills/runtime"
        
        # Test representative sample of atomic skills installed by foundry
        sample_skills = [
            "elmos-capability-taxonomy-governance",
            "elmos-source-freshness-and-expiry",
            "elmos-symbol-aware-retrieval",
            "elmos-episodic-memory-store",
            "elmos-dataset-contract-and-schema",
            "elmos-lora-qlora-adapter-training",
            "elmos-router-and-risk-dataset",
            "elmos-cross-tenant-data-separation",
        ]
        for skill in sample_skills:
            self.assertTrue((ws_skills / skill / "SKILL.md").is_file(), f"Missing in workspace: {skill}")
            self.assertTrue((rt_skills / skill / "SKILL.md").is_file(), f"Missing in runtime: {skill}")


if __name__ == "__main__":
    unittest.main()
