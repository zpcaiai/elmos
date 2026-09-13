"""Migration Run Ingestion Engine (Batch 41 - Skill 1396).

Automatically ingests completed migration runs, extracts reusable code transformation
rules, antipatterns, error resolutions, and test fixtures into the intelligence flywheel.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any, Dict, List, Optional
import uuid

from elmos_mature_platform.types import (
    IngestedAssetType,
    IngestionQualityScore,
    MigrationRunSummary,
    RunIngestionArtifact,
)


class MigrationRunIngestionEngine:
    """Industrial engine for ingesting migration runs into reusable knowledge assets (B41)."""

    def __init__(self):
        self._runs: Dict[str, MigrationRunSummary] = {}
        self._artifacts: Dict[str, RunIngestionArtifact] = {}
        self._audit_log: List[Dict[str, Any]] = []

    def ingest_migration_run(self, run: MigrationRunSummary) -> List[RunIngestionArtifact]:
        """Ingest a migration run and automatically extract candidate knowledge assets."""
        if not run.run_id:
            run.run_id = f"run-{uuid.uuid4().hex[:8]}"
        if not run.completed_at:
            run.completed_at = datetime.now(timezone.utc).isoformat()

        self._runs[run.run_id] = run
        extracted: List[RunIngestionArtifact] = []

        # 1. If successful with transformations, extract transformation patterns
        if run.success and run.transformations_applied > 0:
            pat_id = f"art-{uuid.uuid4().hex[:6]}"
            pat_art = RunIngestionArtifact(
                artifact_id=pat_id,
                run_id=run.run_id,
                asset_type=IngestedAssetType.PATTERN,
                source_language=run.source_tech,
                target_language=run.target_tech,
                content=f"Transformation pattern for {run.source_tech}->{run.target_tech} with {run.transformations_applied} changes",
                quality=IngestionQualityScore.HIGH,
                confidence_score=0.92,
                ingested_at=datetime.now(timezone.utc).isoformat(),
                provenance_run_id=run.run_id,
            )
            self._artifacts[pat_id] = pat_art
            extracted.append(pat_art)

        # 2. Extract error solutions for any logged errors
        for idx, err in enumerate(run.errors_encountered):
            sol_id = f"art-{uuid.uuid4().hex[:6]}"
            sol_art = RunIngestionArtifact(
                artifact_id=sol_id,
                run_id=run.run_id,
                asset_type=IngestedAssetType.ERROR_SOLUTION,
                source_language=run.source_tech,
                target_language=run.target_tech,
                content=f"Error resolution signature: {err}",
                quality=IngestionQualityScore.MEDIUM if not run.success else IngestionQualityScore.HIGH,
                confidence_score=0.85 if run.success else 0.65,
                ingested_at=datetime.now(timezone.utc).isoformat(),
                provenance_run_id=run.run_id,
            )
            self._artifacts[sol_id] = sol_art
            extracted.append(sol_art)

        # 3. Generate regression test fixture candidate
        fix_id = f"art-{uuid.uuid4().hex[:6]}"
        fix_art = RunIngestionArtifact(
            artifact_id=fix_id,
            run_id=run.run_id,
            asset_type=IngestedAssetType.FIXTURE,
            source_language=run.source_tech,
            target_language=run.target_tech,
            content=f"Gold verification fixture based on project {run.project_name} ({run.files_migrated} files)",
            quality=IngestionQualityScore.HIGH if run.success else IngestionQualityScore.REJECTED,
            confidence_score=0.95 if run.success else 0.30,
            ingested_at=datetime.now(timezone.utc).isoformat(),
            provenance_run_id=run.run_id,
        )
        self._artifacts[fix_id] = fix_art
        extracted.append(fix_art)

        self._record_audit("run_ingested", run.run_id, {
            "project": run.project_name,
            "assets_extracted": len(extracted),
        })
        return extracted

    def evaluate_artifact_quality(
        self,
        artifact_id: str,
        threshold: float = 0.8,
    ) -> IngestionQualityScore:
        """Score artifact quality based on confidence and empirical validity."""
        artifact = self._get_artifact_or_raise(artifact_id)
        if artifact.confidence_score >= 0.9:
            artifact.quality = IngestionQualityScore.VERIFIED
        elif artifact.confidence_score >= threshold:
            artifact.quality = IngestionQualityScore.HIGH
        elif artifact.confidence_score >= 0.5:
            artifact.quality = IngestionQualityScore.MEDIUM
        else:
            artifact.quality = IngestionQualityScore.REJECTED

        return artifact.quality

    def approve_artifact_for_curation(
        self,
        artifact_id: str,
        curator: str,
    ) -> RunIngestionArtifact:
        """Human or supervisor curation approval for promoting asset into official flywheel."""
        artifact = self._get_artifact_or_raise(artifact_id)
        if artifact.quality == IngestionQualityScore.REJECTED:
            raise ValueError(f"Cannot approve rejected artifact {artifact_id}")

        artifact.approved_by = curator
        artifact.quality = IngestionQualityScore.VERIFIED
        self._record_audit("artifact_approved", artifact_id, {"curator": curator})
        return artifact

    def query_harvested_assets(
        self,
        source_tech: str,
        target_tech: str,
        asset_type: Optional[IngestedAssetType] = None,
    ) -> List[RunIngestionArtifact]:
        """Search harvested knowledge assets by tech stack and optional asset type."""
        results = [
            a for a in self._artifacts.values()
            if a.source_language.lower() == source_tech.lower()
            and a.target_language.lower() == target_tech.lower()
        ]
        if asset_type:
            results = [a for a in results if a.asset_type == asset_type]
        return results

    def get_flywheel_harvest_stats(self) -> Dict[str, Any]:
        """Aggregate intelligence flywheel statistics."""
        by_type: Dict[str, int] = {}
        by_quality: Dict[str, int] = {}
        approved_count = 0

        for a in self._artifacts.values():
            by_type[a.asset_type.value] = by_type.get(a.asset_type.value, 0) + 1
            by_quality[a.quality.value] = by_quality.get(a.quality.value, 0) + 1
            if a.approved_by:
                approved_count += 1

        return {
            "total_runs_ingested": len(self._runs),
            "total_assets_harvested": len(self._artifacts),
            "curated_approved_assets": approved_count,
            "assets_by_type": by_type,
            "assets_by_quality": by_quality,
        }

    def _get_artifact_or_raise(self, artifact_id: str) -> RunIngestionArtifact:
        if artifact_id not in self._artifacts:
            raise ValueError(f"Artifact {artifact_id} not found")
        return self._artifacts[artifact_id]

    def _record_audit(self, action: str, target: str, details: Dict[str, Any]) -> None:
        self._audit_log.append({
            "action": action,
            "target": target,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details,
        })
