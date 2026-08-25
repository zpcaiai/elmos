from __future__ import annotations

import io
import json
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts.operations import build_spring_clean_source_images as subject


COMMIT = "a" * 40
CONTEXT_DIGEST = "b" * 64
STATUS_DIGEST = "c" * 64


class SpringCleanSourceBuildTest(unittest.TestCase):
    def _tar(self, root: Path, entries: list[tuple[str, bytes, bytes | None]]) -> Path:
        archive = root / "source.tar"
        with tarfile.open(archive, "w") as handle:
            for name, kind, payload in entries:
                member = tarfile.TarInfo(name)
                member.mode = 0o644
                if kind == tarfile.REGTYPE:
                    assert payload is not None
                    member.size = len(payload)
                    handle.addfile(member, io.BytesIO(payload))
                else:
                    member.type = kind
                    member.linkname = "target"
                    handle.addfile(member)
        return archive

    def test_commit_is_exact_lowercase_40_hex(self) -> None:
        self.assertEqual(COMMIT, subject.validate_commit(COMMIT))
        for value in ("a" * 39, "a" * 41, "A" * 40, "HEAD", "main"):
            with self.subTest(value=value), self.assertRaises(subject.BuildFailure):
                subject.validate_commit(value)

    def test_image_tags_are_explicit_non_latest_and_well_formed(self) -> None:
        valid = "localhost:5000/elmos/java-runtime-runner:spring-a1"
        self.assertEqual(valid, subject.validate_image_tag(valid))
        for value in (
            "elmos/runtime",
            "elmos/runtime:latest",
            f"elmos/runtime@sha256:{'a' * 64}",
            "ELMOS/runtime:test",
            "elmos//runtime:test",
        ):
            with self.subTest(value=value), self.assertRaises(subject.BuildFailure):
                subject.validate_image_tag(value)

    def test_canonical_source_status_digest_is_stable(self) -> None:
        status = subject.source_status_document(
            source_commit=COMMIT,
            context_sha256=CONTEXT_DIGEST,
            file_count=2,
            byte_count=7,
        )
        first = subject.canonical_json_bytes(status)
        second = subject.canonical_json_bytes(dict(reversed(list(status.items()))))
        self.assertEqual(first, second)
        self.assertEqual(subject.sha256_bytes(first), subject.sha256_bytes(second))
        self.assertNotIn(b"created_at", first)
        self.assertEqual("CLEAN_SOURCE", status["source_state"])
        self.assertFalse(status["source_dirty"])

    def test_git_tree_rejects_submodules_and_symlinks(self) -> None:
        for mode, object_type, expected in (
            (b"160000", b"commit", "submodule"),
            (b"120000", b"blob", "symbolic link"),
        ):
            payload = mode + b" " + object_type + b" " + b"d" * 40 + b"\tdeps/x\x00"
            with self.subTest(mode=mode), self.assertRaisesRegex(subject.BuildFailure, expected):
                subject.parse_git_tree(payload)

    def test_git_tree_rejects_unsafe_and_case_colliding_paths(self) -> None:
        unsafe = b"100644 blob " + b"d" * 40 + b"\t../escape\x00"
        with self.assertRaises(subject.BuildFailure):
            subject.parse_git_tree(unsafe)
        colliding = (
            b"100644 blob " + b"d" * 40 + b"\tA.txt\x00"
            b"100644 blob " + b"e" * 40 + b"\ta.txt\x00"
        )
        with self.assertRaisesRegex(subject.BuildFailure, "colliding"):
            subject.parse_git_tree(colliding)

    def test_safe_extract_rejects_traversal_links_and_lfs_pointers(self) -> None:
        cases = (
            ([("../escape", tarfile.REGTYPE, b"x")], {"../escape": "100644"}, "path traversal"),
            ([("link", tarfile.SYMTYPE, None)], {"link": "100644"}, "link"),
            (
                [("large.bin", tarfile.REGTYPE, subject.LFS_POINTER_PREFIX + b"\noid sha256:x\n")],
                {"large.bin": "100644"},
                "LFS",
            ),
            (
                [(".gitattributes", tarfile.REGTYPE, b"*.bin filter=lfs diff=lfs\n")],
                {".gitattributes": "100644"},
                "LFS",
            ),
        )
        for entries, expected, message in cases:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                archive = self._tar(root, entries)
                with self.assertRaisesRegex(subject.BuildFailure, message):
                    subject.safe_extract_git_archive(archive, root / "context", expected)

    def test_safe_extract_emits_deterministic_content_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self._tar(
                root,
                [
                    ("z.txt", tarfile.REGTYPE, b"z"),
                    ("a/b.txt", tarfile.REGTYPE, b"hello"),
                ],
            )
            result = subject.safe_extract_git_archive(
                archive,
                root / "context",
                {"a/b.txt": "100644", "z.txt": "100644"},
            )
            self.assertEqual(["a/b.txt", "z.txt"], [item["path"] for item in result["manifest"]["files"]])
            self.assertEqual(6, result["byte_count"])
            self.assertEqual(
                result["context_sha256"],
                subject.sha256_bytes(subject.canonical_json_bytes(result["manifest"])),
            )

    def test_archive_limits_fail_before_destination_is_created(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self._tar(
                root,
                [
                    ("a.txt", tarfile.REGTYPE, b"a"),
                    ("b.txt", tarfile.REGTYPE, b"b"),
                ],
            )
            destination = root / "context"
            with patch.object(subject, "MAX_ARCHIVE_ENTRY_COUNT", 1), self.assertRaisesRegex(
                subject.BuildFailure, "entry hard limit"
            ):
                subject.safe_extract_git_archive(
                    archive,
                    destination,
                    {"a.txt": "100644", "b.txt": "100644"},
                )
            self.assertFalse(destination.exists())

            with patch.object(subject, "MAX_ARCHIVE_REGULAR_BYTES", 1), self.assertRaisesRegex(
                subject.BuildFailure, "regular-byte hard limit"
            ):
                subject.safe_extract_git_archive(
                    archive,
                    destination,
                    {"a.txt": "100644", "b.txt": "100644"},
                )
            self.assertFalse(destination.exists())

    def test_archive_capacity_is_checked_before_destination_file_and_each_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self._tar(root, [("a.txt", tarfile.REGTYPE, b"abcd")])
            evidence: list[dict[str, object]] = []
            with patch.object(subject, "EXTRACTION_BATCH_BYTES", 2), patch.object(
                subject.shutil,
                "disk_usage",
                return_value=SimpleNamespace(free=13 * subject.GIB),
            ) as disk_usage:
                subject.safe_extract_git_archive(
                    archive,
                    root / "context",
                    {"a.txt": "100644"},
                    capacity_path=root,
                    capacity_evidence=evidence,
                )
            self.assertEqual(4, disk_usage.call_count)
            self.assertEqual(
                [
                    "extract-archive:preflight",
                    "extract-archive:file-0:before",
                    "extract-archive:file-0:batch-0:before",
                    "extract-archive:file-0:batch-1:before",
                ],
                [item["stage"] for item in evidence],
            )

    def test_archive_capacity_failure_never_creates_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self._tar(root, [("a.txt", tarfile.REGTYPE, b"a")])
            destination = root / "context"
            required = (
                subject.HARD_STOP_FREE_BYTES
                + subject.EXTRACTION_METADATA_RESERVE_BYTES
                + 1
            )
            with patch.object(
                subject.shutil,
                "disk_usage",
                return_value=SimpleNamespace(free=required),
            ), self.assertRaises(subject.CapacityFailure):
                subject.safe_extract_git_archive(
                    archive,
                    destination,
                    {"a.txt": "100644"},
                    capacity_path=root,
                    capacity_evidence=[],
                )
            self.assertFalse(destination.exists())

    def test_archive_batch_capacity_failure_writes_no_payload_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self._tar(root, [("a.txt", tarfile.REGTYPE, b"abcd")])
            destination = root / "context"
            usage = [
                SimpleNamespace(free=13 * subject.GIB),
                SimpleNamespace(free=13 * subject.GIB),
                SimpleNamespace(free=subject.HARD_STOP_FREE_BYTES),
            ]
            with patch.object(subject.shutil, "disk_usage", side_effect=usage), self.assertRaises(
                subject.CapacityFailure
            ):
                subject.safe_extract_git_archive(
                    archive,
                    destination,
                    {"a.txt": "100644"},
                    capacity_path=root,
                    capacity_evidence=[],
                )
            self.assertEqual(b"", (destination / "a.txt").read_bytes())

    def test_capacity_requires_12_gib_to_start_and_hard_stops_at_8(self) -> None:
        evidence: list[dict[str, object]] = []
        with patch.object(subject.shutil, "disk_usage", return_value=SimpleNamespace(free=12 * subject.GIB)):
            subject.capacity_snapshot(
                Path("."),
                "build",
                evidence,
                minimum_free_bytes=subject.MINIMUM_BUILD_FREE_BYTES,
            )
        with patch.object(subject.shutil, "disk_usage", return_value=SimpleNamespace(free=12 * subject.GIB - 1)):
            with self.assertRaisesRegex(subject.CapacityFailure, "insufficient"):
                subject.capacity_snapshot(
                    Path("."),
                    "build",
                    [],
                    minimum_free_bytes=subject.MINIMUM_BUILD_FREE_BYTES,
                )
        with patch.object(subject.shutil, "disk_usage", return_value=SimpleNamespace(free=8 * subject.GIB)):
            with self.assertRaisesRegex(subject.CapacityFailure, "hard stop"):
                subject.capacity_snapshot(Path("."), "running", [])

    def test_command_runner_uses_argv_without_a_shell(self) -> None:
        process = Mock()
        process.wait.return_value = 0
        with tempfile.TemporaryDirectory() as temporary, patch.object(
            subject.shutil, "disk_usage", return_value=SimpleNamespace(free=13 * subject.GIB)
        ), patch.object(subject.subprocess, "Popen", return_value=process) as popen:
            root = Path(temporary)
            subject.run_command(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                log_path=root / "command.log",
                stage="test",
                capacity_path=root,
                capacity_evidence=[],
                command_evidence=[],
            )
        self.assertEqual(["git", "rev-parse", "HEAD"], popen.call_args.args[0])
        self.assertIs(False, popen.call_args.kwargs["shell"])

    def test_command_runner_terminates_when_capacity_crosses_hard_floor(self) -> None:
        process = Mock()
        process.pid = 42
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired(["docker"], 2), 0]
        usage = [SimpleNamespace(free=13 * subject.GIB), SimpleNamespace(free=8 * subject.GIB)]
        with tempfile.TemporaryDirectory() as temporary, patch.object(
            subject.shutil, "disk_usage", side_effect=usage
        ), patch.object(subject.subprocess, "Popen", return_value=process), patch.object(
            subject.os, "killpg"
        ) as killpg:
            root = Path(temporary)
            with self.assertRaises(subject.CapacityFailure):
                subject.run_command(
                    ["docker", "buildx", "build"],
                    cwd=root,
                    log_path=root / "command.log",
                    stage="build",
                    capacity_path=root,
                    capacity_evidence=[],
                    command_evidence=[],
                    minimum_start_bytes=subject.MINIMUM_BUILD_FREE_BYTES,
                )
        killpg.assert_called_once_with(42, subject.signal.SIGTERM)

    def test_command_runner_terminates_child_when_interrupted(self) -> None:
        process = Mock()
        process.wait.side_effect = KeyboardInterrupt
        with tempfile.TemporaryDirectory() as temporary, patch.object(
            subject.shutil, "disk_usage", return_value=SimpleNamespace(free=13 * subject.GIB)
        ), patch.object(subject.subprocess, "Popen", return_value=process), patch.object(
            subject, "terminate_process_group"
        ) as terminate:
            root = Path(temporary)
            commands: list[dict[str, object]] = []
            with self.assertRaises(KeyboardInterrupt):
                subject.run_command(
                    ["docker", "buildx", "build"],
                    cwd=root,
                    log_path=root / "command.log",
                    stage="build-runtime",
                    capacity_path=root,
                    capacity_evidence=[],
                    command_evidence=commands,
                    minimum_start_bytes=subject.MINIMUM_BUILD_FREE_BYTES,
                )
        terminate.assert_called_once_with(process)
        self.assertEqual("INTERRUPTED", commands[0]["status"])
        self.assertIn("completed_at", commands[0])

    def test_docker_build_argv_binds_all_three_source_identities(self) -> None:
        argv = subject.docker_build_argv(
            subject.IMAGE_SPECS[0],
            tag="elmos/runtime:test-a",
            platform="linux/arm64",
            source_commit=COMMIT,
            context_sha256=CONTEXT_DIGEST,
            source_status_sha256=STATUS_DIGEST,
            context_dir=Path("/tmp/exact-context"),
        )
        self.assertEqual(["docker", "buildx", "build"], argv[:3])
        self.assertIn(f"ELMOS_SOURCE_REVISION={COMMIT}", argv)
        self.assertIn(f"ELMOS_SOURCE_CONTEXT_SHA256={CONTEXT_DIGEST}", argv)
        self.assertIn(f"ELMOS_SOURCE_STATUS_SHA256={STATUS_DIGEST}", argv)
        self.assertNotIn("sh", argv)
        self.assertNotIn("-c", argv)

    def test_existing_image_tag_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.object(
            subject,
            "run_command",
            return_value=subject.CommandResult(0, Path(temporary) / "inspect.log"),
        ):
            with self.assertRaisesRegex(subject.BuildFailure, "overwrite"):
                subject.ensure_tag_absent(
                    "elmos/runtime:test-a",
                    root=Path(temporary),
                    evidence_dir=Path(temporary),
                    capacity_evidence=[],
                    command_evidence=[],
                )

    def test_built_image_contract_requires_symmetric_clean_source_labels(self) -> None:
        labels = {
            "org.opencontainers.image.revision": COMMIT,
            "io.elmos.evidence.scope": "spring-modernization-local",
            "io.elmos.evidence.class": "LOCAL_NON_CERTIFYING",
            "io.elmos.build.source-status": "CLEAN_SOURCE",
            "io.elmos.build.source-dirty": "false",
            "io.elmos.build.context-sha256": CONTEXT_DIGEST,
            "io.elmos.build.context-status-sha256": STATUS_DIGEST,
        }
        record = {
            "Id": "sha256:" + "d" * 64,
            "Os": "linux",
            "Architecture": "arm64",
            "Variant": "v8",
            "Config": {"User": "10003:10003", "Labels": labels},
        }
        self.assertEqual(
            record["Id"],
            subject.validate_built_image(
                record,
                spec=subject.IMAGE_SPECS[0],
                platform="linux/arm64",
                source_commit=COMMIT,
                context_sha256=CONTEXT_DIGEST,
                source_status_sha256=STATUS_DIGEST,
            ),
        )
        labels["io.elmos.build.source-dirty"] = "true"
        with self.assertRaises(subject.BuildFailure):
            subject.validate_built_image(
                record,
                spec=subject.IMAGE_SPECS[0],
                platform="linux/arm64",
                source_commit=COMMIT,
                context_sha256=CONTEXT_DIGEST,
                source_status_sha256=STATUS_DIGEST,
            )

    def test_built_image_contract_requires_exact_requested_platform_metadata(self) -> None:
        labels = {
            "org.opencontainers.image.revision": COMMIT,
            "io.elmos.evidence.scope": "spring-modernization-local",
            "io.elmos.evidence.class": "LOCAL_NON_CERTIFYING",
            "io.elmos.build.source-status": "CLEAN_SOURCE",
            "io.elmos.build.source-dirty": "false",
            "io.elmos.build.context-sha256": CONTEXT_DIGEST,
            "io.elmos.build.context-status-sha256": STATUS_DIGEST,
        }
        base = {
            "Id": "sha256:" + "d" * 64,
            "Os": "linux",
            "Architecture": "amd64",
            "Variant": "",
            "Config": {"User": "10003:10003", "Labels": labels},
        }
        self.assertEqual(
            base["Id"],
            subject.validate_built_image(
                base,
                spec=subject.IMAGE_SPECS[0],
                platform="linux/amd64",
                source_commit=COMMIT,
                context_sha256=CONTEXT_DIGEST,
                source_status_sha256=STATUS_DIGEST,
            ),
        )
        arm64 = dict(base, Architecture="arm64", Variant="v8")
        self.assertEqual(
            arm64["Id"],
            subject.validate_built_image(
                arm64,
                spec=subject.IMAGE_SPECS[0],
                platform="linux/arm64",
                source_commit=COMMIT,
                context_sha256=CONTEXT_DIGEST,
                source_status_sha256=STATUS_DIGEST,
            ),
        )
        arm64_without_variant = dict(arm64)
        del arm64_without_variant["Variant"]
        self.assertEqual(
            arm64_without_variant["Id"],
            subject.validate_built_image(
                arm64_without_variant,
                spec=subject.IMAGE_SPECS[0],
                platform="linux/arm64",
                source_commit=COMMIT,
                context_sha256=CONTEXT_DIGEST,
                source_status_sha256=STATUS_DIGEST,
            ),
        )
        for field, value in (
            ("Os", "windows"),
            ("Architecture", "arm64"),
            ("Variant", "v2"),
        ):
            invalid = dict(base)
            invalid[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(
                subject.BuildFailure, "requested platform"
            ):
                subject.validate_built_image(
                    invalid,
                    spec=subject.IMAGE_SPECS[0],
                    platform="linux/amd64",
                    source_commit=COMMIT,
                    context_sha256=CONTEXT_DIGEST,
                    source_status_sha256=STATUS_DIGEST,
                )

    def test_invalid_input_still_writes_failure_evidence_without_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = subject.BuildConfig(
                repository_root=root,
                source_commit="HEAD",
                evidence_dir=root / "evidence",
                platform="linux/arm64",
                tags={
                    "runtime": "elmos/runtime:test-a",
                    "transformer": "elmos/transformer:test-a",
                    "verifier": "elmos/verifier:test-a",
                },
            )
            returncode, receipt, evidence = subject.build_clean_source_images(config)
            self.assertEqual(1, returncode)
            self.assertEqual("FAILED", receipt["status"])
            self.assertEqual([], receipt["commands"])
            persisted = json.loads(evidence.read_text(encoding="utf-8"))
            self.assertEqual("validate-input", persisted["failure"]["stage"])
            self.assertFalse(persisted["certification_eligible"])

    def test_extraction_capacity_stop_writes_fail_closed_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "command.log").write_bytes(b"mock")
            config = subject.BuildConfig(
                repository_root=root,
                source_commit=COMMIT,
                evidence_dir=root / "evidence",
                platform="linux/arm64",
                tags={
                    "runtime": "elmos/runtime:test-a",
                    "transformer": "elmos/transformer:test-a",
                    "verifier": "elmos/verifier:test-a",
                },
            )
            with patch.object(subject, "capacity_snapshot"), patch.object(
                subject, "verify_repository_and_commit"
            ), patch.object(subject, "ensure_tag_absent"), patch.object(
                subject, "parse_git_tree", return_value={"a.txt": "100644"}
            ), patch.object(
                subject,
                "run_command",
                return_value=subject.CommandResult(0, root / "command.log"),
            ), patch.object(
                subject,
                "safe_extract_git_archive",
                side_effect=subject.CapacityFailure(
                    "extract-archive:file-0:batch-0:before", "capacity hard stop reached"
                ),
            ):
                returncode, receipt, evidence = subject.build_clean_source_images(config)
            self.assertEqual(1, returncode)
            self.assertEqual("FAILED", receipt["status"])
            self.assertEqual(
                "extract-archive:file-0:batch-0:before", receipt["failure"]["stage"]
            )
            persisted = json.loads(evidence.read_text(encoding="utf-8"))
            self.assertEqual(receipt["failure"], persisted["failure"])
            self.assertEqual("FAILED", persisted["status"])
            self.assertFalse(persisted["certified"])

    def test_build_failure_finalizes_overall_and_active_image_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            command_log = root / "command.log"
            command_log.write_bytes(b"mock")
            config = subject.BuildConfig(
                repository_root=root,
                source_commit=COMMIT,
                evidence_dir=root / "evidence",
                platform="linux/arm64",
                tags={
                    "runtime": "elmos/runtime:test-a",
                    "transformer": "elmos/transformer:test-a",
                    "verifier": "elmos/verifier:test-a",
                },
            )

            def run_command(*args: object, **kwargs: object) -> subject.CommandResult:
                if kwargs.get("stage") == "build-runtime":
                    raise subject.BuildFailure("build-runtime", "network download failed")
                return subject.CommandResult(0, command_log)

            extracted = {
                "context_sha256": CONTEXT_DIGEST,
                "manifest": {"schema_version": "test", "files": []},
                "file_count": 1,
                "byte_count": 1,
                "archive_entry_count": 1,
                "archive_regular_byte_count": 1,
            }
            with patch.object(subject, "capacity_snapshot"), patch.object(
                subject, "verify_repository_and_commit"
            ), patch.object(subject, "ensure_tag_absent"), patch.object(
                subject, "parse_git_tree", return_value={"a.txt": "100644"}
            ), patch.object(
                subject, "run_command", side_effect=run_command
            ), patch.object(
                subject, "safe_extract_git_archive", return_value=extracted
            ), patch.object(
                subject,
                "write_canonical_json",
                side_effect=[CONTEXT_DIGEST, STATUS_DIGEST],
            ), patch.object(subject, "sha256_file", return_value="a" * 64):
                returncode, receipt, evidence = subject.build_clean_source_images(config)

            self.assertEqual(1, returncode)
            self.assertEqual("FAILED", receipt["status"])
            self.assertEqual("FAILED", receipt["overall_status"])
            self.assertEqual("FAILED", receipt["images"]["runtime"]["status"])
            self.assertEqual(
                receipt["failure"], receipt["images"]["runtime"]["failure"]
            )
            self.assertEqual("NOT_RUN", receipt["images"]["transformer"]["status"])
            persisted = json.loads(evidence.read_text(encoding="utf-8"))
            self.assertEqual("FAILED", persisted["overall_status"])
            self.assertEqual("FAILED", persisted["images"]["runtime"]["status"])


if __name__ == "__main__":
    unittest.main()
