from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest

from elmos_formal_assurance.cli import main


class FormalAssuranceCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_cli_loads_digest_pinned_registry_and_private_permit_key(self) -> None:
        key_path = self.root / "permit.key"
        key_path.write_bytes(b"k" * 32)
        key_path.chmod(0o600)
        registry_path = self.root / "toolchains.json"
        registry_bytes = json.dumps(
            {
                "format": "elmos-formal-toolchain-registry/v1",
                "toolchains": [],
            },
            separators=(",", ":"),
        ).encode("utf-8")
        registry_path.write_bytes(registry_bytes)
        registry_digest = "sha256:" + hashlib.sha256(registry_bytes).hexdigest()
        output = StringIO()
        with redirect_stdout(output):
            result = main(
                [
                    "--permit-key-file",
                    str(key_path),
                    "--toolchain-registry",
                    str(registry_path),
                    "--toolchain-registry-sha256",
                    registry_digest,
                    "skills",
                ]
            )
        self.assertEqual(result, 0)
        self.assertEqual(len(json.loads(output.getvalue())["skills"]), 60)
        self.assertNotIn((b"k" * 32).decode("ascii"), output.getvalue())

    def test_cli_rejects_permit_key_readable_by_group_or_others(self) -> None:
        key_path = self.root / "permit.key"
        key_path.write_bytes(b"k" * 32)
        key_path.chmod(0o644)
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as raised:
            main(["--permit-key-file", str(key_path), "skills"])
        self.assertEqual(raised.exception.code, 2)

    def test_cli_rejects_symlinked_key_and_unpaired_registry_options(self) -> None:
        key_path = self.root / "permit.key"
        key_path.write_bytes(os.urandom(32))
        key_path.chmod(0o600)
        link_path = self.root / "permit-link.key"
        link_path.symlink_to(key_path)
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            main(["--permit-key-file", str(link_path), "skills"])
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            main(["--toolchain-registry", str(self.root / "missing.json"), "skills"])


if __name__ == "__main__":
    unittest.main()
