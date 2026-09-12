"""Reconciliation Evidence Reporter for Heterogeneous CDC Migrations.

Assembles schema diffs, chunk hash results, and incremental event streams into
standardized, machine-readable evidence adhering to Non-Self-Certification contracts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from .data_comparator import SnapshotCompareReport
from .event_comparator import EventReconciliationReport
from .schema_comparator import SchemaDiffReport


@dataclass
class CdcReconciliationReport:
    source_dialect: str
    target_dialect: str
    target_id: str
    execution_timestamp: str
    schema_diffs: list[SchemaDiffReport] = field(default_factory=list)
    snapshot_diffs: list[SnapshotCompareReport] = field(default_factory=list)
    event_diffs: list[EventReconciliationReport] = field(default_factory=list)
    execution_mode: str = "LOCAL_SIMULATION"  # "LOCAL_CONTAINER_RUN", "LOCAL_SIMULATION"
    evidence_digest: str = ""

    def generate_summary(self) -> dict[str, Any]:
        """Compute aggregated reconciliation metrics and fail-closed status."""
        schema_compatible = all(s.is_compatible for s in self.schema_diffs) if self.schema_diffs else True
        total_src_rows = sum(d.total_source_rows for d in self.snapshot_diffs)
        total_tgt_rows = sum(d.total_target_rows for d in self.snapshot_diffs)
        aligned_rows = sum(d.aligned_rows for d in self.snapshot_diffs)
        max_rows = max(total_src_rows, total_tgt_rows)
        alignment_rate = round(aligned_rows / max_rows, 6) if max_rows > 0 else 1.0

        all_events_consistent = all(e.state_consistent for e in self.event_diffs) if self.event_diffs else True

        if schema_compatible and alignment_rate == 1.0 and all_events_consistent:
            reconciliation_status = "LOCAL_ALIGNED"
        else:
            reconciliation_status = "DIVERGED"

        summary = {
            "schemaVersion": "1.0",
            "reportType": "elmos.cdc-reconciliation-evidence",
            "generatedAt": self.execution_timestamp,
            "sourceDialect": self.source_dialect,
            "targetDialect": self.target_dialect,
            "targetId": self.target_id,
            "executionMode": self.execution_mode,
            "reconciliationStatus": reconciliation_status,
            # Mandatory non-self-certification boundaries
            "implementationStatus": "LOCAL_ADAPTER",
            "externalExecution": "NOT_RUN" if self.execution_mode == "LOCAL_SIMULATION" else "LOCAL_CONTAINER_RUN",
            "certification": "NOT_CERTIFIED",
            "claim": (
                "Self-attested local reconciliation evidence. Does not constitute production "
                "certification or independent verifier sign-off."
            ),
            "metrics": {
                "tablesEvaluated": len(self.schema_diffs) or len(self.snapshot_diffs),
                "schemaCompatible": schema_compatible,
                "totalSourceRows": total_src_rows,
                "totalTargetRows": total_tgt_rows,
                "alignedRows": aligned_rows,
                "mismatchedRows": max_rows - aligned_rows,
                "alignmentRate": alignment_rate,
                "eventStreamConsistent": all_events_consistent,
            },
            "schemaDiscrepancies": [
                s.to_dict() for s in self.schema_diffs if not s.is_identical
            ],
            "snapshotDiscrepancies": [
                d.to_dict() for d in self.snapshot_diffs if d.status != "ALIGNED"
            ],
            "eventDiscrepancies": [
                e.to_dict() for e in self.event_diffs if e.status != "CONSISTENT"
            ],
        }

        # Calculate reproducible hash digest over the canonical JSON
        encoded = json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = f"sha256:{hashlib.sha256(encoded.encode('utf-8')).hexdigest()}"
        summary["evidenceDigest"] = digest
        return summary

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.generate_summary(), indent=indent, ensure_ascii=False)

    @classmethod
    def build_report(
        cls,
        source_dialect: str,
        target_dialect: str,
        target_id: str,
        schema_results: dict[str, Any] | list[SchemaDiffReport] | None = None,
        data_results: dict[str, Any] | list[SnapshotCompareReport] | None = None,
        event_results: dict[str, Any] | list[EventReconciliationReport] | None = None,
        execution_mode: str = "LOCAL_SIMULATION",
    ) -> dict[str, Any]:
        s_diffs = list(schema_results.values()) if isinstance(schema_results, dict) else (schema_results or [])
        d_diffs = list(data_results.values()) if isinstance(data_results, dict) else (data_results or [])
        e_diffs = list(event_results.values()) if isinstance(event_results, dict) else (event_results or [])

        report = cls(
            source_dialect=source_dialect,
            target_dialect=target_dialect,
            target_id=target_id,
            execution_timestamp=datetime.now(UTC).isoformat(),
            schema_diffs=s_diffs,
            snapshot_diffs=d_diffs,
            event_diffs=e_diffs,
            execution_mode=execution_mode,
        )
        return report.generate_summary()

    @staticmethod
    def save_report(report_data: dict[str, Any], path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(report_data, indent=2, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def load_report(path: str | Path) -> dict[str, Any]:
        p = Path(path)
        data = json.loads(p.read_text(encoding="utf-8"))
        return cast(dict[str, Any], data)

    @staticmethod
    def verify_report_integrity(report_data: dict[str, Any]) -> bool:
        if "evidenceDigest" not in report_data:
            return False
        expected = str(report_data["evidenceDigest"])
        copy_data = dict(report_data)
        del copy_data["evidenceDigest"]
        encoded = json.dumps(copy_data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        actual = f"sha256:{hashlib.sha256(encoded.encode('utf-8')).hexdigest()}"
        return bool(actual == expected)


CdcReporter = CdcReconciliationReport


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate CDC Reconciliation Evidence Report.")
    parser.add_argument("--source-dialect", default="postgres", help="Source database dialect")
    parser.add_argument("--target-dialect", default="opengauss", help="Target database dialect")
    parser.add_argument("--target-id", default="opengauss", help="ChinaDB target identifier")
    parser.add_argument("--output", default="cdc-reconciliation-report.json", help="Output report path")
    parser.add_argument("--mode", default="LOCAL_CONTAINER_RUN", choices=["LOCAL_CONTAINER_RUN", "LOCAL_SIMULATION"])
    args = parser.parse_args(argv)

    timestamp = datetime.now(UTC).isoformat()

    report = CdcReconciliationReport(
        source_dialect=args.source_dialect,
        target_dialect=args.target_dialect,
        target_id=args.target_id,
        execution_timestamp=timestamp,
        execution_mode=args.mode,
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report.to_json(), encoding="utf-8")
    print(f"Reconciliation evidence report written to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
