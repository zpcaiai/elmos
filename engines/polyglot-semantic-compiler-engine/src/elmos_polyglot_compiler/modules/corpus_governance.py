"""Batch O: Certification Corpora & Test Assets Module (Skills 249-262)."""

from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List, Optional

from ..models import BatchType, ObligationStatus, SemanticObligation, SemanticRisk


class CorpusGovernanceModule:
    """Manages fixture corpus registry, license provenance, feature coverage threshold, and test minimization."""

    def __init__(self):
        self.fixtures: Dict[str, Dict[str, Any]] = {}

    def register_fixture(
        self,
        fixture_id: str,
        language: str,
        category: str,
        code_content: str,
        license_id: str = "Apache-2.0",
    ) -> Dict[str, Any]:
        """Registers a certification fixture with provenance metadata."""
        digest = hashlib.sha256(code_content.encode("utf-8")).hexdigest()
        entry = {
            "fixture_id": fixture_id,
            "language": language,
            "category": category,
            "license_id": license_id,
            "sha256": digest,
            "registered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": "REGISTERED",
        }
        self.fixtures[fixture_id] = entry
        return entry

    def assess_feature_coverage(self, total_features: int, covered_features: List[str]) -> Dict[str, Any]:
        """Computes coverage percentage against route language specifications."""
        unique_cnt = len(set(covered_features))
        ratio = unique_cnt / total_features if total_features > 0 else 1.0
        return {
            "total_features": total_features,
            "covered_features": unique_cnt,
            "coverage_ratio": ratio,
            "is_certification_eligible": ratio >= 0.80,
            "status": "PASS" if ratio >= 0.80 else "INSUFFICIENT_COVERAGE",
        }

    def create_corpus_obligation(
        self,
        corpus_id: str,
        target_suite: str,
        property_name: str,
    ) -> SemanticObligation:
        """Emits a Batch O corpus obligation."""
        obl_id = f"obl-O-{hashlib.sha256((corpus_id + target_suite + property_name).encode('utf-8')).hexdigest()[:10]}"
        return SemanticObligation(
            obligation_id=obl_id,
            batch=BatchType.BATCH_O,
            layer="corpus",
            source_construct=corpus_id,
            target_construct=target_suite,
            property_name=property_name,
            invariants=["CORPUS_PROVENANCE_ASSURANCE", "LICENSE_IP_CLEANLINESS", "FEATURE_COVERAGE_METRIC_PASS"],
            risk=SemanticRisk.CRITICAL,
            status=ObligationStatus.NOT_RUN,
        )
