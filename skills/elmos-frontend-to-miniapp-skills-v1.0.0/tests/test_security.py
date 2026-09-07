from __future__ import annotations

import unittest

from _support import ROOT
from check_no_secrets import scan


class SecurityTests(unittest.TestCase):
    def test_package_contains_no_detected_secret_values(self) -> None:
        result = scan(ROOT)
        self.assertTrue(result["ok"], result["findings"])

    def test_security_documents_define_credential_boundary(self) -> None:
        text = (ROOT / "docs" / "SECURITY-PRIVACY.md").read_text(encoding="utf-8").lower()
        self.assertIn("secret", text)
        self.assertIn("客户端", text)
        self.assertIn("必须审批", text)


if __name__ == "__main__":
    unittest.main()
