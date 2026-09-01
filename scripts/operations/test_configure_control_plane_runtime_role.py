from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONFIGURATOR = ROOT / "scripts/operations/configure_control_plane_runtime_role.sh"
STORE = ROOT / "modules/persistence/src/main/java/io/elmos/persistence/JdbcPlatformAdminStore.java"


class ControlPlanePlatformAdminGrantContractTest(unittest.TestCase):
    def test_actual_login_receives_every_store_function_but_no_identity_table(self) -> None:
        script = CONFIGURATOR.read_text(encoding="utf-8")
        store = STORE.read_text(encoding="utf-8")
        expected_names = set(re.findall(r"elmos_platform_[a-z_]+", store))
        self.assertEqual(
            {
                "elmos_platform_authorize",
                "elmos_platform_grant_admin",
                "elmos_platform_job_overview",
                "elmos_platform_resolve_admin_account",
                "elmos_platform_revoke_admin",
                "elmos_platform_topup_orders",
                "elmos_platform_wallet_adjust",
                "elmos_platform_wallet_ledger",
                "elmos_platform_wallet_overview",
            },
            expected_names,
        )
        start = script.index("-- JdbcPlatformAdminStore uses only these nine")
        end = script.index("-- V72 keeps snapshot materialization leases", start)
        grant_block = script[start:end]
        granted_names = set(
            re.findall(r"public\.(elmos_platform_[a-z_]+)\(", grant_block)
        )

        self.assertEqual(expected_names, granted_names)
        self.assertEqual(9, grant_block.count("'public.elmos_platform_"))
        self.assertIn("to_regprocedure(function_signature) IS NULL", grant_block)
        self.assertNotIn("elmos_platform_bootstrap_admin", grant_block)
        self.assertNotIn("accounts,", grant_block)
        self.assertNotIn("platform_administrators", grant_block)


if __name__ == "__main__":
    unittest.main()
