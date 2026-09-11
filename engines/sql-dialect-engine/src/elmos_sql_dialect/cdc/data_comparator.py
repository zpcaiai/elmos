"""Data Comparator for Snapshot Chunk Hashing and Row-level Reconciliation.

Performs deterministic row normalization, primary-key range chunking,
SHA-256 / xxHash64 chunk digests, and binary difference pinpointing.
Optionally accelerates execution via the high-performance cdc-engine-rust binary.
"""

from __future__ import annotations

import decimal
import hashlib
import json
import os
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any


def normalize_cell_value(val: Any) -> str:
    """Normalize a single database value deterministically."""
    if val is None:
        return "§NULL§"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float | decimal.Decimal):
        # Normalize float/decimal representation: strip exponent and trailing zero noise
        if isinstance(val, float) and (val != val or val == float("inf") or val == float("-inf")):
            return str(val)
        d = decimal.Decimal(str(val))
        # Remove trailing zeroes from fractional part without scientific notation
        normalized = d.quantize(decimal.Decimal(1)) if d == d.to_integral() else d.normalize()
        return f"{normalized:f}"
    if isinstance(val, datetime):
        # Normalize to UTC ISO 8601 string
        if val.tzinfo is None:
            # Assume UTC if naive
            utc_dt = val.replace(tzinfo=UTC)
        else:
            utc_dt = val.astimezone(UTC)
        return utc_dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    if isinstance(val, date):
        return val.isoformat()
    if isinstance(val, bytes | bytearray | memoryview):
        return bytes(val).hex().lower()
    return str(val)


def normalize_row_dict(row: dict[str, Any], columns: list[str] | None = None) -> str:
    """Canonical string encoding of a row dictionary.

    Keys are ordered alphabetically (or by columns order) and mapped
    to deterministic cell strings.
    """
    keys = columns if columns is not None else sorted(row.keys())
    parts = [f"{k}={normalize_cell_value(row.get(k))}" for k in keys]
    return "§".join(parts)


def hash_normalized_string(normalized: str, algorithm: str = "sha256") -> str:
    """Hash a normalized string with SHA-256 or MD5 fallback."""
    if algorithm.lower() == "md5":
        return hashlib.md5(normalized.encode("utf-8"), usedforsecurity=False).hexdigest()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def hash_rows(rows: list[dict[str, Any]], columns: list[str] | None = None, algorithm: str = "sha256") -> str:
    """Compute an aggregated hash for a list of rows in a chunk."""
    if not rows:
        return hash_normalized_string("§EMPTY§", algorithm)

    row_hashes = [
        hash_normalized_string(normalize_row_dict(r, columns), algorithm)
        for r in rows
    ]
    # Aggregate chunk hash deterministically
    combined = "\n".join(row_hashes)
    return hash_normalized_string(combined, algorithm)


@dataclass
class RowDiff:
    primary_key: Any
    diff_type: str  # "MODIFIED", "MISSING_IN_TARGET", "EXTRA_IN_TARGET"
    source_row: dict[str, Any] | None = None
    target_row: dict[str, Any] | None = None
    differing_fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "primaryKey": self.primary_key,
            "diffType": self.diff_type,
            "sourceRow": self.source_row,
            "targetRow": self.target_row,
            "differingFields": self.differing_fields,
        }


@dataclass
class ChunkDiffResult:
    chunk_id: int
    start_pk: Any
    end_pk: Any
    matched: bool
    source_row_count: int
    target_row_count: int
    source_hash: str
    target_hash: str
    mismatched_pks: list[Any] = field(default_factory=list)
    diff_samples: list[RowDiff] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunkId": self.chunk_id,
            "startPk": self.start_pk,
            "endPk": self.end_pk,
            "matched": self.matched,
            "sourceRowCount": self.source_row_count,
            "targetRowCount": self.target_row_count,
            "sourceHash": self.source_hash,
            "targetHash": self.target_hash,
            "mismatchedPks": self.mismatched_pks,
            "diffSamples": [d.to_dict() for d in self.diff_samples],
        }


@dataclass
class SnapshotCompareReport:
    table_name: str
    primary_key: str
    total_chunks: int
    matched_chunks: int
    mismatched_chunks: int
    total_source_rows: int
    total_target_rows: int
    aligned_rows: int
    alignment_rate: float
    status: str  # "ALIGNED", "DIVERGED", "EMPTY"
    chunk_results: list[ChunkDiffResult] = field(default_factory=list)
    execution_engine: str = "PYTHON_CANONICAL"  # or "RUST_CDC_CORE"

    def to_dict(self) -> dict[str, Any]:
        return {
            "tableName": self.table_name,
            "primaryKey": self.primary_key,
            "totalChunks": self.total_chunks,
            "matchedChunks": self.matched_chunks,
            "mismatchedChunks": self.mismatched_chunks,
            "totalSourceRows": self.total_source_rows,
            "totalTargetRows": self.total_target_rows,
            "alignedRows": self.aligned_rows,
            "alignmentRate": self.alignment_rate,
            "status": self.status,
            "executionEngine": self.execution_engine,
            "chunkResults": [c.to_dict() for c in self.chunk_results],
        }


class DataComparator:
    """Compares snapshot tables using primary-key chunking and hash validation."""

    def __init__(
        self,
        chunk_size: int = 1000,
        hasher: str = "sha256",
        rust_binary_path: str | None = None,
        use_rust: bool = False,
        enable_rust: bool = False,
    ) -> None:
        self.chunk_size = chunk_size
        self.hasher = hasher
        self.use_rust = use_rust or enable_rust
        self.rust_binary_path = rust_binary_path or self._find_rust_binary()

    @staticmethod
    def _find_rust_binary() -> str | None:
        """Locate compiled cdc-engine-rust binary if present."""
        base_dir = os.path.dirname(__file__)
        candidates = [
            os.path.join(base_dir, "..", "..", "..", "cdc-engine-rust", "target", "release", "cdc-engine-rust"),
            os.path.join(base_dir, "..", "..", "..", "cdc-engine-rust", "target", "debug", "cdc-engine-rust"),
        ]
        for c in candidates:
            abs_path = os.path.abspath(c)
            if os.path.isfile(abs_path) and os.access(abs_path, os.X_OK):
                return abs_path
        return None

    def compare_row_sets(
        self,
        source_rows: list[dict[str, Any]],
        target_rows: list[dict[str, Any]],
        pk_col: str,
        table_name: str = "default_table",
        columns: list[str] | None = None,
    ) -> SnapshotCompareReport:
        """Compare in-memory source and target row sets with chunking."""
        # Index rows by primary key
        src_by_pk = {r[pk_col]: r for r in source_rows if pk_col in r}
        tgt_by_pk = {r[pk_col]: r for r in target_rows if pk_col in r}

        all_pks = sorted(set(src_by_pk.keys()) | set(tgt_by_pk.keys()))
        total_pks = len(all_pks)

        if total_pks == 0:
            return SnapshotCompareReport(
                table_name=table_name,
                primary_key=pk_col,
                total_chunks=0,
                matched_chunks=0,
                mismatched_chunks=0,
                total_source_rows=0,
                total_target_rows=0,
                aligned_rows=0,
                alignment_rate=1.0,
                status="EMPTY",
                execution_engine="PYTHON_CANONICAL",
            )

        # Slice PKs into chunks
        chunks: list[list[Any]] = []
        for i in range(0, total_pks, self.chunk_size):
            chunks.append(all_pks[i : i + self.chunk_size])

        chunk_results: list[ChunkDiffResult] = []
        aligned_rows_count = 0

        engine_used = (
            "RUST_CDC_CORE"
            if (self.use_rust and self.rust_binary_path and os.path.isfile(self.rust_binary_path))
            else "PYTHON_CANONICAL"
        )

        for idx, pk_slice in enumerate(chunks):
            start_pk = pk_slice[0]
            end_pk = pk_slice[-1]

            chunk_src_rows = [src_by_pk[k] for k in pk_slice if k in src_by_pk]
            chunk_tgt_rows = [tgt_by_pk[k] for k in pk_slice if k in tgt_by_pk]

            if engine_used == "RUST_CDC_CORE":
                chunk_res = self._compare_chunk_with_rust(
                    chunk_id=idx + 1,
                    start_pk=start_pk,
                    end_pk=end_pk,
                    chunk_src_rows=chunk_src_rows,
                    chunk_tgt_rows=chunk_tgt_rows,
                    pk_col=pk_col,
                )
                if chunk_res is not None:
                    if chunk_res.matched:
                        aligned_rows_count += len(chunk_src_rows)
                    else:
                        aligned_rows_count += max(0, len(chunk_src_rows) - len(chunk_res.mismatched_pks))
                    chunk_results.append(chunk_res)
                    continue

            src_hash = hash_rows(chunk_src_rows, columns, self.hasher)
            tgt_hash = hash_rows(chunk_tgt_rows, columns, self.hasher)

            if src_hash == tgt_hash:
                aligned_rows_count += len(chunk_src_rows)
                chunk_results.append(
                    ChunkDiffResult(
                        chunk_id=idx + 1,
                        start_pk=start_pk,
                        end_pk=end_pk,
                        matched=True,
                        source_row_count=len(chunk_src_rows),
                        target_row_count=len(chunk_tgt_rows),
                        source_hash=src_hash,
                        target_hash=tgt_hash,
                    )
                )
            else:
                # Granular inspection of mismatched chunk
                mismatched_pks: list[Any] = []
                diff_samples: list[RowDiff] = []

                for pk in pk_slice:
                    s_row = src_by_pk.get(pk)
                    t_row = tgt_by_pk.get(pk)

                    if s_row is None and t_row is not None:
                        mismatched_pks.append(pk)
                        diff_samples.append(
                            RowDiff(
                                primary_key=pk,
                                diff_type="EXTRA_IN_TARGET",
                                target_row=t_row,
                            )
                        )
                    elif s_row is not None and t_row is None:
                        mismatched_pks.append(pk)
                        diff_samples.append(
                            RowDiff(
                                primary_key=pk,
                                diff_type="MISSING_IN_TARGET",
                                source_row=s_row,
                            )
                        )
                    elif s_row is not None and t_row is not None:
                        s_norm = normalize_row_dict(s_row, columns)
                        t_norm = normalize_row_dict(t_row, columns)
                        if s_norm != t_norm:
                            mismatched_pks.append(pk)
                            # Identify differing field names
                            all_cols = sorted(set(s_row.keys()) | set(t_row.keys()))
                            differing = [
                                c
                                for c in all_cols
                                if normalize_cell_value(s_row.get(c)) != normalize_cell_value(t_row.get(c))
                            ]
                            diff_samples.append(
                                RowDiff(
                                    primary_key=pk,
                                    diff_type="MODIFIED",
                                    source_row=s_row,
                                    target_row=t_row,
                                    differing_fields=differing,
                                )
                            )
                        else:
                            aligned_rows_count += 1

                chunk_results.append(
                    ChunkDiffResult(
                        chunk_id=idx + 1,
                        start_pk=start_pk,
                        end_pk=end_pk,
                        matched=False,
                        source_row_count=len(chunk_src_rows),
                        target_row_count=len(chunk_tgt_rows),
                        source_hash=src_hash,
                        target_hash=tgt_hash,
                        mismatched_pks=mismatched_pks,
                        diff_samples=diff_samples,
                    )
                )

        matched_count = sum(1 for c in chunk_results if c.matched)
        mismatched_count = len(chunk_results) - matched_count
        alignment_rate = round(aligned_rows_count / total_pks, 6) if total_pks > 0 else 1.0

        return SnapshotCompareReport(
            table_name=table_name,
            primary_key=pk_col,
            total_chunks=len(chunk_results),
            matched_chunks=matched_count,
            mismatched_chunks=mismatched_count,
            total_source_rows=len(source_rows),
            total_target_rows=len(target_rows),
            aligned_rows=aligned_rows_count,
            alignment_rate=alignment_rate,
            status="ALIGNED" if (mismatched_count == 0 and alignment_rate == 1.0) else "DIVERGED",
            chunk_results=chunk_results,
            execution_engine=engine_used,
        )

    def _compare_chunk_with_rust(
        self,
        chunk_id: int,
        start_pk: Any,
        end_pk: Any,
        chunk_src_rows: list[dict[str, Any]],
        chunk_tgt_rows: list[dict[str, Any]],
        pk_col: str,
    ) -> ChunkDiffResult | None:
        """Delegate single chunk comparison to Rust CLI."""
        import tempfile

        if not self.rust_binary_path or not os.path.isfile(self.rust_binary_path):
            return None

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as s_file, tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False
        ) as t_file:
            json.dump(chunk_src_rows, s_file)
            json.dump(chunk_tgt_rows, t_file)
            s_path = s_file.name
            t_path = t_file.name

        try:
            cmd = [
                self.rust_binary_path,
                "compare-chunks",
                "--source",
                s_path,
                "--target",
                t_path,
                "--pk",
                pk_col,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            output_data = json.loads(result.stdout)

            return ChunkDiffResult(
                chunk_id=chunk_id,
                start_pk=start_pk,
                end_pk=end_pk,
                matched=output_data.get("matched", False),
                source_row_count=len(chunk_src_rows),
                target_row_count=len(chunk_tgt_rows),
                source_hash=output_data.get("source_hash", ""),
                target_hash=output_data.get("target_hash", ""),
                mismatched_pks=output_data.get("mismatched_pks", []),
            )
        except Exception:
            return None
        finally:
            if os.path.exists(s_path):
                os.remove(s_path)
            if os.path.exists(t_path):
                os.remove(t_path)
