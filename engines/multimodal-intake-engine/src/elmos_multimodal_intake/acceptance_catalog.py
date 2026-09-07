"""Immutable acceptance identities for the multimodal intake source package.

The IDs below are copied from the package's ``evals/acceptance-matrix.yaml``.
They are data, not instructions.  Every source-package acceptance obligation is
kept visible and defaults to external evidence ``NOT_RUN``; a bounded local
evaluation can add engineering evidence but cannot rewrite this catalog or
manufacture certification.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from .canonical import canonical_digest


SOURCE_ARCHIVE_SHA256: Final = "23f9f2cee63e2fb1a43f85df539942e92077db2c58ddd75a8a0854773eb1c90b"
ACCEPTANCE_MATRIX_SHA256: Final = "38a012f853a363750e4723fcd4b2ed6d25f7ea3adf9a01175ba1307fe158a7f3"

# Each identity is intentionally explicit.  Do not replace this table with
# numeric range expansion: omissions and ownership drift must be reviewable.
ACCEPTANCE_IDS_BY_SKILL: Final[Mapping[str, tuple[str, ...]]] = {
    "elmos-multimodal-input-orchestrator": ("S01-01", "S01-02", "S01-03", "S01-04"),
    "elmos-secure-resumable-upload": ("S02-01", "S02-02", "S02-03", "S02-04"),
    "elmos-file-type-detection-and-validation": ("S03-01", "S03-02", "S03-03", "S03-04"),
    "elmos-malware-quarantine-and-sandbox": ("S04-01", "S04-02", "S04-03", "S04-04"),
    "elmos-audio-asr-and-diarization": ("S05-01", "S05-02", "S05-03", "S05-04"),
    "elmos-image-ocr-and-preprocessing": ("S06-01", "S06-02", "S06-03", "S06-04"),
    "elmos-visual-ui-understanding": ("S07-01", "S07-02", "S07-03", "S07-04"),
    "elmos-diagram-and-architecture-understanding": ("S08-01", "S08-02", "S08-03", "S08-04"),
    "elmos-pdf-layout-table-parser": ("S09-01", "S09-02", "S09-03", "S09-04"),
    "elmos-word-document-parser": ("S10-01", "S10-02", "S10-03", "S10-04"),
    "elmos-markdown-text-log-parser": ("S11-01", "S11-02", "S11-03", "S11-04"),
    "elmos-unified-multimodal-content-ir": ("S12-01", "S12-02", "S12-03", "S12-04"),
    "elmos-source-anchor-and-provenance": ("S13-01", "S13-02", "S13-03", "S13-04"),
    "elmos-multimodal-requirement-extraction": ("S14-01", "S14-02", "S14-03", "S14-04"),
    "elmos-multi-asset-content-fusion": ("S15-01", "S15-02", "S15-03", "S15-04"),
    "elmos-document-version-and-conflict-detection": ("S16-01", "S16-02", "S16-03", "S16-04"),
    "elmos-human-review-and-correction": ("S17-01", "S17-02", "S17-03", "S17-04"),
    "elmos-prompt-injection-defense": ("S18-01", "S18-02", "S18-03", "S18-04"),
    "elmos-provider-routing-and-fallback": ("S19-01", "S19-02", "S19-03", "S19-04"),
    "elmos-storage-index-and-retrieval": ("S20-01", "S20-02", "S20-03", "S20-04"),
    "elmos-durable-processing-and-recovery": ("S21-01", "S21-02", "S21-03", "S21-04"),
    "elmos-processing-cost-and-eta-estimation": ("S22-01", "S22-02", "S22-03", "S22-04"),
    "elmos-multimodal-observability": ("S23-01", "S23-02", "S23-03", "S23-04"),
    "elmos-multimodal-evaluation-framework": ("S24-01", "S24-02", "S24-03", "S24-04"),
    "elmos-multimodal-input-workbench-ui": ("S25-01", "S25-02", "S25-03", "S25-04"),
    "elmos-ingestion-api-and-sdk": ("S26-01", "S26-02", "S26-03", "S26-04"),
    "elmos-data-retention-and-governance": ("S27-01", "S27-02", "S27-03", "S27-04"),
    "elmos-downstream-agent-integration": ("S28-01", "S28-02", "S28-03", "S28-04"),
    "elmos-codex-context-capacity-parity": ("S29-01", "S29-02", "S29-03", "S29-04"),
    "elmos-context-budget-manager": ("S30-01", "S30-02", "S30-03", "S30-04"),
    "elmos-multimodal-token-accounting": ("S31-01", "S31-02", "S31-03", "S31-04", "S31-05", "S31-06"),
    "elmos-long-context-packing-and-ranking": ("S32-01", "S32-02", "S32-03", "S32-04", "S32-05", "S32-06"),
    "elmos-context-pressure-monitor": ("S33-01", "S33-02", "S33-03", "S33-04", "S33-05", "S33-06"),
    "elmos-structured-context-compaction": ("S34-01", "S34-02", "S34-03", "S34-04", "S34-05", "S34-06"),
    "elmos-context-checkpoint-and-recovery": ("S35-01", "S35-02", "S35-03", "S35-04", "S35-05", "S35-06"),
    "elmos-context-rehydration": ("S36-01", "S36-02", "S36-03", "S36-04", "S36-05", "S36-06"),
    "elmos-project-memory-and-retrieval": ("S37-01", "S37-02", "S37-03", "S37-04", "S37-05", "S37-06"),
    "elmos-repository-context-map": ("S38-01", "S38-02", "S38-03", "S38-04", "S38-05", "S38-06"),
    "elmos-model-capability-discovery": ("S39-01", "S39-02", "S39-03", "S39-04", "S39-05", "S39-06"),
    "elmos-context-integrity-and-loss-detection": ("S40-01", "S40-02", "S40-03", "S40-04", "S40-05", "S40-06"),
    "elmos-folder-tree-input": ("S41-01", "S41-02", "S41-03", "S41-04", "S41-05", "S41-06"),
    "elmos-resumable-multi-file-folder-upload": ("S42-01", "S42-02", "S42-03", "S42-04", "S42-05", "S42-06"),
    "elmos-project-package-manifest": ("S43-01", "S43-02", "S43-03", "S43-04", "S43-05", "S43-06"),
    "elmos-secure-zip-tar-extraction": ("S44-01", "S44-02", "S44-03", "S44-04", "S44-05", "S44-06"),
    "elmos-archive-bomb-and-path-traversal-defense": ("S45-01", "S45-02", "S45-03", "S45-04", "S45-05", "S45-06"),
    "elmos-project-root-language-framework-detection": ("S46-01", "S46-02", "S46-03", "S46-04", "S46-05", "S46-06"),
    "elmos-ignore-generated-vendored-file-classification": ("S47-01", "S47-02", "S47-03", "S47-04", "S47-05", "S47-06"),
    "elmos-repository-map-and-symbol-indexing": ("S48-01", "S48-02", "S48-03", "S48-04", "S48-05", "S48-06"),
    "elmos-project-package-version-and-incremental-update": ("S49-01", "S49-02", "S49-03", "S49-04", "S49-05", "S49-06"),
    "elmos-project-package-preview-and-review-ui": ("S50-01", "S50-02", "S50-03", "S50-04", "S50-05", "S50-06"),
}

ACCEPTANCE_TO_SKILL: Final[Mapping[str, str]] = {
    acceptance_id: skill
    for skill, acceptance_ids in ACCEPTANCE_IDS_BY_SKILL.items()
    for acceptance_id in acceptance_ids
}

if len(ACCEPTANCE_TO_SKILL) != 240:
    raise RuntimeError("multimodal acceptance catalog must contain exactly 240 unique IDs")

ACCEPTANCE_CATALOG_DIGEST: Final = canonical_digest(
    {
        "schema_version": "elmos-multimodal-acceptance-catalog-v1",
        "source_archive_sha256": SOURCE_ARCHIVE_SHA256,
        "acceptance_matrix_sha256": ACCEPTANCE_MATRIX_SHA256,
        "skills": ACCEPTANCE_IDS_BY_SKILL,
    }
)


def external_acceptance_status() -> list[dict[str, str]]:
    """Return all source obligations without claiming external execution."""

    return [
        {
            "acceptance_id": acceptance_id,
            "skill": ACCEPTANCE_TO_SKILL[acceptance_id],
            "evidence_scope": "EXTERNAL_OR_INDEPENDENT_REQUIRED",
            "external_evidence": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }
        for acceptance_id in sorted(ACCEPTANCE_TO_SKILL)
    ]
