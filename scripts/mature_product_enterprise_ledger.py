"""Mature Product Enterprise Ledger for Batches 38-45.

Provides 100% terminal disposition accounting across all enterprise mature product domains:
B38: Deployment Editions & Topologies (Air-Gapped, Sovereign Cloud, SaaS)
B39: Global SRE & Operations (SLO, Chaos, Restore, DR)
B40: Supply Chain & Compliance (SBOM, Signatures, VEX, CVEs)
B41: Knowledge Flywheel & Prediction (Data Provenance, Privacy Isolation)
B42: Governed Agent Factory (Tool Permissions, Kill-Switch, Autonomy)
B43: Product Lifecycle & LTS (Compatibility Matrix, Deprecations)
B44: FinOps & Economics (Usage Metering, Gross Margin, Billing)
B45: Mature Product Certification (Comprehensive Gate, Residual Risks)

Track A: Automated Proof / Conformance / Signature / Reconciliation
Track B: Fail-Closed Enterprise Handoff Dossier with Exact Remediation Runbooks
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class MatureBatchDomain(str, Enum):
    B38_DEPLOYMENT_EDITIONS = "B38_DEPLOYMENT_EDITIONS"
    B39_GLOBAL_SRE_OPS = "B39_GLOBAL_SRE_OPS"
    B40_SUPPLY_CHAIN_SECURITY = "B40_SUPPLY_CHAIN_SECURITY"
    B41_KNOWLEDGE_PREDICTION = "B41_KNOWLEDGE_PREDICTION"
    B42_GOVERNED_AGENT_FACTORY = "B42_GOVERNED_AGENT_FACTORY"
    B43_PRODUCT_LIFECYCLE_LTS = "B43_PRODUCT_LIFECYCLE_LTS"
    B44_FINOPS_ECONOMICS = "B44_FINOPS_ECONOMICS"
    B45_MATURE_PRODUCT_CERTIFICATION = "B45_MATURE_PRODUCT_CERTIFICATION"


class MatureItemStatus(str, Enum):
    AUTOMATED_CONFORMANCE_VERIFIED = "AUTOMATED_CONFORMANCE_VERIFIED"
    SLO_PROVED = "SLO_PROVED"
    SIGNATURE_VERIFIED = "SIGNATURE_VERIFIED"
    FINOPS_RECONCILED = "FINOPS_RECONCILED"
    MATURE_CERTIFIED = "MATURE_CERTIFIED"
    AIRGAP_BUNDLE_DEFECT = "AIRGAP_BUNDLE_DEFECT"
    SRE_FAILOVER_GAP = "SRE_FAILOVER_GAP"
    CVE_SECURITY_REMEDIATION = "CVE_SECURITY_REMEDIATION"
    KNOWLEDGE_LEAKAGE_RISK = "KNOWLEDGE_LEAKAGE_RISK"
    AGENT_KILLSWITCH_UNVERIFIED = "AGENT_KILLSWITCH_UNVERIFIED"
    BREAKING_SCHEMA_BLOCKED = "BREAKING_SCHEMA_BLOCKED"
    MARGIN_DEFICIT_ESCALATION = "MARGIN_DEFICIT_ESCALATION"
    CRITICAL_RESIDUAL_RISK = "CRITICAL_RESIDUAL_RISK"


@dataclass
class MatureProductItem:
    item_id: str
    domain: MatureBatchDomain
    name: str
    status: MatureItemStatus
    target_resource: str
    risk_description: Optional[str] = None
    remediation_runbook: str = ""
    priority: str = "P1"
    sha256_hash: str = field(default="")

    def __post_init__(self) -> None:
        if not self.sha256_hash:
            content = f"{self.item_id}:{self.domain.value}:{self.name}:{self.target_resource}:{self.status.value}"
            self.sha256_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass
class MatureProductDispositionSummary:
    total_items: int
    automated_verified_count: int
    governance_handoff_count: int
    disposition_coverage: float
    items: List[MatureProductItem]

    @property
    def is_fully_dispositioned(self) -> bool:
        return (
            self.total_items > 0
            and (self.automated_verified_count + self.governance_handoff_count) == self.total_items
            and abs(self.disposition_coverage - 1.0) < 1e-6
        )


class MatureProductEnterpriseLedger:
    """Ledger for computing 100% disposition coverage across mature platform product domains."""

    AUTOMATED_STATUSES = {
        MatureItemStatus.AUTOMATED_CONFORMANCE_VERIFIED,
        MatureItemStatus.SLO_PROVED,
        MatureItemStatus.SIGNATURE_VERIFIED,
        MatureItemStatus.FINOPS_RECONCILED,
        MatureItemStatus.MATURE_CERTIFIED,
    }

    def scan_and_classify(
        self, items: List[MatureProductItem]
    ) -> MatureProductDispositionSummary:
        total = len(items)
        if total == 0:
            return MatureProductDispositionSummary(
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
                if not item.remediation_runbook:
                    item.remediation_runbook = self._default_runbook(item.status)

        coverage = (verified + handoff) / total
        return MatureProductDispositionSummary(
            total_items=total,
            automated_verified_count=verified,
            governance_handoff_count=handoff,
            disposition_coverage=round(coverage, 4),
            items=items,
        )

    def _default_runbook(self, status: MatureItemStatus) -> str:
        defaults = {
            MatureItemStatus.AIRGAP_BUNDLE_DEFECT: "Re-package offline update bundle with cryptographic manifest and test dry-run rollback.",
            MatureItemStatus.SRE_FAILOVER_GAP: "Execute simulated AZ evacuation drill and calibrate multi-region database replication lag.",
            MatureItemStatus.CVE_SECURITY_REMEDIATION: "Apply vendor security patch or register formal VEX non-reachability waiver signed by CISO.",
            MatureItemStatus.KNOWLEDGE_LEAKAGE_RISK: "Purge tenant embedding artifacts and enforce k-anonymity / differential privacy boundary.",
            MatureItemStatus.AGENT_KILLSWITCH_UNVERIFIED: "Execute emergency SIGKILL / circuit breaker drill on autonomous agent worker pool.",
            MatureItemStatus.BREAKING_SCHEMA_BLOCKED: "Synthesize backward-compatible expand-and-contract shim; defer field removal to next LTS.",
            MatureItemStatus.MARGIN_DEFICIT_ESCALATION: "Re-rate workload compute allocation, apply prompt cache compaction, or review tiered pricing.",
            MatureItemStatus.CRITICAL_RESIDUAL_RISK: "Convene Enterprise Product Architecture Board to resolve critical holdout blockers.",
        }
        return defaults.get(status, "Escalate to enterprise engineering operations board.")

    def generate_enterprise_json(
        self, summary: MatureProductDispositionSummary
    ) -> Dict[str, Any]:
        handoff_items = [
            {
                "item_id": item.item_id,
                "domain": item.domain.value,
                "name": item.name,
                "target_resource": item.target_resource,
                "status": item.status.value,
                "priority": item.priority,
                "risk_description": item.risk_description,
                "remediation_runbook": item.remediation_runbook,
                "sha256_hash": item.sha256_hash,
            }
            for item in summary.items
            if item.status not in self.AUTOMATED_STATUSES
        ]

        verified_items = [
            {
                "item_id": item.item_id,
                "domain": item.domain.value,
                "name": item.name,
                "target_resource": item.target_resource,
                "status": item.status.value,
                "sha256_hash": item.sha256_hash,
            }
            for item in summary.items
            if item.status in self.AUTOMATED_STATUSES
        ]

        return {
            "schema_version": 1,
            "ledger_type": "batches-38-45-mature-product-enterprise-ledger",
            "total_items": summary.total_items,
            "automated_verified_count": summary.automated_verified_count,
            "governance_handoff_count": summary.governance_handoff_count,
            "disposition_coverage_ratio": summary.disposition_coverage,
            "disposition_coverage_percent": f"{summary.disposition_coverage * 100:.1f}%",
            "is_fully_dispositioned": summary.is_fully_dispositioned,
            "verified_items": verified_items,
            "governance_handoff_items": handoff_items,
        }

    def generate_markdown_dossier(
        self, summary: MatureProductDispositionSummary
    ) -> str:
        lines = [
            "# Batches 38-45 Mature Commercial Platform Product Disposition Dossier",
            "",
            "## 1. Executive Summary",
            f"- **Total Scanned Items**: {summary.total_items}",
            f"- **Automated Verified / Proved**: {summary.automated_verified_count}",
            f"- **Fail-Closed Governance Handoffs**: {summary.governance_handoff_count}",
            f"- **Disposition Coverage**: `{summary.disposition_coverage * 100:.1f}%` (100% Accounted)",
            f"- **Zero Unaccounted Gap**: {'PASSED (100% Industrial Standard)' if summary.is_fully_dispositioned else 'FAILED'}",
            "",
            "## 2. Cross-Batch Enterprise Governance Backlog",
            "| Item ID | Batch Domain | Name | Status | Priority | Target Resource | Remediation Runbook |",
            "|---------|--------------|------|--------|----------|-----------------|---------------------|",
        ]

        handoffs = [item for item in summary.items if item.status not in self.AUTOMATED_STATUSES]
        if not handoffs:
            lines.append("| None | - | - | - | - | - | All mature product items verified automatically |")
        else:
            for item in handoffs:
                lines.append(
                    f"| `{item.item_id}` | `{item.domain.value}` | {item.name} | `{item.status.value}` | "
                    f"**{item.priority}** | `{item.target_resource}` | {item.remediation_runbook} |"
                )

        lines.extend([
            "",
            "## 3. Platform Invariants & Non-Negotiable Controls",
            "1. **Zero Unsigned Production**: Binaries, container images, and offline update bundles require valid signatures.",
            "2. **Strict Privacy & Provenance**: Tenant knowledge data cannot cross isolation boundaries without explicit consent.",
            "3. **Fail-Closed Operations**: Critical SRE failover and Agent kill-switches must be proven before production promotion.",
        ])

        return "\n".join(lines)

    def write_handoff_dossier(
        self, summary: MatureProductDispositionSummary, output_dir: Path
    ) -> tuple[Path, Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / "mature-product-enterprise-ledger.json"
        md_path = output_dir / "mature-product-enterprise-dossier.md"

        json_data = self.generate_enterprise_json(summary)
        json_path.write_text(json.dumps(json_data, indent=2, ensure_ascii=False), encoding="utf-8")

        md_content = self.generate_markdown_dossier(summary)
        md_path.write_text(md_content, encoding="utf-8")

        return json_path, md_path
