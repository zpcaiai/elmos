from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tooling" / "validate_windows_checkout_paths.py"
SPEC = importlib.util.spec_from_file_location(
    "validate_windows_checkout_paths", MODULE_PATH
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Windows checkout path validator could not be loaded")
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)


class WindowsCheckoutPathValidatorTest(unittest.TestCase):
    def test_accepts_unique_portable_names(self) -> None:
        paths = [
            "README.md",
            "verification-packs/"
            + "/".join(["long-evidence-segment"] * 14)
            + "/evidence.json",
            "src/cafe\N{COMBINING ACUTE ACCENT}.txt",
        ]

        self.assertEqual([], validator.audit_path_names(paths))
        self.assertGreaterEqual(validator.utf16_units(paths[1]), 260)

    def test_rejects_windows_reserved_invalid_and_colliding_names(self) -> None:
        findings = "\n".join(
            validator.audit_path_names(
                [
                    "src/CON.txt",
                    "src/trailing-period.",
                    "src/invalid?.txt",
                    "src/CaseSensitive.txt",
                    "src/casesensitive.txt",
                ]
            )
        )

        self.assertIn("reserved Windows component", findings)
        self.assertIn("ends in a space or period", findings)
        self.assertIn("invalid Windows character", findings)
        self.assertIn("collision", findings)

    def test_inventory_digest_is_order_independent_and_nul_delimited(self) -> None:
        expected = validator.inventory_digest(["a", "bc"])

        self.assertEqual(expected, validator.inventory_digest(["bc", "a"]))
        self.assertNotEqual(expected, validator.inventory_digest(["ab", "c"]))

    def test_claim_boundary_is_explicit(self) -> None:
        self.assertEqual("CHECKOUT_AND_TRACKED_PATH_ACCESS_ONLY", validator.SCOPE)
        self.assertEqual("NOT_RUN", validator.WINDOWS_RUNTIME_STATUS)
        self.assertEqual("NOT_CERTIFIED", validator.CERTIFICATION_STATUS)


if __name__ == "__main__":
    unittest.main()
