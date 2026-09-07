from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import elmos_software_factory.artifact_binding as artifact_binding
from elmos_software_factory.artifact_binding import (
    ArtifactBindingError,
    ContentReference,
    read_content_reference,
)
from elmos_software_factory.evidence_models import EvidenceContractError


class ArtifactPlatformHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="elmos-artifact-flags-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.payload = b"bound evidence\n"
        (self.root / "evidence.bin").write_bytes(self.payload)
        self.reference = ContentReference(
            path="evidence.bin",
            sha256="sha256:" + hashlib.sha256(self.payload).hexdigest(),
            size_bytes=len(self.payload),
            media_type="application/octet-stream",
        )

    def test_missing_no_follow_flag_fails_closed_as_evidence_contract_error(self) -> None:
        with patch.object(artifact_binding.os, "O_NOFOLLOW", None):
            with self.assertRaisesRegex(EvidenceContractError, "O_NOFOLLOW"):
                read_content_reference(self.reference, self.root)

    def test_missing_directory_flag_fails_closed_as_evidence_contract_error(self) -> None:
        with patch.object(artifact_binding.os, "O_DIRECTORY", None):
            with self.assertRaisesRegex(EvidenceContractError, "O_DIRECTORY"):
                read_content_reference(self.reference, self.root)

    def test_missing_open_dir_fd_support_fails_closed_as_evidence_contract_error(self) -> None:
        with patch.object(artifact_binding.os, "supports_dir_fd", set()):
            with self.assertRaisesRegex(EvidenceContractError, "dir_fd"):
                read_content_reference(self.reference, self.root)

    def test_binding_error_remains_specific_evidence_contract_error(self) -> None:
        self.assertTrue(issubclass(ArtifactBindingError, EvidenceContractError))

    def test_root_intermediate_and_final_symlinks_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-artifact-link-target-") as target_directory:
            target_root = Path(target_directory)
            (target_root / "evidence.bin").write_bytes(self.payload)
            root_link = self.root / "root-link"
            os.symlink(target_root, root_link)
            with self.assertRaises(ArtifactBindingError):
                read_content_reference(self.reference, root_link)

        real_parent = self.root / "real-parent"
        real_parent.mkdir()
        (real_parent / "evidence.bin").write_bytes(self.payload)
        intermediate_link = self.root / "parent-link"
        os.symlink(real_parent, intermediate_link)
        intermediate_reference = ContentReference(
            path="parent-link/evidence.bin",
            sha256=self.reference.sha256,
            size_bytes=self.reference.size_bytes,
            media_type=self.reference.media_type,
        )
        with self.assertRaises(ArtifactBindingError):
            read_content_reference(intermediate_reference, self.root)

        final_link = self.root / "evidence-link.bin"
        os.symlink(self.root / "evidence.bin", final_link)
        final_reference = ContentReference(
            path="evidence-link.bin",
            sha256=self.reference.sha256,
            size_bytes=self.reference.size_bytes,
            media_type=self.reference.media_type,
        )
        with self.assertRaises(ArtifactBindingError):
            read_content_reference(final_reference, self.root)


if __name__ == "__main__":
    unittest.main()
