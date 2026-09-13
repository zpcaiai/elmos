"""Comprehensive tests for EditionResponsibilityMatrixEngine (Batch 38 - Skill 1326)."""

import unittest

from elmos_mature_platform.edition_responsibility_matrix_engine import (
    EditionResponsibilityMatrixEngine,
)
from elmos_mature_platform.types import (
    EditionResponsibilityMatrix,
    EditionResponsibilityRecord,
    EditionType,
    ResponsibilityArea,
    ResponsibleParty,
)


class TestEditionResponsibilityMatrixComprehensive(unittest.TestCase):
    """Test suite verifying edition responsibility boundaries and matrices."""

    def setUp(self):
        self.engine = EditionResponsibilityMatrixEngine()

    def test_default_seeded_matrices(self):
        """Verify SaaS, Customer VPC, and Air-Gapped matrices are seeded by default."""
        matrices = self.engine.get_all_matrices()
        self.assertGreaterEqual(len(matrices), 3)

        saas = self.engine.get_matrix_by_edition(EditionType.MULTITENANT_SAAS)
        self.assertIsNotNone(saas)
        self.assertEqual(saas.edition, EditionType.MULTITENANT_SAAS)

        vpc = self.engine.get_matrix_by_edition(EditionType.CUSTOMER_VPC)
        self.assertIsNotNone(vpc)

        airgap = self.engine.get_matrix_by_edition(EditionType.AIR_GAPPED)
        self.assertIsNotNone(airgap)

    def test_get_party_for_area_saas_vs_airgap(self):
        """Verify party responsibility differences between SaaS and Air-Gapped editions."""
        # In SaaS, platform provider owns OS/runtime
        party_saas = self.engine.get_party_for_area(
            EditionType.MULTITENANT_SAAS,
            ResponsibilityArea.OS_CONTAINER_RUNTIME,
        )
        self.assertEqual(party_saas, ResponsibleParty.PLATFORM_PROVIDER)

        # In Air-Gapped, customer owns OS/runtime
        party_airgap = self.engine.get_party_for_area(
            EditionType.AIR_GAPPED,
            ResponsibilityArea.OS_CONTAINER_RUNTIME,
        )
        self.assertEqual(party_airgap, ResponsibleParty.CUSTOMER)

    def test_get_party_for_unregistered_area_fails_to_shared(self):
        """Verify missing matrix returns fail-closed default of SHARED."""
        party = self.engine.get_party_for_area(
            EditionType.EDGE_RESTRICTED,
            ResponsibilityArea.BACKUP_AND_RESTORE,
        )
        self.assertEqual(party, ResponsibleParty.SHARED)

    def test_create_custom_matrix(self):
        """Verify registering a custom edition matrix."""
        matrix = EditionResponsibilityMatrix(
            matrix_id="",
            edition=EditionType.DEDICATED_SAAS,
            approved_by="VP Cloud",
        )
        matrix.responsibilities[ResponsibilityArea.PLATFORM_SOFTWARE.value] = EditionResponsibilityRecord(
            area=ResponsibilityArea.PLATFORM_SOFTWARE,
            party=ResponsibleParty.PLATFORM_PROVIDER,
            sla_guaranteed=True,
            notes="Managed platform",
        )

        mid = self.engine.create_or_update_matrix(matrix)
        self.assertTrue(mid.startswith("mat-"))

        retrieved = self.engine.get_matrix_by_edition(EditionType.DEDICATED_SAAS)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.approved_by, "VP Cloud")

    def test_compare_edition_boundaries(self):
        """Verify comparison output between SaaS and Customer VPC editions."""
        diff = self.engine.compare_edition_boundaries(
            EditionType.MULTITENANT_SAAS,
            EditionType.CUSTOMER_VPC,
        )
        self.assertEqual(diff["edition_a"], EditionType.MULTITENANT_SAAS.value)
        self.assertEqual(diff["edition_b"], EditionType.CUSTOMER_VPC.value)
        self.assertGreater(diff["differing_areas_count"], 0)

        # Hardware should differ: provider in SaaS vs customer in VPC
        hardware_diff = next(
            (d for d in diff["differences"] if d["area"] == ResponsibilityArea.INFRASTRUCTURE_HARDWARE.value),
            None,
        )
        self.assertIsNotNone(hardware_diff)
        self.assertEqual(hardware_diff[EditionType.MULTITENANT_SAAS.value], ResponsibleParty.PLATFORM_PROVIDER.value)
        self.assertEqual(hardware_diff[EditionType.CUSTOMER_VPC.value], ResponsibleParty.CUSTOMER.value)


if __name__ == "__main__":
    unittest.main()
