"""Security, negative testing, and fail-closed isolation tests."""

from __future__ import annotations

import unittest
from elmos_ai_capability.kernel import (
    MemoryRecord,
    authorize_memory,
    isolation_probe,
    IncidentController,
    PackageTrustInput,
    trust_decision,
    ActionPreview,
    ux_gate,
)
from elmos_ai_capability.runtime import AICapabilityRuntime


class SecurityIsolationTests(unittest.TestCase):
    def test_cross_tenant_memory_probe(self) -> None:
        records = [
            MemoryRecord("m1", "tenant-victim", "secret-key-123"),
            MemoryRecord("m2", "tenant-victim", "financial-data"),
        ]
        auth = authorize_memory(records, "tenant-attacker")
        self.assertEqual(len(auth), 0)
        self.assertTrue(isolation_probe(auth, "tenant-attacker"))

    def test_incident_kill_switch_blocks_execution(self) -> None:
        ctrl = IncidentController()
        self.assertTrue(ctrl.can_execute())
        ctrl.trigger_kill_switch("INC-999")
        self.assertFalse(ctrl.can_execute())

    def test_malicious_package_quarantine(self) -> None:
        pkg = PackageTrustInput(
            package_name="untrusted-plugin",
            version="1.0.0",
            provenance_signed=False,
            sbom_present=False,
            vulnerabilities=("CVE-2026-9999",),
        )
        dec = trust_decision(pkg)
        self.assertEqual(dec, "QUARANTINE")

    def test_destructive_action_requires_explicit_confirmation(self) -> None:
        action = ActionPreview(action_type="DELETE_DATABASE", impact_level="CRITICAL", reversible=False)
        self.assertFalse(ux_gate(action, user_confirmed=False))
        self.assertTrue(ux_gate(action, user_confirmed=True))


if __name__ == "__main__":
    unittest.main()
