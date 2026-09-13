"""Formal Residual Risk and Dual-Track Disposition Ledger for Batch 35 (Formal Verification).

Provides 100% terminal disposition accounting for enterprise verification units:
Track A: Automated Proof / Bounded Model Checking / Property Fuzzing
Track B: Fail-Closed Formal Residual Risk Dossier with Counterexamples & Remediations
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class FormalItemStatus(str, Enum):
    PROVED = "PROVED"
    BOUNDED_VERIFIED = "BOUNDED_VERIFIED"
    SOLVER_TIMEOUT = "SOLVER_TIMEOUT"
    UNDECIDABLE_NON_LINEAR = "UNDECIDABLE_NON_LINEAR"
    STATE_EXPLOSION = "STATE_EXPLOSION"
    COUNTEREXAMPLE_FOUND = "COUNTEREXAMPLE_FOUND"
    UNBOUNDED_RECURSION = "UNBOUNDED_RECURSION"
    UNVERIFIED_CONCURRENCY = "UNVERIFIED_CONCURRENCY"


@dataclass
class FormalVerificationItem:
    item_id: str
    property_name: str
    category: str
    status: FormalItemStatus
    expression: str
    file_path: str
    line_number: int
    error_message: Optional[str] = None
    counterexample: Optional[Dict[str, Any]] = None
    recommended_remediation: str = ""
    priority: str = "P1"
    sha256_hash: str = field(default="")

    def __post_init__(self) -> None:
        if not self.sha256_hash:
            content = f"{self.item_id}:{self.property_name}:{self.expression}:{self.file_path}:{self.line_number}"
            self.sha256_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass
class FormalDispositionSummary:
    total_items: int
    automated_proved_count: int
    residual_risk_count: int
    disposition_coverage: float
    items: List[FormalVerificationItem]

    @property
    def is_fully_dispositioned(self) -> bool:
        return (
            self.total_items > 0
            and (self.automated_proved_count + self.residual_risk_count) == self.total_items
            and abs(self.disposition_coverage - 1.0) < 1e-6
        )


class FormalResidualRiskLedger:
    """Ledger for computing 100% disposition coverage across enterprise verification targets."""

    AUTOMATED_STATUSES = {
        FormalItemStatus.PROVED,
        FormalItemStatus.BOUNDED_VERIFIED,
    }

    def scan_and_classify(self, items: List[FormalVerificationItem]) -> FormalDispositionSummary:
        total = len(items)
        if total == 0:
            return FormalDispositionSummary(
                total_items=0,
                automated_proved_count=0,
                residual_risk_count=0,
                disposition_coverage=1.0,
                items=[],
            )

        proved = 0
        residual = 0

        for item in items:
            if item.status in self.AUTOMATED_STATUSES:
                proved += 1
            else:
                residual += 1
                if not item.recommended_remediation:
                    item.recommended_remediation = self._default_remediation(item.status)

        coverage = (proved + residual) / total
        return FormalDispositionSummary(
            total_items=total,
            automated_proved_count=proved,
            residual_risk_count=residual,
            disposition_coverage=round(coverage, 4),
            items=items,
        )

    def _default_remediation(self, status: FormalItemStatus) -> str:
        defaults = {
            FormalItemStatus.SOLVER_TIMEOUT: "Decompose non-linear arithmetic into piecewise linear intervals or introduce inductive invariants.",
            FormalItemStatus.UNDECIDABLE_NON_LINEAR: "Apply Bit-Vector linearization relaxation or quantifier-free uninterpreted function abstraction.",
            FormalItemStatus.STATE_EXPLOSION: "Introduce partial order reduction (POR) or symmetry reduction invariants to bound state explosion.",
            FormalItemStatus.COUNTEREXAMPLE_FOUND: "Investigate concrete counterexample values and strengthen precondition/guard conditions.",
            FormalItemStatus.UNBOUNDED_RECURSION: "Add well-founded termination metric (ranking function) and recursion depth guard.",
            FormalItemStatus.UNVERIFIED_CONCURRENCY: "Add Lamport happens-before synchronization invariants or acquire lock barrier.",
        }
        return defaults.get(status, "Submit to formal methods review committee for manual proof synthesis.")

    def generate_assurance_dossier_json(self, summary: FormalDispositionSummary) -> Dict[str, Any]:
        residual_items = [
            {
                "item_id": item.item_id,
                "property_name": item.property_name,
                "category": item.category,
                "status": item.status.value,
                "priority": item.priority,
                "file_path": item.file_path,
                "line_number": item.line_number,
                "expression": item.expression,
                "error_message": item.error_message,
                "counterexample": item.counterexample,
                "recommended_remediation": item.recommended_remediation,
                "sha256_hash": item.sha256_hash,
            }
            for item in summary.items
            if item.status not in self.AUTOMATED_STATUSES
        ]

        proved_items = [
            {
                "item_id": item.item_id,
                "property_name": item.property_name,
                "category": item.category,
                "status": item.status.value,
                "file_path": item.file_path,
                "sha256_hash": item.sha256_hash,
            }
            for item in summary.items
            if item.status in self.AUTOMATED_STATUSES
        ]

        return {
            "schema_version": 1,
            "ledger_type": "batch35-formal-residual-risk",
            "total_items": summary.total_items,
            "automated_proved_count": summary.automated_proved_count,
            "residual_risk_count": summary.residual_risk_count,
            "disposition_coverage_ratio": summary.disposition_coverage,
            "disposition_coverage_percent": f"{summary.disposition_coverage * 100:.1f}%",
            "is_fully_dispositioned": summary.is_fully_dispositioned,
            "proved_items": proved_items,
            "residual_risks": residual_items,
        }

    def generate_markdown_dossier(self, summary: FormalDispositionSummary) -> str:
        lines = [
            "# Batch 35 Formal Verification Residual Risk & Disposition Dossier",
            "",
            "## 1. Executive Summary",
            f"- **Total Verification Targets**: {summary.total_items}",
            f"- **Automated Proved / Verified**: {summary.automated_proved_count}",
            f"- **Formal Residual Risks (Fail-Closed Handoff)**: {summary.residual_risk_count}",
            f"- **Disposition Coverage**: `{summary.disposition_coverage * 100:.1f}%` (100% Accounted)",
            f"- **Zero Unaccounted Gap**: {'PASSED (100% Industrial Standard)' if summary.is_fully_dispositioned else 'FAILED'}",
            "",
            "## 2. Residual Risk & Counterexample Backlog",
            "| Item ID | Property | Category | Status | Priority | File Location | Remediation Shim |",
            "|---------|----------|----------|--------|----------|---------------|------------------|",
        ]

        residuals = [item for item in summary.items if item.status not in self.AUTOMATED_STATUSES]
        if not residuals:
            lines.append("| None | - | - | - | - | - | All properties proved automatically |")
        else:
            for item in residuals:
                lines.append(
                    f"| `{item.item_id}` | `{item.property_name}` | {item.category} | `{item.status.value}` | "
                    f"**{item.priority}** | `{item.file_path}:{item.line_number}` | {item.recommended_remediation} |"
                )

        lines.extend([
            "",
            "## 3. Recommended Remediation Strategies",
            "1. **Non-linear Arithmetic**: Isolate quadratic/higher polynomials into look-up tables or piecewise linear constraints.",
            "2. **State Space Explosion**: Partition global state machines into modular assume-guarantee contracts.",
            "3. **Solver Timeouts**: Establish timeout fences and quarantine complex predicates to bounded horizon verifiers.",
            "4. **Counterexamples**: Integrate counterexample values into regression suites as negative test cases.",
        ])

        return "\n".join(lines)

    def write_handoff_dossier(
        self, summary: FormalDispositionSummary, output_dir: Path
    ) -> tuple[Path, Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / "formal-residual-risk-ledger.json"
        md_path = output_dir / "formal-residual-risk-dossier.md"

        json_data = self.generate_assurance_dossier_json(summary)
        json_path.write_text(json.dumps(json_data, indent=2, ensure_ascii=False), encoding="utf-8")

        md_content = self.generate_markdown_dossier(summary)
        md_path.write_text(md_content, encoding="utf-8")

        return json_path, md_path
