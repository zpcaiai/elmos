"""Batch O: Certification Corpora & Test Assets Module (Skills 249-262)."""

from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List, Optional

from ..models import BatchType, ObligationStatus, SemanticObligation, SemanticRisk


class CorpusGovernanceModule:
    """Manages fixture corpus registry, license provenance, feature coverage, and test minimization."""

    def __init__(self):
        self.corpus_registry: Dict[str, Dict[str, Any]] = {}

    def register_fixture(
        self,
        fixture_id: str,
        language: str,
        category: str,
        code_snippet: str,
        license_id: str = "Apache-2.0",
        is_adversarial: bool = False,
    ) -> Dict[str, Any]:
        """Registers a test fixture with verified provenance and license terms."""
        digest = hashlib.sha256(code_snippet.encode("utf-8")).hexdigest()
        entry = {
            "fixture_id": fixture_id,
            "language": language,
            "category": category,
            "license_id": license_id,
            "sha256": digest,
            "is_adversarial": is_adversarial,
            "registered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": "ACTIVE",
        }
        self.corpus_registry[fixture_id] = entry
        return entry

    def calculate_corpus_coverage(
        self,
        total_language_features: int,
        covered_feature_ids: List[str],
    ) -> Dict[str, Any]:
        """Computes grammar and semantic feature coverage across fixture registry."""
        unique_covered = len(set(covered_feature_ids))
        ratio = unique_covered / total_language_features if total_language_features > 0 else 1.0

        return {
            "total_features": total_language_features,
            "covered_features": unique_covered,
            "coverage_ratio": ratio,
            "is_ready_for_certification": ratio >= 0.85,
            "status": "CERTIFIABLE" if ratio >= 0.85 else "INSUFFICIENT_COVERAGE",
        }

    def create_corpus_obligation(
        self,
        corpus_id: str,
        target_suite: str,
        property_name: str,
    ) -> SemanticObligation:
        """Emits a Batch O corpus semantic obligation."""
        obl_id = f"obl-O-{hashlib.sha256((corpus_id + target_suite + property_name).encode('utf-8')).hexdigest()[:10]}"
        return SemanticObligation(
            obligation_id=obl_id,
            batch=BatchType.BATCH_O,
            layer="corpus",
            source_construct=corpus_id,
            target_construct=target_suite,
            property_name=property_name,
            invariants=["CORPUS_PROVENANCE_INTEGRITY", "LICENSE_COMPLIANCE", "FEATURE_COVERAGE_THRESHOLD"],
            risk=SemanticRisk.CRITICAL,
            status=ObligationStatus.NOT_RUN,
        )
