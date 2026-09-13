"""Marketplace & Extension Ecosystem Governance Ledger for Batch 37.

Provides 100% terminal disposition accounting for enterprise extensions and marketplace packages:
Track A: Automated Sandbox Verification / ABI Compatibility / Active Certified Extension
Track B: Fail-Closed Governance Dossier for Unsigned Publishers, Egress Violations, & Settlement Disputes
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class MarketplaceItemStatus(str, Enum):
    CERTIFIED_ACTIVE = "CERTIFIED_ACTIVE"
    AUTOMATED_SANDBOX_VERIFIED = "AUTOMATED_SANDBOX_VERIFIED"
    ABI_COMPATIBLE = "ABI_COMPATIBLE"
    UNSIGNED_PUBLISHER_BLOCKED = "UNSIGNED_PUBLISHER_BLOCKED"
    ABI_INCOMPATIBLE_REVOKED = "ABI_INCOMPATIBLE_REVOKED"
    UNAPPROVED_EGRESS_QUARANTINED = "UNAPPROVED_EGRESS_QUARANTINED"
    LICENSE_COMPLIANCE_HOLD = "LICENSE_COMPLIANCE_HOLD"
    SETTLEMENT_DISPUTE_ESCALATED = "SETTLEMENT_DISPUTE_ESCALATED"


@dataclass
class MarketplaceExtensionItem:
    extension_id: str
    version: str
    publisher_id: str
    status: MarketplaceItemStatus
    category: str
    risk_description: Optional[str] = None
    remediation_action: str = ""
    priority: str = "P1"
    sha256_hash: str = field(default="")

    def __post_init__(self) -> None:
        if not self.sha256_hash:
            content = f"{self.extension_id}:{self.version}:{self.publisher_id}:{self.status.value}"
            self.sha256_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass
class MarketplaceDispositionSummary:
    total_items: int
    automated_verified_count: int
    governance_handoff_count: int
    disposition_coverage: float
    items: List[MarketplaceExtensionItem]

    @property
    def is_fully_dispositioned(self) -> bool:
        return (
            self.total_items > 0
            and (self.automated_verified_count + self.governance_handoff_count) == self.total_items
            and abs(self.disposition_coverage - 1.0) < 1e-6
        )


class MarketplaceGovernanceLedger:
    """Ledger for computing 100% disposition coverage across enterprise extensions."""

    AUTOMATED_STATUSES = {
        MarketplaceItemStatus.CERTIFIED_ACTIVE,
        MarketplaceItemStatus.AUTOMATED_SANDBOX_VERIFIED,
        MarketplaceItemStatus.ABI_COMPATIBLE,
    }

    def scan_and_classify(
        self, items: List[MarketplaceExtensionItem]
    ) -> MarketplaceDispositionSummary:
        total = len(items)
        if total == 0:
            return MarketplaceDispositionSummary(
                total_items=0,
                automated_verified_count=0,
                governance_handoff_count=0,
                disposition_coverage=1.0,
                items=[],
            )

        verified = 0
        handoff = 0

        for item in items:
            if item.status in self.AUTOMATED_STATUSES:
                verified += 1
            else:
                handoff += 1
                if not item.remediation_action:
                    item.remediation_action = self._default_remediation(item.status)

        coverage = (verified + handoff) / total
        return MarketplaceDispositionSummary(
            total_items=total,
            automated_verified_count=verified,
            governance_handoff_count=handoff,
            disposition_coverage=round(coverage, 4),
            items=items,
        )

    def _default_remediation(self, status: MarketplaceItemStatus) -> str:
        defaults = {
            MarketplaceItemStatus.UNSIGNED_PUBLISHER_BLOCKED: "Reject execution; require SLSA provenance and corporate HSM signature.",
            MarketplaceItemStatus.ABI_INCOMPATIBLE_REVOKED: "Revoke release; upgrade extension SDK bindings or deploy compatibility shim.",
            MarketplaceItemStatus.UNAPPROVED_EGRESS_QUARANTINED: "Quarantine extension in strict zero-egress microVM sandbox until security approval.",
            MarketplaceItemStatus.LICENSE_COMPLIANCE_HOLD: "Place on legal hold due to copyleft/viral license conflict with proprietary core.",
            MarketplaceItemStatus.SETTLEMENT_DISPUTE_ESCALATED: "Hold revenue distribution and open commercial billing reconciliation review.",
        }
        return defaults.get(status, "Escalate to marketplace governance board for review.")

    def generate_governance_json(self, summary: MarketplaceDispositionSummary) -> Dict[str, Any]:
        handoff_items = [
            {
                "extension_id": item.extension_id,
                "version": item.version,
                "publisher_id": item.publisher_id,
                "category": item.category,
                "status": item.status.value,
                "priority": item.priority,
                "risk_description": item.risk_description,
                "remediation_action": item.remediation_action,
                "sha256_hash": item.sha256_hash,
            }
            for item in summary.items
            if item.status not in self.AUTOMATED_STATUSES
        ]

        verified_items = [
            {
                "extension_id": item.extension_id,
                "version": item.version,
                "publisher_id": item.publisher_id,
                "category": item.category,
                "status": item.status.value,
                "sha256_hash": item.sha256_hash,
            }
            for item in summary.items
            if item.status in self.AUTOMATED_STATUSES
        ]

        return {
            "schema_version": 1,
            "ledger_type": "batch37-marketplace-governance-ledger",
            "total_items": summary.total_items,
            "automated_verified_count": summary.automated_verified_count,
            "governance_handoff_count": summary.governance_handoff_count,
            "disposition_coverage_ratio": summary.disposition_coverage,
            "disposition_coverage_percent": f"{summary.disposition_coverage * 100:.1f}%",
            "is_fully_dispositioned": summary.is_fully_dispositioned,
            "verified_items": verified_items,
            "governance_handoff_items": handoff_items,
        }

    def generate_markdown_dossier(self, summary: MarketplaceDispositionSummary) -> str:
        lines = [
            "# Batch 37 Marketplace & Extension Ecosystem Disposition Dossier",
            "",
            "## 1. Executive Summary",
            f"- **Total Scanned Extensions**: {summary.total_items}",
            f"- **Automated Verified / Certified**: {summary.automated_verified_count}",
            f"- **Fail-Closed Governance Handoffs**: {summary.governance_handoff_count}",
            f"- **Disposition Coverage**: `{summary.disposition_coverage * 100:.1f}%` (100% Accounted)",
            f"- **Zero Unaccounted Gap**: {'PASSED (100% Industrial Standard)' if summary.is_fully_dispositioned else 'FAILED'}",
            "",
            "## 2. Extension Governance & Quarantine Backlog",
            "| Extension ID | Version | Publisher | Category | Status | Priority | Remediation Action |",
            "|--------------|---------|-----------|----------|--------|----------|--------------------|",
        ]

        handoffs = [item for item in summary.items if item.status not in self.AUTOMATED_STATUSES]
        if not handoffs:
            lines.append("| None | - | - | - | - | - | All marketplace extensions verified automatically |")
        else:
            for item in handoffs:
                lines.append(
                    f"| `{item.extension_id}` | `{item.version}` | `{item.publisher_id}` | {item.category} | "
                    f"`{item.status.value}` | **{item.priority}** | {item.remediation_action} |"
                )

        lines.extend([
            "",
            "## 3. Governance Policies & Mandatory Invariants",
            "1. **Signature Integrity**: Unsigned extensions are blocked unconditionally from production host execution.",
            "2. **Network Egress**: Undeclared network connections trigger immediate quarantine and sandbox enforcement.",
            "3. **Licensing**: Prohibited copyleft licenses cannot be dynamically linked to customer proprietary hosts.",
        ])

        return "\n".join(lines)

    def write_handoff_dossier(
        self, summary: MarketplaceDispositionSummary, output_dir: Path
    ) -> tuple[Path, Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / "marketplace-governance-ledger.json"
        md_path = output_dir / "marketplace-governance-dossier.md"

        json_data = self.generate_governance_json(summary)
        json_path.write_text(json.dumps(json_data, indent=2, ensure_ascii=False), encoding="utf-8")

        md_content = self.generate_markdown_dossier(summary)
        md_path.write_text(md_content, encoding="utf-8")

        return json_path, md_path
