"""K2: Repository Intelligence Kernel for Elmos Commercial Capability Expansion."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Dict, List, Set

from ..models import RiskAssessment, RiskLevel, TaskContext


class RepositoryIntelligenceKernel:
    """Extracts syntax, symbol, dependency, build, ownership, and risk intelligence."""

    def __init__(self):
        self.symbol_index: Dict[str, Dict[str, Any]] = {}
        self.dependency_graph: Dict[str, List[str]] = {}
        self.call_graph: Dict[str, List[str]] = {}
        self.file_language_map: Dict[str, str] = {
            ".py": "python",
            ".ts": "typescript",
            ".js": "javascript",
            ".java": "java",
            ".cs": "csharp",
            ".rs": "rust",
            ".go": "go",
            ".sql": "sql",
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
        }

    def index_repository_symbols(self, repo_path: Path) -> Dict[str, Any]:
        """Indexes symbols, definitions, and language distribution across repository."""
        counts = {"files": 0, "symbols": 0, "languages": set()}
        if not repo_path.is_dir():
            return {"status": "SKIPPED", "reason": "non-existent path", "metrics": counts}

        for root, _, files in os.walk(repo_path):
            if any(p in root for p in [".git", "node_modules", ".venv", "dist", "build"]):
                continue
            for f in files:
                ext = Path(f).suffix.lower()
                lang = self.file_language_map.get(ext)
                if lang:
                    counts["files"] += 1
                    counts["languages"].add(lang)
                    # Simplified symbol indexing
                    sym_id = f"{f}:{lang}"
                    self.symbol_index[sym_id] = {
                        "path": str(Path(root) / f),
                        "language": lang,
                        "name": f,
                    }
                    counts["symbols"] += 1

        counts["languages"] = list(counts["languages"])
        return {
            "status": "INDEXED",
            "total_files": counts["files"],
            "total_symbols": counts["symbols"],
            "languages": counts["languages"],
        }

    def compute_blast_radius(self, modified_files: List[str]) -> List[str]:
        """Computes transitive blast radius across modules and consumers."""
        affected: Set[str] = set(modified_files)
        for f in modified_files:
            deps = self.dependency_graph.get(f, [])
            affected.update(deps)
        return sorted(list(affected))

    def select_affected_tests(self, modified_files: List[str], all_tests: List[str]) -> List[str]:
        """Selects the minimal high-confidence subset of tests affected by changed files."""
        selected: Set[str] = set()
        for mf in modified_files:
            stem = Path(mf).stem.lower()
            for t in all_tests:
                if stem in t.lower() or "test_" + stem in t.lower() or stem + "_test" in t.lower():
                    selected.add(t)
        # Always return at least smoke test if available
        if not selected and all_tests:
            selected.add(all_tests[0])
        return sorted(list(selected))

    def evaluate_change_risk(
        self,
        context: TaskContext,
        modified_files: List[str],
        critical_paths: Optional[List[str]] = None,
    ) -> RiskAssessment:
        """Classifies change risk and generates mandatory verification obligations."""
        critical_paths = critical_paths or ["auth", "security", "database", "payment", "billing", "crypto"]
        affected = self.compute_blast_radius(modified_files)
        blast_radius = len(affected)

        is_critical = any(any(cp in f.lower() for cp in critical_paths) for f in modified_files)
        is_large = blast_radius > 15 or len(modified_files) > 10

        if is_critical and is_large:
            level = RiskLevel.CRITICAL
            score = 0.95
            obligations = [
                "E4_DIFFERENTIAL_RUNTIME",
                "E5_FORMAL_PROVENANCE",
                "POLICY_AS_CODE_REVIEW",
                "SANDBOX_HERMETIC_ISOLATION",
                "MUTATION_TEST_ADEQUACY",
            ]
        elif is_critical:
            level = RiskLevel.HIGH
            score = 0.80
            obligations = [
                "E3_SECURITY_ISOLATION",
                "E4_DIFFERENTIAL_RUNTIME",
                "SANDBOX_HERMETIC_ISOLATION",
                "AFFECTED_TEST_SUITE",
            ]
        elif is_large:
            level = RiskLevel.MEDIUM
            score = 0.50
            obligations = [
                "E2_UNIT_INTEGRATION",
                "AFFECTED_TEST_SUITE",
                "COMPILER_CHECK",
            ]
        else:
            level = RiskLevel.LOW
            score = 0.20
            obligations = [
                "E1_SYNTAX_COMPILE",
                "AFFECTED_TEST_SUITE",
            ]

        rationale = f"Risk evaluated for {len(modified_files)} files (blast radius {blast_radius}): critical_match={is_critical}"
        assessment_id = f"risk-{context.repository_id}-{hashlib.sha256(rationale.encode('utf-8')).hexdigest()[:12]}"

        return RiskAssessment(
            assessment_id=assessment_id,
            blast_radius=blast_radius,
            affected_modules=affected,
            risk_score=score,
            risk_level=level,
            mandatory_obligations=obligations,
            rationale=rationale,
        )
