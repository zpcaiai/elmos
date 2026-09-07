from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
import struct
import sys
import tempfile
import unittest
import warnings
import zipfile


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tooling import integrate_proof_driven_harness_intelligence_v1 as importer  # noqa: E402


PINNED_ARCHIVE = (
    REPO_ROOT
    / "skills/subskills/sub/elmos-proof-driven-harness-intelligence-v1.0.0.zip"
)


def _member(
    name: str,
    content: bytes,
    *,
    method: int = zipfile.ZIP_DEFLATED,
    mode: int = stat.S_IFREG | 0o644,
) -> tuple[zipfile.ZipInfo, bytes]:
    info = zipfile.ZipInfo(name, date_time=(2026, 8, 30, 0, 0, 0))
    info.create_system = 3
    info.compress_type = method
    info.external_attr = mode << 16
    return info, content


def _write_zip(
    path: Path,
    entries: list[tuple[zipfile.ZipInfo, bytes]],
) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(path, mode="w") as archive:
            for info, content in entries:
                archive.writestr(info, content)


def _policy(
    path: Path,
    allowed: dict[str, bytes],
    **overrides: object,
) -> importer.ArchivePolicy:
    values: dict[str, object] = {
        "root": "pkg",
        "expected_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "allowed_members": {
            name: hashlib.sha256(content).hexdigest()
            for name, content in allowed.items()
        },
        "max_archive_bytes": 1024 * 1024,
        "max_member_bytes": 128 * 1024,
        "max_total_bytes": 256 * 1024,
        "max_compression_ratio": 100.0,
        "allowed_methods": frozenset({zipfile.ZIP_DEFLATED}),
        "validate_source_semantics": False,
    }
    values.update(overrides)
    return importer.ArchivePolicy(**values)  # type: ignore[arg-type]


class PinnedImporterTests(unittest.TestCase):
    def test_pinned_archive_validates_exact_contracts_and_counts(self) -> None:
        validated = importer.validate_pinned_archive(PINNED_ARCHIVE)
        self.assertEqual(validated.archive_sha256, importer.ARCHIVE_SHA256)
        self.assertEqual(validated.archive_bytes, 28_988)
        self.assertEqual(len(validated.members), 25)
        self.assertEqual(len(validated.member_metadata), 25)
        self.assertEqual(set(validated.contract_fields), set(importer.SOURCE_CONTRACT_FIELDS))

    def test_materialization_is_bounded_atomic_idempotent_and_drift_safe(self) -> None:
        validated = importer.validate_pinned_archive(PINNED_ARCHIVE)
        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory)
            first = importer.materialize(validated, output_root=output_root)
            self.assertEqual(first["materialization"], "INSTALLED")
            self.assertEqual(first["distribution_output_count"], 81)
            destination = output_root / importer.INTEGRATION_RELATIVE
            self.assertEqual(
                len([path for path in destination.rglob("*") if path.is_file()]),
                33,
            )
            self.assertTrue((destination / "UNTRUSTED-SOURCE-BOUNDARY.json").is_file())
            self.assertEqual(
                (destination / "source-data/SKILL.md").read_bytes(),
                validated.members["SKILL.md"],
            )
            normalized = json.loads(
                (destination / "normalized/capability-registry.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(normalized["canonical_capability_count"], 260)
            self.assertEqual(normalized["source_occurrence_count"], 262)
            runtime_manifest = json.loads(
                (destination / "normalized/runtime-manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(runtime_manifest["canonical_operation_count"], 260)
            self.assertEqual(runtime_manifest["source_task_id_count"], 0)
            self.assertEqual(runtime_manifest["source_dependency_edge_count"], 0)
            self.assertEqual(
                runtime_manifest["derived_runtime_dependency_kind"],
                "REPOSITORY_DERIVED_NOT_SOURCE_DECLARED",
            )
            self.assertNotIn("source_tasks", runtime_manifest)
            self.assertNotIn("source_dependency_edges", runtime_manifest)
            schema_root = output_root / importer.SCHEMA_RELATIVE
            schemas = sorted(schema_root.glob("*.schema.json"))
            self.assertEqual(len(schemas), 8)
            for schema_path in schemas:
                schema = json.loads(schema_path.read_text(encoding="utf-8"))
                self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
                self.assertFalse(schema["additionalProperties"])
            provenance = json.loads(
                (
                    output_root
                    / importer.PROVENANCE_RELATIVE
                    / "source-provenance.json"
                ).read_text(encoding="utf-8")
            )
            self.assertFalse(provenance["source_content_executed"])
            self.assertEqual(provenance["skill_count"], 12)
            for skill in importer.SKILL_REGISTRY.values():
                first_root = output_root / importer.SKILL_ROOTS[0] / skill.name
                second_root = output_root / importer.SKILL_ROOTS[1] / skill.name
                first_files = {
                    path.relative_to(first_root).as_posix(): path.read_bytes()
                    for path in first_root.rglob("*")
                    if path.is_file()
                }
                second_files = {
                    path.relative_to(second_root).as_posix(): path.read_bytes()
                    for path in second_root.rglob("*")
                    if path.is_file()
                }
                self.assertEqual(first_files, second_files)
                self.assertEqual(
                    set(first_files),
                    {"SKILL.md", "agents/openai.yaml", "compiled-contract.json"},
                )
                self.assertIn(b"repository-owned", first_files["SKILL.md"])
                contract = json.loads(first_files["compiled-contract.json"])
                self.assertFalse(contract["source"]["source_content_executed"])
                self.assertFalse(contract["gates"]["self_certification_allowed"])
            second = importer.materialize(validated, output_root=output_root)
            self.assertEqual(second["materialization"], "ALREADY_CURRENT")

            wrapper = (
                output_root
                / importer.SKILL_ROOTS[0]
                / "elmos-harness-contracts"
                / "compiled-contract.json"
            )
            original_wrapper = wrapper.read_bytes()
            wrapper.write_text("tampered", encoding="utf-8")
            with self.assertRaises(importer.IntegrationError) as error:
                importer.materialize(validated, output_root=output_root)
            self.assertEqual(error.exception.code, "OUTPUT_DRIFT")
            wrapper.write_bytes(original_wrapper)

            (destination / "normalized/contracts.json").write_text(
                "tampered", encoding="utf-8"
            )
            with self.assertRaises(importer.IntegrationError) as error:
                importer.materialize(validated, output_root=output_root)
            self.assertEqual(error.exception.code, "OUTPUT_DRIFT")

    def test_archive_symlink_is_rejected_before_read(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            link = Path(directory) / "archive.zip"
            try:
                link.symlink_to(PINNED_ARCHIVE)
            except OSError as exc:  # pragma: no cover - platform capability
                self.skipTest(str(exc))
            with self.assertRaises(importer.ArchiveSecurityError) as error:
                importer.validate_pinned_archive(link)
            self.assertEqual(error.exception.code, "ARCHIVE_SYMLINK")

    def test_pinned_digest_rejects_modified_archive_before_member_use(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            modified = Path(directory) / "modified.zip"
            modified.write_bytes(PINNED_ARCHIVE.read_bytes() + b"x")
            with self.assertRaises(importer.IntegrityError) as error:
                importer.validate_pinned_archive(modified)
            self.assertEqual(error.exception.code, "ARCHIVE_DIGEST_MISMATCH")


class ArchiveAttackTests(unittest.TestCase):
    def _assert_rejected(
        self,
        path: Path,
        policy: importer.ArchivePolicy,
        code: str,
    ) -> None:
        with self.assertRaises(importer.PDHIError) as error:
            importer.validate_archive(path, policy=policy)
        self.assertEqual(error.exception.code, code)

    def test_safe_minimal_fixture_is_accepted_without_source_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "safe.zip"
            _write_zip(path, [_member("pkg/safe.txt", b"safe")])
            validated = importer.validate_archive(
                path, policy=_policy(path, {"safe.txt": b"safe"})
            )
            self.assertEqual(dict(validated.members), {"safe.txt": b"safe"})
            self.assertEqual(dict(validated.contract_fields), {})

    def test_path_traversal_is_rejected_even_if_count_matches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "traversal.zip"
            _write_zip(path, [_member("pkg/../escape.txt", b"escape")])
            self._assert_rejected(
                path,
                _policy(path, {"safe.txt": b"escape"}),
                "MEMBER_PATH_TRAVERSAL",
            )

    def test_duplicate_member_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.zip"
            _write_zip(
                path,
                [
                    _member("pkg/safe.txt", b"one"),
                    _member("pkg/safe.txt", b"two"),
                ],
            )
            self._assert_rejected(
                path,
                _policy(path, {"safe.txt": b"one"}),
                "DUPLICATE_MEMBER",
            )

    def test_casefold_collision_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "casefold.zip"
            _write_zip(
                path,
                [
                    _member("pkg/A.txt", b"upper"),
                    _member("pkg/a.txt", b"lower"),
                ],
            )
            self._assert_rejected(
                path,
                _policy(path, {"A.txt": b"upper", "a.txt": b"lower"}),
                "CASEFOLD_COLLISION",
            )

    def test_symlink_member_mode_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "symlink-member.zip"
            _write_zip(
                path,
                [
                    _member(
                        "pkg/safe.txt",
                        b"../../outside",
                        mode=stat.S_IFLNK | 0o777,
                    )
                ],
            )
            self._assert_rejected(
                path,
                _policy(path, {"safe.txt": b"../../outside"}),
                "UNSAFE_MEMBER_MODE",
            )

    def test_unsupported_compression_method_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stored.zip"
            _write_zip(
                path,
                [_member("pkg/safe.txt", b"safe", method=zipfile.ZIP_STORED)],
            )
            self._assert_rejected(
                path,
                _policy(path, {"safe.txt": b"safe"}),
                "UNSUPPORTED_COMPRESSION",
            )

    def test_compression_ratio_and_member_size_limits_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ratio_path = Path(directory) / "ratio.zip"
            content = b"A" * 20_000
            _write_zip(ratio_path, [_member("pkg/safe.txt", content)])
            self._assert_rejected(
                ratio_path,
                _policy(
                    ratio_path,
                    {"safe.txt": content},
                    max_compression_ratio=2.0,
                ),
                "COMPRESSION_RATIO",
            )

            size_path = Path(directory) / "size.zip"
            _write_zip(size_path, [_member("pkg/safe.txt", b"0123456789")])
            self._assert_rejected(
                size_path,
                _policy(size_path, {"safe.txt": b"0123456789"}, max_member_bytes=4),
                "MEMBER_TOO_LARGE",
            )

    def test_encryption_flag_is_rejected_before_decompression(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "encrypted-flag.zip"
            _write_zip(path, [_member("pkg/safe.txt", b"safe")])
            blob = bytearray(path.read_bytes())
            local = blob.index(b"PK\x03\x04")
            central = blob.index(b"PK\x01\x02")
            struct.pack_into("<H", blob, local + 6, 1)
            struct.pack_into("<H", blob, central + 8, 1)
            path.write_bytes(blob)
            self._assert_rejected(
                path,
                _policy(path, {"safe.txt": b"safe"}),
                "ENCRYPTED_MEMBER",
            )

    def test_local_header_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "local-mismatch.zip"
            _write_zip(path, [_member("pkg/safe.txt", b"safe")])
            blob = bytearray(path.read_bytes())
            local = blob.index(b"PK\x03\x04")
            struct.pack_into("<H", blob, local + 8, zipfile.ZIP_STORED)
            path.write_bytes(blob)
            self._assert_rejected(
                path,
                _policy(path, {"safe.txt": b"safe"}),
                "LOCAL_HEADER_MISMATCH",
            )

    def test_non_utf8_member_name_is_rejected_from_raw_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad-name.zip"
            _write_zip(path, [_member("pkg/a.txt", b"safe")])
            blob = path.read_bytes().replace(b"pkg/a.txt", b"pkg/a.tx\xff")
            self.assertNotEqual(blob, path.read_bytes())
            path.write_bytes(blob)
            self._assert_rejected(
                path,
                _policy(path, {"a.txt": b"safe"}),
                "MEMBER_NAME_UTF8",
            )

    def test_non_utf8_member_content_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad-content.zip"
            _write_zip(path, [_member("pkg/safe.txt", b"\xff")])
            self._assert_rejected(
                path,
                _policy(path, {"safe.txt": b"\xff"}),
                "MEMBER_CONTENT_UTF8",
            )

    def test_trailing_bytes_are_rejected_even_with_matching_test_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trailing.zip"
            _write_zip(path, [_member("pkg/safe.txt", b"safe")])
            path.write_bytes(path.read_bytes() + b"hidden")
            self._assert_rejected(
                path,
                _policy(path, {"safe.txt": b"safe"}),
                "ZIP_TRAILING_DATA",
            )


if __name__ == "__main__":
    unittest.main()
