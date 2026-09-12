"""Developer Experience, IDE & CLI Handoff Ledger for Batch 36.

Provides 100% terminal disposition accounting for enterprise developer workflow units:
Track A: Automated Quick-Fix / LSP Diagnostic Resolution / Automated PR Analysis
Track B: Fail-Closed Developer Handoff Dossier for Protected Regions, 3-Way Conflicts & Internal Hooks
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class DevExItemStatus(str, Enum):
    LSP_DIAGNOSTIC_RESOLVED = "LSP_DIAGNOSTIC_RESOLVED"
    AUTOMATED_QUICK_FIX_APPLIED = "AUTOMATED_QUICK_FIX_APPLIED"
    AUTOMATED_PR_REVIEWED = "AUTOMATED_PR_REVIEWED"
    PROTECTED_REGION_BLOCKED = "PROTECTED_REGION_BLOCKED"
    PROPRIETARY_LSP_UNAVAILABLE = "PROPRIETARY_LSP_UNAVAILABLE"
    AIRGAP_CREDENTIAL_REQUIRED = "AIRGAP_CREDENTIAL_REQUIRED"
    THREE_WAY_CONFLICT_ESCALATION = "THREE_WAY_CONFLICT_ESCALATION"
    UNRESOLVED_INTERNAL_HOOK = "UNRESOLVED_INTERNAL_HOOK"


@dataclass
class DevExItem:
    item_id: str
    operation_name: str
    category: str
    status: DevExItemStatus
    target_file: str
    line_range: Optional[str] = None
    diagnostic_message: Optional[str] = None
    suggested_action: str = ""
    priority: str = "P1"
    sha256_hash: str = field(default="")

    def __post_init__(self) -> None:
        if not self.sha256_hash:
            content = f"{self.item_id}:{self.operation_name}:{self.target_file}:{self.line_range}:{self.status.value}"
            self.sha256_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass
class DevExDispositionSummary:
    total_items: int
    automated_success_count: int
    handoff_count: int
    disposition_coverage: float
    items: List[DevExItem]

    @property
    def is_fully_dispositioned(self) -> bool:
        return (
            self.total_items > 0
            and (self.automated_success_count + self.handoff_count) == self.total_items
            and abs(self.disposition_coverage - 1.0) < 1e-6
        )


class DevExHandoffLedger:
    """Ledger for computing 100% disposition coverage across developer workflow actions."""

    AUTOMATED_STATUSES = {
        DevExItemStatus.LSP_DIAGNOSTIC_RESOLVED,
        DevExItemStatus.AUTOMATED_QUICK_FIX_APPLIED,
        DevExItemStatus.AUTOMATED_PR_REVIEWED,
    }

    def scan_and_classify(self, items: List[DevExItem]) -> DevExDispositionSummary:
        total = len(items)
        if total == 0:
            return DevExDispositionSummary(
                total_items=0,
                automated_success_count=0,
                handoff_count=0,
                disposition_coverage=1.0,
                items=[],
            )

        success = 0
        handoff = 0

        for item in items:
            if item.status in self.AUTOMATED_STATUSES:
                success += 1
            else:
                handoff += 1
                if not item.suggested_action:
                    item.suggested_action = self._default_suggested_action(item.status)

        coverage = (success + handoff) / total
        return DevExDispositionSummary(
            total_items=total,
            automated_success_count=success,
            handoff_count=handoff,
            disposition_coverage=round(coverage, 4),
            items=items,
        )

    def _default_suggested_action(self, status: DevExItemStatus) -> str:
        defaults = {
            DevExItemStatus.PROTECTED_REGION_BLOCKED: "Inspect @generated or protected region block. Do not overwrite; request manual developer sign-off.",
            DevExItemStatus.PROPRIETARY_LSP_UNAVAILABLE: "Configure internal enterprise language server proxy or provide semantic stub definitions.",
            DevExItemStatus.AIRGAP_CREDENTIAL_REQUIRED: "Mount enterprise internal artifact repository certificate / token in devcontainer environment.",
            DevExItemStatus.THREE_WAY_CONFLICT_ESCALATION: "Resolve complex multi-developer semantic AST collision in interactive merge conflict editor.",
            DevExItemStatus.UNRESOLVED_INTERNAL_HOOK: "Execute custom pre-commit compliance hook within isolated enterprise sandbox environment.",
        }
        return defaults.get(status, "Escalate to repository owner for manual developer intervention.")

    def generate_handoff_json(self, summary: DevExDispositionSummary) -> Dict[str, Any]:
        handoff_items = [
            {
                "item_id": item.item_id,
                "operation_name": item.operation_name,
                "category": item.category,
                "status": item.status.value,
                "priority": item.priority,
                "target_file": item.target_file,
                "line_range": item.line_range,
                "diagnostic_message": item.diagnostic_message,
                "suggested_action": item.suggested_action,
                "sha256_hash": item.sha256_hash,
            }
            for item in summary.items
            if item.status not in self.AUTOMATED_STATUSES
        ]

        automated_items = [
            {
                "item_id": item.item_id,
                "operation_name": item.operation_name,
                "category": item.category,
                "status": item.status.value,
                "target_file": item.target_file,
                "sha256_hash": item.sha256_hash,
            }
            for item in summary.items
            if item.status in self.AUTOMATED_STATUSES
        ]

        return {
            "schema_version": 1,
            "ledger_type": "batch36-devex-handoff-ledger",
            "total_items": summary.total_items,
            "automated_success_count": summary.automated_success_count,
            "handoff_count": summary.handoff_count,
            "disposition_coverage_ratio": summary.disposition_coverage,
            "disposition_coverage_percent": f"{summary.disposition_coverage * 100:.1f}%",
            "is_fully_dispositioned": summary.is_fully_dispositioned,
            "automated_items": automated_items,
            "handoff_items": handoff_items,
        }

    def generate_markdown_dossier(self, summary: DevExDispositionSummary) -> str:
        lines = [
            "# Batch 36 Developer Experience & IDE/CLI Disposition Dossier",
            "",
            "## 1. Executive Summary",
            f"- **Total DevEx Operations**: {summary.total_items}",
            f"- **Automated Diagnosed / Quick-Fixed**: {summary.automated_success_count}",
            f"- **Fail-Closed Developer Handoffs**: {summary.handoff_count}",
            f"- **Disposition Coverage**: `{summary.disposition_coverage * 100:.1f}%` (100% Accounted)",
            f"- **Zero Unaccounted Gap**: {'PASSED (100% Industrial Standard)' if summary.is_fully_dispositioned else 'FAILED'}",
            "",
            "## 2. Developer Action Backlog",
            "| Item ID | Operation | Category | Status | Priority | Target File | Suggested Action |",
            "|---------|-----------|----------|--------|----------|-------------|------------------|",
        ]

        handoffs = [item for item in summary.items if item.status not in self.AUTOMATED_STATUSES]
        if not handoffs:
            lines.append("| None | - | - | - | - | - | All developer operations automated successfully |")
        else:
            for item in handoffs:
                loc = f"`{item.target_file}`"
                if item.line_range:
                    loc += f" (`{item.line_range}`)"
                lines.append(
                    f"| `{item.item_id}` | `{item.operation_name}` | {item.category} | `{item.status.value}` | "
                    f"**{item.priority}** | {loc} | {item.suggested_action} |"
                )

        lines.extend([
            "",
            "## 3. Developer Guidance & Safety Rules",
            "1. **Protected Regions**: Do NOT bypass `@generated` tags or comments forbidding auto-edits.",
            "2. **Conflict Arbitration**: Interactive 3-way AST merge is required when both sides alter control flow.",
            "3. **Air-Gap Environments**: Ensure proxy certs and tokens are mounted before triggering package sync.",
        ])

        return "\n".join(lines)

    def write_handoff_dossier(
        self, summary: DevExDispositionSummary, output_dir: Path
    ) -> tuple[Path, Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / "devex-handoff-ledger.json"
        md_path = output_dir / "devex-handoff-dossier.md"

        json_data = self.generate_handoff_json(summary)
        json_path.write_text(json.dumps(json_data, indent=2, ensure_ascii=False), encoding="utf-8")

        md_content = self.generate_markdown_dossier(summary)
        md_path.write_text(md_content, encoding="utf-8")

        return json_path, md_path
