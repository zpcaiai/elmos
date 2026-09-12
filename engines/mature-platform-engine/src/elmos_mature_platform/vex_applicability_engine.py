"""VEX Applicability Engine (Batch 40 - Skill 1380).

Evaluates vulnerability exploitability in context (VEX), suppressing non-actionable CVEs
with machine-readable justifications and exporting standard OpenVEX documents.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    VexAssessmentResult,
    VexJustification,
    VexStatement,
    VexStatus,
)


class VexApplicabilityEngine:
    """Manages Vulnerability Exploitability eXchange (VEX) statements and applicability assessments."""

    def __init__(self) -> None:
        self._statements: Dict[str, VexStatement] = {}

    def record_statement(self, statement: VexStatement) -> str:
        """Record a new VEX assertion for a CVE within a product context."""
        if not statement.cve_id or not statement.product_id:
            raise ValueError("cve_id and product_id are required")

        if not statement.vex_id:
            statement.vex_id = f"vex-{uuid.uuid4().hex[:8]}"

        if not statement.timestamp:
            statement.timestamp = datetime.now(timezone.utc).isoformat()
        statement.created_at = statement.timestamp

        self._statements[statement.vex_id] = statement
        return statement.vex_id

    def update_status(
        self,
        statement_id: str,
        status: VexStatus,
        justification: Optional[VexJustification] = None,
        impact: str = "",
    ) -> VexStatement:
        """Update the exploitability status and technical justification for a statement."""
        statement = self._statements.get(statement_id)
        if not statement:
            raise ValueError(f"VEX statement not found: {statement_id}")

        if status == VexStatus.NOT_AFFECTED and not justification:
            raise ValueError("Justification is required when marking a vulnerability NOT_AFFECTED")

        statement.status = status.value if hasattr(status, "value") else str(status)
        statement.justification = justification
        statement.impact_statement = impact
        statement.timestamp = datetime.now(timezone.utc).isoformat()
        return statement

    def get_statement(self, statement_id: str) -> Optional[VexStatement]:
        """Retrieve VEX statement by ID."""
        return self._statements.get(statement_id)

    def get_cve_status(self, cve_id: str, product_id: str) -> Optional[VexStatement]:
        """Look up active VEX assertion for a CVE in a given product."""
        for stmt in self._statements.values():
            if stmt.cve_id == cve_id and stmt.product_id == product_id:
                return stmt
        return None

    def is_vulnerability_actionable(self, cve_id: str, product_id: str) -> bool:
        """Determine whether a CVE requires patching (AFFECTED or UNDER_INVESTIGATION)."""
        stmt = self.get_cve_status(cve_id, product_id)
        if not stmt:
            # If no VEX statement exists, default to fail-closed actionable
            return True

        status_str = stmt.status.value if hasattr(stmt.status, "value") else str(stmt.status).lower()
        if status_str in (VexStatus.NOT_AFFECTED.value, "not_affected", VexStatus.FIXED.value, "fixed"):
            return False
        return True

    def assess_product_cves(
        self, product_id: str, cve_list: List[Dict[str, str]]
    ) -> VexAssessmentResult:
        """Filter raw CVE scanner findings using recorded VEX assertions."""
        if not product_id:
            raise ValueError("product_id is required")

        result = VexAssessmentResult(
            assessment_id=f"vex-asm-{uuid.uuid4().hex[:8]}",
            product_id=product_id,
            total_cves=len(cve_list),
        )

        for item in cve_list:
            cve_id = item.get("cve_id", "")
            stmt = self.get_cve_status(cve_id, product_id)
            if stmt:
                result.statements.append(stmt)
                if self.is_vulnerability_actionable(cve_id, product_id):
                    result.actionable_cves += 1
                else:
                    result.suppressed_cves += 1
            else:
                # Unmapped CVE is treated as actionable
                result.actionable_cves += 1

        return result

    def export_openvex_document(self, product_id: str) -> Dict[str, Any]:
        """Export standard OpenVEX document for transparency distribution."""
        product_stmts = [
            s for s in self._statements.values() if s.product_id == product_id
        ]
        doc_id = f"https://elmos.io/vex/{product_id}/{uuid.uuid4().hex[:6]}"

        statements_data = []
        for s in product_stmts:
            just_str = s.justification.value if hasattr(s.justification, "value") else str(s.justification) if s.justification else None
            statements_data.append({
                "vulnerability": {"name": s.cve_id},
                "products": [{"@id": s.product_id}],
                "status": s.status.value if hasattr(s.status, "value") else str(s.status),
                "justification": just_str,
                "impact_statement": s.impact_statement,
                "timestamp": s.timestamp,
            })

        return {
            "@context": "https://openvex.dev/ns/v0.2.0",
            "@id": doc_id,
            "author": "Elmos Mature Platform VEX Authority",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": 1,
            "statements": statements_data,
        }

    def get_vex_summary(self) -> Dict[str, Any]:
        """Aggregate metrics across all VEX records."""
        total = len(self._statements)
        not_aff = sum(
            1 for s in self._statements.values()
            if (s.status.value if hasattr(s.status, "value") else str(s.status).lower()) == "not_affected"
        )
        affected = sum(
            1 for s in self._statements.values()
            if (s.status.value if hasattr(s.status, "value") else str(s.status).lower()) == "affected"
        )
        under_inv = sum(
            1 for s in self._statements.values()
            if (s.status.value if hasattr(s.status, "value") else str(s.status).lower()) == "under_investigation"
        )

        return {
            "total_statements": total,
            "not_affected_count": not_aff,
            "affected_count": affected,
            "under_investigation_count": under_inv,
            "suppression_ratio": round(not_aff / total, 4) if total > 0 else 0.0,
        }
