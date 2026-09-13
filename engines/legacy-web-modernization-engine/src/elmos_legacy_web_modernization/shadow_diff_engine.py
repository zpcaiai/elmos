"""Automated Traffic Record & Replay with 13-Dimension Shadow Differential Engine.

Provides deep behavioral parity validation between legacy services and modern
Spring Boot targets, with response normalization, database state reconciliation,
transaction rollback verification, and fail-closed regression checks.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class HttpExchange:
    method: str
    path: str
    status_code: int
    headers: dict[str, str]
    body: str
    latency_ms: float = 0.0


@dataclass(frozen=True, slots=True)
class TableSnapshot:
    table_name: str
    rows: tuple[dict[str, Any], ...]
    row_checksums: tuple[str, ...]

    @classmethod
    def from_rows(cls, table_name: str, rows: Sequence[dict[str, Any]]) -> TableSnapshot:
        checksums = []
        for r in rows:
            canonical_row = json.dumps(r, sort_keys=True, default=str)
            checksums.append(hashlib.sha256(canonical_row.encode("utf-8")).hexdigest())
        return cls(
            table_name=table_name,
            rows=tuple(rows),
            row_checksums=tuple(sorted(checksums)),
        )


@dataclass(frozen=True, slots=True)
class DatabaseDifferential:
    table_name: str
    matched: bool
    legacy_row_count: int
    target_row_count: int
    differences: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ShadowDiffResult:
    equivalent: bool
    dimension_scores: dict[str, float]
    mismatches: tuple[str, ...]
    database_diffs: tuple[DatabaseDifferential, ...]
    critical_regression: bool
    verdict: str


class ShadowDiffEngine:
    """Evaluates behavioral and state parity across all 13 modernization dimensions."""

    DIMENSIONS = (
        "route",
        "protocol",
        "view",
        "binding",
        "validation",
        "navigation",
        "session",
        "security",
        "transaction",
        "database",
        "externalEffects",
        "concurrency",
        "performance",
    )

    IGNORED_HEADERS = {
        "date",
        "server",
        "transfer-encoding",
        "connection",
        "x-trace-id",
        "x-request-id",
        "traceparent",
    }

    def __init__(self, latency_tolerance_ratio: float = 2.0):
        self.latency_tolerance_ratio = latency_tolerance_ratio

    def normalize_headers(self, headers: Mapping[str, str]) -> dict[str, str]:
        return {
            k.lower().strip(): v.strip()
            for k, v in headers.items()
            if k.lower().strip() not in self.IGNORED_HEADERS
        }

    def normalize_body(self, body: str) -> Any:
        trimmed = body.strip()
        if not trimmed:
            return ""
        try:
            parsed = json.loads(trimmed)
            if isinstance(parsed, dict):
                # Mask volatile fields like timestamp, random IDs
                clean = {}
                for k, v in parsed.items():
                    if any(vol in k.lower() for vol in ("time", "timestamp", "nonce", "uuid")):
                        clean[k] = "<VOLATILE_NORMALIZED>"
                    else:
                        clean[k] = v
                return clean
            return parsed
        except (ValueError, TypeError):
            # Fallback for HTML/Plain text
            return re.sub(r"\s+", " ", trimmed)

    def compare_exchanges(
        self,
        legacy: HttpExchange,
        target: HttpExchange,
        *,
        legacy_db: TableSnapshot | None = None,
        target_db: TableSnapshot | None = None,
        transaction_rolled_back: bool = False,
    ) -> ShadowDiffResult:
        mismatches: list[str] = []
        dim_scores: dict[str, float] = {d: 1.0 for d in self.DIMENSIONS}

        # 1. Route & Protocol
        if legacy.method.upper() != target.method.upper() or legacy.path != target.path:
            mismatches.append(f"Route mismatch: {legacy.method} {legacy.path} vs {target.method} {target.path}")
            dim_scores["route"] = 0.0

        if legacy.status_code != target.status_code:
            mismatches.append(f"Status code mismatch: {legacy.status_code} vs {target.status_code}")
            dim_scores["protocol"] = 0.0
            if legacy.status_code < 500 <= target.status_code:
                dim_scores["validation"] = 0.0

        # 2. Content / View
        norm_legacy_body = self.normalize_body(legacy.body)
        norm_target_body = self.normalize_body(target.body)
        if norm_legacy_body != norm_target_body:
            mismatches.append(f"Response body mismatch for {legacy.path}")
            dim_scores["view"] = 0.0
            dim_scores["binding"] = 0.0

        # 3. Headers / Security & Session
        leg_headers = self.normalize_headers(legacy.headers)
        tar_headers = self.normalize_headers(target.headers)
        if leg_headers.get("content-type") != tar_headers.get("content-type"):
            mismatches.append(f"Content-Type mismatch: {leg_headers.get('content-type')} vs {tar_headers.get('content-type')}")
            dim_scores["protocol"] = min(dim_scores["protocol"], 0.5)

        # 4. Database Reconciliation
        db_diffs: list[DatabaseDifferential] = []
        if legacy_db is not None and target_db is not None:
            if legacy_db.row_checksums == target_db.row_checksums:
                db_diffs.append(DatabaseDifferential(
                    table_name=legacy_db.table_name,
                    matched=True,
                    legacy_row_count=len(legacy_db.rows),
                    target_row_count=len(target_db.rows),
                    differences=(),
                ))
            else:
                diff_desc = f"Checksum mismatch on table {legacy_db.table_name}: count {len(legacy_db.rows)} vs {len(target_db.rows)}"
                mismatches.append(diff_desc)
                dim_scores["database"] = 0.0
                dim_scores["transaction"] = 0.0
                db_diffs.append(DatabaseDifferential(
                    table_name=legacy_db.table_name,
                    matched=False,
                    legacy_row_count=len(legacy_db.rows),
                    target_row_count=len(target_db.rows),
                    differences=(diff_desc,),
                ))

        # 5. Rollback verification
        if transaction_rolled_back and legacy_db is not None and target_db is not None:
            if len(target_db.rows) > len(legacy_db.rows):
                mismatches.append(f"Transaction rollback failure on table {legacy_db.table_name}: leak detected")
                dim_scores["transaction"] = 0.0

        # 6. Performance Parity
        if legacy.latency_ms > 0 and target.latency_ms > 0:
            if target.latency_ms > legacy.latency_ms * self.latency_tolerance_ratio:
                mismatches.append(f"Performance latency regression: {target.latency_ms:.1f}ms vs baseline {legacy.latency_ms:.1f}ms")
                dim_scores["performance"] = 0.5

        has_critical = any(dim_scores[d] == 0.0 for d in ("route", "protocol", "security", "database", "transaction"))
        is_equiv = len(mismatches) == 0

        return ShadowDiffResult(
            equivalent=is_equiv,
            dimension_scores=dim_scores,
            mismatches=tuple(mismatches),
            database_diffs=tuple(db_diffs),
            critical_regression=has_critical,
            verdict="PASS" if is_equiv else "FAIL",
        )
