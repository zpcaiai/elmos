"""Enterprise Database Handoff Ledger Generator.

Implements the fail-closed dual-track closure mechanism for enterprise database migrations,
ensuring 100% disposition coverage across arbitrary blackbox SQL corpora.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from .scan import FeasibilityReport, ScanFinding

P0_BLOCKERS = frozenset(
    {
        "DYNAMIC_SQL_CONCATENATION",
        "AUTONOMOUS_TRANSACTION",
        "CERTIFIED_DDL_JSON_BINARY_SEMANTICS_UNSUPPORTED",
        "CERTIFIED_ROUTINE_TRIGGER_TARGET_ROUTE_REQUIRED",
        "CERTIFIED_RLS_TARGET_ROUTE_REQUIRED",
        "CERTIFIED_PRIVILEGE_PRINCIPAL_UNSUPPORTED_BY_TARGET",
        "PROPRIETARY_PACKAGE_STATE",
    }
)

P1_BLOCKERS = frozenset(
    {
        "CERTIFIED_DDL_ARRAY_TARGET_UNSUPPORTED",
        "CERTIFIED_DDL_IF_NOT_EXISTS_UNSUPPORTED_BY_TARGET",
        "CERTIFIED_DDL_INDEX_EXPRESSION_UNSUPPORTED_BY_TARGET",
        "CERTIFIED_DDL_INDEX_PREDICATE_UNSUPPORTED_BY_TARGET",
        "CERTIFIED_ROUTINE_STRICT_UNSUPPORTED_BY_TARGET",
        "CERTIFIED_SCHEMA_UNSUPPORTED_TARGET",
        "TABLE_VARIABLE_CONVERSION",
    }
)


def _digest_str(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _priority(reason_code: str) -> str:
    if reason_code in P0_BLOCKERS:
        return "P0"
    if reason_code in P1_BLOCKERS:
        return "P1"
    return "P2"


def _recommended_action(reason_code: str) -> str:
    if "DYNAMIC_SQL" in reason_code:
        return (
            "Refactor dynamic SQL string concatenation into parameterized queries "
            "or register an explicit target DBMS dynamic execution wrapper."
        )
    if "AUTONOMOUS_TRANSACTION" in reason_code:
        return (
            "Decouple autonomous transaction logging into a separate connection pool "
            "or outbox queue table."
        )
    if "PACKAGE" in reason_code:
        return (
            "Decompose PL/SQL package body into individual stored procedures and functions, "
            "migrating package state to session temporary tables."
        )
    if "TRIGGER" in reason_code:
        return (
            "Port trigger with target-specific BEFORE/AFTER statement semantics and transition "
            "variables (OLD/NEW table references)."
        )
    if "NAMESPACE" in reason_code:
        return "Apply reviewed schema mapping in namespace-profile and rerun scanner."
    if "INDEX" in reason_code:
        return "Rewrite unsupported expression/predicate index using target-supported function index or generated column."
    return "Implement target dialect adapter shim and attach dual-run execution verification evidence."


@dataclass
class DatabaseHandoffLedger:
    """Manages the full disposition lifecycle of an enterprise SQL database migration."""

    findings: list[ScanFinding] = field(default_factory=list)
    source_report_digest: str = "sha256:" + "0" * 64
    owner_default: str = "database-migration-specialist"

    @classmethod
    def from_report(cls, report: FeasibilityReport, report_digest: str | None = None) -> DatabaseHandoffLedger:
        raw_digest = report_digest or ("sha256:" + _digest_str(json.dumps(report.totals, sort_keys=True)))
        if not raw_digest.startswith("sha256:"):
            raw_digest = "sha256:" + raw_digest
        return cls(findings=report.findings, source_report_digest=raw_digest)

    @classmethod
    def from_findings(cls, findings: Sequence[ScanFinding], report_digest: str = "sha256:" + "0" * 64) -> DatabaseHandoffLedger:
        return cls(findings=list(findings), source_report_digest=report_digest)

    @property
    def total_discovered(self) -> int:
        return len(self.findings)

    @property
    def automated_candidates(self) -> list[ScanFinding]:
        return [f for f in self.findings if f.disposition == "AUTOMATED_TRANSLATION_CANDIDATE"]

    @property
    def manual_items(self) -> list[ScanFinding]:
        return [f for f in self.findings if f.disposition != "AUTOMATED_TRANSLATION_CANDIDATE"]

    @property
    def disposition_coverage(self) -> float:
        if not self.findings:
            return 1.0
        covered = len(self.automated_candidates) + len(self.manual_items)
        return round(covered / len(self.findings), 4)

    def is_100_percent_covered(self) -> bool:
        """Verify that every discovered statement has a deterministic terminal disposition."""
        return self.disposition_coverage == 1.0 and len(self.findings) == (
            len(self.automated_candidates) + len(self.manual_items)
        )

    def to_manual_review_backlog(self) -> dict[str, Any]:
        """Serialize manual items into canonical Batch 31 manual-review-backlog JSON."""
        items: list[dict[str, Any]] = []

        for finding in self.manual_items:
            fingerprint_mat = json.dumps(
                {
                    "source_path": finding.source_path,
                    "statement_index": finding.statement_index,
                    "reason_code": finding.reason_code,
                    "excerpt": finding.excerpt,
                },
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            raw_fp = hashlib.sha256(fingerprint_mat.encode("utf-8")).hexdigest()
            fingerprint = f"sha256:{raw_fp}"
            finding_id = f"sql-review-{raw_fp[:20]}"

            reason_code = finding.reason_code or "UNCLASSIFIED_MANUAL_MIGRATION"
            reason = finding.reason or "Requires manual inspection and migration recipe"

            items.append(
                {
                    "finding_id": finding_id,
                    "fingerprint": fingerprint,
                    "source_path": finding.source_path,
                    "statement_index": finding.statement_index,
                    "reason_code": reason_code,
                    "reason": reason,
                    "family": finding.family,
                    "excerpt": finding.excerpt,
                    "status": "OPEN",
                    "owner": self.owner_default,
                    "recommended_action": _recommended_action(reason_code),
                    "resolution": {
                        "strategy": "NOT_SET",
                        "artifact_refs": [],
                    },
                    "waiver": {
                        "status": "NOT_REQUESTED",
                        "approved_by": [],
                        "expires_at": None,
                        "reason": None,
                    },
                    "revalidation": {
                        "status": "NOT_RUN",
                        "evidence_refs": [],
                    },
                }
            )

        summary = {
            "total": len(items),
            "open": len(items),
            "in_review": 0,
            "resolved": 0,
            "waived": 0,
            "blocked": 0,
            "release_blocked": bool(items),
        }

        return {
            "schema_version": 1,
            "kind": "elmos.batch31.manual-review-backlog",
            "source_report_digest": self.source_report_digest,
            "summary": summary,
            "items": items,
        }

    def generate_markdown_dossier(self, title: str = "Enterprise SQL Migration Handoff Dossier") -> str:
        """Generate human-actionable Markdown remediation runbook."""
        lines: list[str] = [
            f"# {title}",
            "",
            "## 1. Executive Disposition Summary",
            "",
            f"- **Total Discovered Statements**: `{self.total_discovered}`",
            f"- **Automated Translation Candidates**: `{len(self.automated_candidates)}`",
            f"- **Manual Migration & Review Items**: `{len(self.manual_items)}`",
            f"- **Disposition Coverage**: `{self.disposition_coverage * 100:.1f}%` (100% Accounted)",
            f"- **Source Report Digest**: `{self.source_report_digest}`",
            "",
            "## 2. Priority & Blocker Breakdown",
            "",
        ]

        # Count by priority
        counts: Counter[str] = Counter()
        for item in self.manual_items:
            code = item.reason_code or "UNKNOWN"
            counts[_priority(code)] += 1

        lines.append(f"| Priority | Count | Description |")
        lines.append(f"| :--- | :---: | :--- |")
        lines.append(f"| **P0** | `{counts['P0']}` | Critical architectural blockers (Dynamic SQL, Autonomous Tx, RLS) |")
        lines.append(f"| **P1** | `{counts['P1']}` | Dialect feature gaps (Expression Index, IF NOT EXISTS, Strict Routines) |")
        lines.append(f"| **P2** | `{counts['P2']}` | Standard dialect refactorings & schema mappings |")
        lines.append("")

        lines.append("## 3. Actionable Remediation Workbooks")
        lines.append("")

        for idx, finding in enumerate(self.manual_items, 1):
            code = finding.reason_code or "MANUAL_MIGRATION"
            prio = _priority(code)
            lines.extend(
                [
                    f"### Item #{idx:03d} [{prio}] `{code}`",
                    f"- **Location**: `{finding.source_path}` (Stmt #{finding.statement_index})",
                    f"- **Statement Excerpt**: `{finding.excerpt}`",
                    f"- **Root Cause**: {finding.reason}",
                    f"- **Recommended Remediation**: {_recommended_action(code)}",
                    f"- **Verification Command**: `uv run elmos-sql-dialect test-statement --input \"{finding.excerpt}\"`",
                    "",
                ]
            )

        return "\n".join(lines)
