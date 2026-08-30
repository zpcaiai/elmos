"""Batch A: Discovery, Intake & Repository Ingestion Module (Skills 001-016)."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional

from ..models import BatchType, ObligationStatus, SemanticObligation, SemanticRisk


class DiscoveryIngestionModule:
    """Manages repository inventory scanning, symbol recovery, dependency graph discovery, and intake snapshots."""

    def __init__(self) -> None:
        self.snapshots: Dict[str, Dict[str, Any]] = {}

    def scan_repository_surface(
        self,
        repository_path: str,
        detected_languages: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create a bounded intake plan; the trusted runtime performs the scan."""
        snap_id = f"snap-{hashlib.sha256(repository_path.encode('utf-8')).hexdigest()[:10]}"
        languages = list(detected_languages or [])
        result = {
            "snapshot_id": snap_id,
            "repository_path": repository_path,
            "caller_supplied_languages": languages,
            "detected_languages": [],
            "total_files": None,
            "build_systems": [],
            "status": "TRUSTED_REPOSITORY_SCAN_REQUIRED",
            "execution_evidence": "NOT_RUN",
        }
        self.snapshots[snap_id] = result
        return result

    def create_discovery_obligation(
        self,
        surface_name: str,
        property_name: str,
    ) -> SemanticObligation:
        """Emits a Batch A discovery semantic obligation."""
        obl_id = f"obl-A-{hashlib.sha256((surface_name + property_name).encode('utf-8')).hexdigest()[:10]}"
        return SemanticObligation(
            obligation_id=obl_id,
            batch=BatchType.BATCH_A,
            layer="discovery",
            source_construct=surface_name,
            target_construct="canonical-inventory",
            property_name=property_name,
            invariants=("COMPLETE_FILE_INVENTORY", "DETERMINISTIC_SNAPSHOT_HASH"),
            risk=SemanticRisk.HIGH,
            status=ObligationStatus.NOT_RUN,
        )
