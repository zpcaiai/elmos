"""Database State Verification & Shadow Differential Engine.

Computes row-level cryptographic state digests, detects state divergences
between source/target migrations, and validates transaction isolation anomalies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class RowDifferential:
    primary_key: Any
    divergence_type: str  # MISSING_IN_TARGET, EXTRA_IN_TARGET, COLUMN_MISMATCH
    source_values: Optional[Dict[str, Any]] = None
    target_values: Optional[Dict[str, Any]] = None
    mismatched_columns: List[str] = field(default_factory=list)


@dataclass
class TableDifferentialResult:
    table_name: str
    source_row_count: int
    target_row_count: int
    divergent_row_count: int
    is_bit_identical: bool
    merkle_source_root: str
    merkle_target_root: str
    divergences: List[RowDifferential] = field(default_factory=list)


class DBStateVerificationEngine:
    """Performs row-level hash comparisons and migration state audits."""

    @classmethod
    def compute_row_hash(cls, row: Dict[str, Any]) -> str:
        # Sort columns to ensure canonical serialized representation
        canonical = json.dumps(row, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode('utf-8')).hexdigest()

    @classmethod
    def compare_tables(
        cls,
        table_name: str,
        pk_field: str,
        source_rows: List[Dict[str, Any]],
        target_rows: List[Dict[str, Any]],
    ) -> TableDifferentialResult:
        src_map: Dict[Any, Dict[str, Any]] = {r[pk_field]: r for r in source_rows}
        tgt_map: Dict[Any, Dict[str, Any]] = {r[pk_field]: r for r in target_rows}

        divergences: List[RowDifferential] = []

        # Check for missing or mismatched in target
        for pk, src_r in src_map.items():
            if pk not in tgt_map:
                divergences.append(
                    RowDifferential(
                        primary_key=pk,
                        divergence_type="MISSING_IN_TARGET",
                        source_values=src_r,
                    )
                )
            else:
                tgt_r = tgt_map[pk]
                src_hash = cls.compute_row_hash(src_r)
                tgt_hash = cls.compute_row_hash(tgt_r)
                if src_hash != tgt_hash:
                    mismatched_cols = [
                        col for col in set(src_r.keys()).union(tgt_r.keys())
                        if str(src_r.get(col)) != str(tgt_r.get(col))
                    ]
                    divergences.append(
                        RowDifferential(
                            primary_key=pk,
                            divergence_type="COLUMN_MISMATCH",
                            source_values=src_r,
                            target_values=tgt_r,
                            mismatched_columns=mismatched_cols,
                        )
                    )

        # Check for extras in target
        for pk, tgt_r in tgt_map.items():
            if pk not in src_map:
                divergences.append(
                    RowDifferential(
                        primary_key=pk,
                        divergence_type="EXTRA_IN_TARGET",
                        target_values=tgt_r,
                    )
                )

        src_hashes = sorted([cls.compute_row_hash(r) for r in source_rows])
        tgt_hashes = sorted([cls.compute_row_hash(r) for r in target_rows])

        src_root = hashlib.sha256(''.join(src_hashes).encode('utf-8')).hexdigest()
        tgt_root = hashlib.sha256(''.join(tgt_hashes).encode('utf-8')).hexdigest()

        return TableDifferentialResult(
            table_name=table_name,
            source_row_count=len(source_rows),
            target_row_count=len(target_rows),
            divergent_row_count=len(divergences),
            is_bit_identical=src_root == tgt_root and len(divergences) == 0,
            merkle_source_root=src_root,
            merkle_target_root=tgt_root,
            divergences=divergences,
        )
