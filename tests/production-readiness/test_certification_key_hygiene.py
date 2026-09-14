from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/certification/check_repository_key_hygiene.py"
SPEC = importlib.util.spec_from_file_location("key_hygiene", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CertificationKeyHygieneTest(unittest.TestCase):
    def test_rejects_private_key_filename(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "certifier-private.pem"
            path.write_text("not-even-a-valid-key\n", encoding="utf-8")
            violations = MODULE.find_violations(root, [path.name])
            self.assertEqual(violations[0]["reason"], "forbidden-private-key-filename")

    def test_rejects_private_key_block_in_arbitrary_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "evidence.txt"
            begin = "-----BEGIN " + "PRIVATE KEY-----\n"
            path.write_text(begin + "A" * 64 + "\n" + "B" * 64 + "\n", encoding="utf-8")
            violations = MODULE.find_violations(root, [path.name])
            self.assertEqual(violations[0]["reason"], "private-key-pem-block")

    def test_allows_public_key_and_prose(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            public = root / "certifier-public.pem"
            public.write_text("-----BEGIN PUBLIC KEY-----\nfixture\n", encoding="utf-8")
            prose = root / "policy.md"
            prose.write_text("Private keys are forbidden.\n", encoding="utf-8")
            self.assertEqual(MODULE.find_violations(root, [public.name, prose.name]), [])


if __name__ == "__main__":
    unittest.main()
