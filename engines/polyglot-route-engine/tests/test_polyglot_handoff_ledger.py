"""Unit tests for PolyglotHandoffLedger in polyglot-route-engine."""

from __future__ import annotations

import unittest

from elmos_polyglot_route.enterprise_transpiler import (
    EnterpriseClass,
    EnterpriseField,
    EnterpriseMethod,
    EnterpriseModule,
)
from elmos_polyglot_route.polyglot_handoff_ledger import (
    PolyglotHandoffLedger,
    PolyglotObligationFinding,
)


class TestPolyglotHandoffLedger(unittest.TestCase):
    def test_from_enterprise_module_detects_hazards(self) -> None:
        m1 = EnterpriseMethod(
            name="calculateTotal",
            parameters=[EnterpriseField("amount", "decimal")],
            return_type="decimal",
            body_statements=["return amount * 1.1m;"],
        )
        m2 = EnterpriseMethod(
            name="loadNativeDriver",
            parameters=[EnterpriseField("path", "string")],
            return_type="void",
            body_statements=['[DllImport("kernel32.dll")]', "System.loadLibrary(path);"],
        )
        m3 = EnterpriseMethod(
            name="directMemoryWrite",
            parameters=[],
            return_type="void",
            body_statements=["unsafe { int* p = &x; *p = 10; }"],
        )
        m4 = EnterpriseMethod(
            name="dynamicPluginLoad",
            parameters=[],
            return_type="object",
            body_statements=['return Activator.CreateInstance("Plugin");'],
        )

        cls_item = EnterpriseClass(
            name="PaymentService",
            methods=[m1, m2, m3, m4],
        )
        module = EnterpriseModule(
            name="PaymentModule",
            classes=[cls_item],
            source_language="csharp",
        )

        ledger = PolyglotHandoffLedger.from_enterprise_module(module, target_language="java")

        self.assertEqual(ledger.total_obligations, 4)
        self.assertEqual(len(ledger.automated_verified), 1)
        self.assertEqual(len(ledger.handoff_items), 3)
        self.assertEqual(ledger.disposition_coverage, 1.0)
        self.assertTrue(ledger.is_100_percent_covered())

        data = ledger.to_dict()
        self.assertEqual(data["schema_version"], "1.0.0")
        self.assertEqual(data["summary"]["coverage_rate"], 1.0)
        self.assertEqual(len(data["handoff_items"]), 3)

        dossier = ledger.generate_markdown_dossier()
        self.assertIn("100% Accounted", dossier)
        self.assertIn("NATIVE_FFI_BOUNDARY", dossier)
        self.assertIn("UNSAFE_MEMORY_POINTER", dossier)
        self.assertIn("DYNAMIC_REFLECTION_INVOCATION", dossier)


if __name__ == "__main__":
    unittest.main()
