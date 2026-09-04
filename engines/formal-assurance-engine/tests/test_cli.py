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

    def test_cli_accepts_encrypted_durable_artifact_store(self) -> None:
        encryption_key_path = self.root / "artifact-encryption.key"
        encryption_key_path.write_bytes(os.urandom(32))
        encryption_key_path.chmod(0o600)
        output = StringIO()
        with redirect_stdout(output):
            result = main(
                [
                    "--artifact-root",
                    str(self.root / "artifacts"),
                    "--artifact-encryption-key-file",
                    str(encryption_key_path),
                    "--artifact-encryption-key-id",
                    "test-artifact-kek-v1",
                    "skills",
                ]
            )
        self.assertEqual(result, 0)
        self.assertEqual(len(json.loads(output.getvalue())["skills"]), 60)

    def test_cli_rejects_incomplete_artifact_encryption_configuration(self) -> None:
        key_path = self.root / "artifact-encryption.key"
        key_path.write_bytes(os.urandom(32))
        key_path.chmod(0o600)
        cases = (
            ["--artifact-root", str(self.root / "artifacts"), "skills"],
            ["--artifact-encryption-key-file", str(key_path), "skills"],
            ["--artifact-encryption-key-id", "artifact-kek-v1", "skills"],
            [
                "--artifact-root",
                str(self.root / "artifacts"),
                "--artifact-encryption-key-file",
                str(key_path),
                "skills",
            ],
        )
        for arguments in cases:
            with self.subTest(arguments=arguments):
                error = StringIO()
                with redirect_stderr(error), self.assertRaises(SystemExit) as raised:
                    main(arguments)
                self.assertEqual(raised.exception.code, 2)
                self.assertIn("must be supplied together", error.getvalue())

    def test_cli_rejects_unsafe_artifact_encryption_keys(self) -> None:
        key_path = self.root / "artifact-encryption.key"
        arguments = [
            "--artifact-root",
            str(self.root / "artifacts"),
            "--artifact-encryption-key-file",
            str(key_path),
            "--artifact-encryption-key-id",
            "artifact-kek-v1",
            "skills",
        ]

        key_path.write_bytes(os.urandom(32))
        key_path.chmod(0o640)
        error = StringIO()
        with redirect_stderr(error), self.assertRaises(SystemExit) as raised:
            main(arguments)
        self.assertEqual(raised.exception.code, 2)
        self.assertIn(
            "artifact encryption key must not be accessible", error.getvalue()
        )

        key_path.chmod(0o600)
        key_path.write_bytes(os.urandom(31))
        error = StringIO()
        with redirect_stderr(error), self.assertRaises(SystemExit) as raised:
            main(arguments)
        self.assertEqual(raised.exception.code, 2)
        self.assertIn(
            "artifact encryption key must contain exactly 32 bytes",
            error.getvalue(),
        )

        key_path.write_bytes(os.urandom(32))
        link_path = self.root / "artifact-encryption-link.key"
        link_path.symlink_to(key_path)
        link_arguments = list(arguments)
        link_arguments[3] = str(link_path)
        error = StringIO()
        with redirect_stderr(error), self.assertRaises(SystemExit) as raised:
            main(link_arguments)
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("artifact encryption key path is unsafe", error.getvalue())

    def test_operator_examples_include_required_artifact_encryption_options(
        self,
    ) -> None:
        repository_root = Path(__file__).resolve().parents[3]
        operator_documents = (
            repository_root / "engines/formal-assurance-engine/README.md",
            repository_root / "docs/formal-assurance-kernel/README.md",
        )
        for document in operator_documents:
            with self.subTest(document=document):
                content = document.read_text(encoding="utf-8")
                self.assertIn("--artifact-root", content)
                self.assertIn("--artifact-encryption-key-file", content)
                self.assertIn("--artifact-encryption-key-id", content)


if __name__ == "__main__":
    unittest.main()
