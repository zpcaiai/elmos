"""Edition Responsibility Matrix Engine (Batch 38 - Skill 1326).

Enforces clear division of operational, security, infrastructure, and compliance
responsibilities across all deployment editions (SaaS, Dedicated, Customer VPC,
Self-Hosted, Sovereign, Air-Gapped, and Edge).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from elmos_mature_platform.types import (
    EditionResponsibilityMatrix,
    EditionResponsibilityRecord,
    EditionType,
    ResponsibilityArea,
    ResponsibleParty,
)


class EditionResponsibilityMatrixEngine:
    """Industrial engine for edition responsibility and operational boundaries (B38)."""

    def __init__(self):
        self._matrices: Dict[str, EditionResponsibilityMatrix] = {}
        self._seed_default_matrices()

    def _seed_default_matrices(self) -> None:
        """Seed default responsibility boundaries for canonical enterprise editions."""
        # 1. MULTITENANT_SAAS: Platform provider manages infra, OS, platform, security patching, backup, DR
        saas_matrix = EditionResponsibilityMatrix(
            matrix_id="matrix-saas",
            edition=EditionType.MULTITENANT_SAAS,
            last_reviewed=datetime.now(timezone.utc).isoformat(),
            approved_by="VP SRE",
        )
        for area in ResponsibilityArea:
            if area == ResponsibilityArea.DATA_PRIVACY_RESIDENCY:
                party = ResponsibleParty.SHARED
            else:
                party = ResponsibleParty.PLATFORM_PROVIDER
            saas_matrix.responsibilities[area.value] = EditionResponsibilityRecord(
                area=area,
                party=party,
                sla_guaranteed=True,
                notes=f"SaaS standard responsibility: {party.value}",
            )
        self._matrices[saas_matrix.matrix_id] = saas_matrix

        # 2. CUSTOMER_VPC: Infra/OS customer or shared, platform software provider
        vpc_matrix = EditionResponsibilityMatrix(
            matrix_id="matrix-customer-vpc",
            edition=EditionType.CUSTOMER_VPC,
            last_reviewed=datetime.now(timezone.utc).isoformat(),
            approved_by="VP SRE",
        )
        for area in ResponsibilityArea:
            if area in (ResponsibilityArea.INFRASTRUCTURE_HARDWARE, ResponsibilityArea.OS_CONTAINER_RUNTIME):
                party = ResponsibleParty.CUSTOMER
            elif area in (ResponsibilityArea.BACKUP_AND_RESTORE, ResponsibilityArea.DISASTER_RECOVERY):
                party = ResponsibleParty.SHARED
            else:
                party = ResponsibleParty.PLATFORM_PROVIDER
            vpc_matrix.responsibilities[area.value] = EditionResponsibilityRecord(
                area=area,
                party=party,
                sla_guaranteed=party != ResponsibleParty.CUSTOMER,
                notes=f"VPC responsibility: {party.value}",
            )
        self._matrices[vpc_matrix.matrix_id] = vpc_matrix

        # 3. AIR_GAPPED: Customer owns infra, OS, backup, DR, and upgrade execution
        airgap_matrix = EditionResponsibilityMatrix(
            matrix_id="matrix-air-gapped",
            edition=EditionType.AIR_GAPPED,
            last_reviewed=datetime.now(timezone.utc).isoformat(),
            approved_by="Chief Security Officer",
        )
        for area in ResponsibilityArea:
            if area == ResponsibilityArea.PLATFORM_SOFTWARE:
                party = ResponsibleParty.PLATFORM_PROVIDER
            else:
                party = ResponsibleParty.CUSTOMER
            airgap_matrix.responsibilities[area.value] = EditionResponsibilityRecord(
                area=area,
                party=party,
                sla_guaranteed=False,
                notes="Air-gapped enclave: customer fully manages local environment",
            )
        self._matrices[airgap_matrix.matrix_id] = airgap_matrix

    def create_or_update_matrix(self, matrix: EditionResponsibilityMatrix) -> str:
        """Create or update a custom responsibility matrix for an edition."""
        if not matrix.matrix_id:
            matrix.matrix_id = f"mat-{uuid.uuid4().hex[:8]}"
        if not matrix.last_reviewed:
            matrix.last_reviewed = datetime.now(timezone.utc).isoformat()

        self._matrices[matrix.matrix_id] = matrix
        return matrix.matrix_id

    def get_matrix_by_edition(self, edition: EditionType) -> Optional[EditionResponsibilityMatrix]:
        """Retrieve the responsibility matrix for a specific edition."""
        for m in self._matrices.values():
            if m.edition == edition:
                return m
        return None

    def get_party_for_area(
        self,
        edition: EditionType,
        area: ResponsibilityArea,
    ) -> ResponsibleParty:
        """Query which party is responsible for an operational area in a given edition."""
        matrix = self.get_matrix_by_edition(edition)
        if not matrix or area.value not in matrix.responsibilities:
            # Safe fail-closed default: SHARED
            return ResponsibleParty.SHARED
        return matrix.responsibilities[area.value].party

    def compare_edition_boundaries(
        self,
        edition_a: EditionType,
        edition_b: EditionType,
    ) -> Dict[str, Any]:
        """Compare responsibility allocations between two editions."""
        mat_a = self.get_matrix_by_edition(edition_a)
        mat_b = self.get_matrix_by_edition(edition_b)

        differences = []
        for area in ResponsibilityArea:
            party_a = mat_a.responsibilities[area.value].party if (mat_a and area.value in mat_a.responsibilities) else "unknown"
            party_b = mat_b.responsibilities[area.value].party if (mat_b and area.value in mat_b.responsibilities) else "unknown"
            if party_a != party_b:
                differences.append({
                    "area": area.value,
                    edition_a.value: party_a.value if hasattr(party_a, "value") else party_a,
                    edition_b.value: party_b.value if hasattr(party_b, "value") else party_b,
                })

        return {
            "edition_a": edition_a.value,
            "edition_b": edition_b.value,
            "differing_areas_count": len(differences),
            "differences": differences,
        }

    def get_all_matrices(self) -> List[EditionResponsibilityMatrix]:
        """Return all registered edition responsibility matrices."""
        return list(self._matrices.values())
