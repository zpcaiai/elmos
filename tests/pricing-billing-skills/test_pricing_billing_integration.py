from __future__ import annotations

import contextlib
import io
import json
import os
import runpy
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLING_ROOT = REPO_ROOT / "tooling"
if str(TOOLING_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLING_ROOT))

import integrate_pricing_billing_skills as integration  # noqa: E402
import validate_pricing_billing_installed as installed_validator  # noqa: E402


ARCHIVE = REPO_ROOT / integration.ARCHIVE_RELATIVE


def _filesystem_tree(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        path.relative_to(root).as_posix(): (
            path.read_bytes(),
            stat.S_IMODE(path.stat().st_mode),
        )
        for path in root.rglob("*")
        if path.is_file()
    }


class PricingBillingIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.snapshot = integration.validate_archive(ARCHIVE)

    def test_pinned_archive_identity_counts_names_and_dags(self) -> None:
        snapshot = self.snapshot
        self.assertEqual(snapshot.archive_sha256, integration.ARCHIVE_SHA256)
        self.assertEqual(len(snapshot.archive_bytes), integration.ARCHIVE_BYTES)
        self.assertEqual(len(snapshot.files), integration.EXPECTED_ENTRY_COUNT)
        self.assertEqual(
            sum(len(payload.content) for payload in snapshot.files.values()),
            integration.EXPECTED_UNCOMPRESSED_BYTES,
        )
        self.assertEqual(snapshot.internal_checksum_count, 129)
        self.assertEqual(snapshot.controlled_file_count, 128)
        self.assertEqual(len(snapshot.skills), 18)
        self.assertEqual(len(snapshot.batches), 54)
        self.assertEqual(
            tuple(record.name for record in snapshot.skills),
            integration.EXPECTED_SKILL_NAMES,
        )
        self.assertEqual(
            tuple(batch.source_id for batch in snapshot.batches),
            tuple(f"B{index:02d}" for index in range(54)),
        )
        self.assertEqual(sum(snapshot.requirement_priority_counts.values()), 180)
        self.assertEqual(sum(snapshot.scenario_priority_counts.values()), 50)
        self.assertEqual(snapshot.executable_reference_tests, 4)
        self.assertEqual(
            {
                payload.mode: sum(
                    item.mode == payload.mode for item in snapshot.files.values()
                )
                for payload in snapshot.files.values()
            },
            integration.EXPECTED_MODE_COUNTS,
        )

    def test_archive_safety_rejects_traversal_and_symlink_members(self) -> None:
        cases = (
            (
                f"{integration.ARCHIVE_ROOT}/../escape",
                stat.S_IFREG | 0o644,
                "ambiguous path",
            ),
            (
                f"{integration.ARCHIVE_ROOT}/link",
                stat.S_IFLNK | 0o777,
                "symbolic link",
            ),
        )
        for name, mode, error in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                archive_path = Path(directory) / "unsafe.zip"
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = mode << 16
                with zipfile.ZipFile(archive_path, "w") as archive:
                    archive.writestr(info, b"x")
                with zipfile.ZipFile(archive_path, "r") as archive:
                    with self.assertRaisesRegex(integration.IntegrationError, error):
                        integration._validate_central_directory(
                            archive,
                            expected_entries=1,
                            expected_uncompressed_bytes=1,
                        )

    def test_check_write_and_validator_reject_lexical_symlink_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            target = base / "real-repository"
            target.mkdir()
            link = base / "repository-link"
            link.symlink_to(target, target_is_directory=True)

            for action in (integration.check_outputs, integration.write_outputs):
                with self.subTest(action=action.__name__), self.assertRaisesRegex(
                    integration.IntegrationError,
                    "repository root must not be a symlink",
                ):
                    action(link, self.snapshot)

            for mode in ("--check", "--write"):
                stderr = io.StringIO()
                with self.subTest(mode=mode), contextlib.redirect_stderr(
                    stderr
                ), self.assertRaises(SystemExit) as raised:
                    integration.main([mode, "--repo-root", str(link)])
                self.assertEqual(raised.exception.code, 1)
                self.assertIn("repository root must not be a symlink", stderr.getvalue())

            with self.assertRaisesRegex(
                installed_validator.ValidationError,
                "repository root must not be a symlink",
            ):
                installed_validator.validate(link)
            self.assertEqual(list(target.iterdir()), [])

    def test_check_write_and_validator_reject_lexical_symlink_archive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "repository"
            root.mkdir()
            archive_link = base / "archive-link.zip"
            archive_link.symlink_to(ARCHIVE)

            with self.assertRaisesRegex(
                integration.IntegrationError,
                "source archive must be a regular file",
            ):
                integration.validate_archive(archive_link)

            for mode in ("--check", "--write"):
                stderr = io.StringIO()
                with self.subTest(mode=mode), contextlib.redirect_stderr(
                    stderr
                ), self.assertRaises(SystemExit) as raised:
                    integration.main(
                        [
                            mode,
                            "--repo-root",
                            str(root),
                            "--archive",
                            str(archive_link),
                        ]
                    )
                self.assertEqual(raised.exception.code, 1)
                self.assertIn("source archive must not be a symlink", stderr.getvalue())

            validator_root = base / "validator-repository"
            validator_archive = validator_root / integration.ARCHIVE_RELATIVE
            validator_archive.parent.mkdir(parents=True)
            validator_archive.symlink_to(ARCHIVE)
            with self.assertRaisesRegex(
                installed_validator.ValidationError,
                "source archive must be a regular file",
            ):
                installed_validator.validate(validator_root)
            self.assertEqual(list(root.iterdir()), [])

    def test_internal_checksums_reject_same_size_payload_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tampered = Path(directory) / "tampered.zip"
            with zipfile.ZipFile(ARCHIVE, "r") as source, zipfile.ZipFile(
                tampered, "w"
            ) as target:
                for info in source.infolist():
                    payload = source.read(info)
                    if info.filename.endswith("/README.md"):
                        payload = bytes([payload[0] ^ 1]) + payload[1:]
                    target.writestr(info, payload)
            with self.assertRaisesRegex(
                integration.IntegrationError, "internal checksum mismatch"
            ):
                integration.validate_archive(
                    tampered,
                    expected_sha256=None,
                    expected_archive_bytes=None,
                )

    def test_contract_rejects_skill_name_and_skill_or_batch_dag_drift(self) -> None:
        files = dict(self.snapshot.files)
        skill_manifest_path = "manifests/skills.manifest.json"
        skill_manifest = json.loads(files[skill_manifest_path].content)
        skill_manifest["skills"][0]["name"] = "renamed-billing-orchestrator"
        name_drift = dict(files)
        name_drift[skill_manifest_path] = integration.FilePayload(
            integration._json_bytes(skill_manifest)
        )
        with self.assertRaisesRegex(integration.IntegrationError, "name/order drift"):
            integration._validate_package_contracts(name_drift)

        skill_manifest = json.loads(files[skill_manifest_path].content)
        skill_manifest["skills"][0]["depends_on"] = [
            skill_manifest["skills"][1]["name"]
        ]
        skill_cycle = dict(files)
        skill_cycle[skill_manifest_path] = integration.FilePayload(
            integration._json_bytes(skill_manifest)
        )
        with self.assertRaisesRegex(integration.IntegrationError, "cycle in Skill DAG"):
            integration._validate_package_contracts(skill_cycle)

        batch_manifest_path = "manifests/batches.manifest.json"
        batch_manifest = json.loads(files[batch_manifest_path].content)
        batch_manifest["batches"][0]["depends_on"] = ["B01"]
        batch_cycle = dict(files)
        batch_cycle[batch_manifest_path] = integration.FilePayload(
            integration._json_bytes(batch_manifest)
        )
        with self.assertRaisesRegex(integration.IntegrationError, "cycle in batch DAG"):
            integration._validate_package_contracts(batch_cycle)

    def test_generation_is_deterministic_and_support_helpers_are_non_executable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_report = integration.write_outputs(root, self.snapshot)
            first = {
                tree.relative_root.as_posix(): _filesystem_tree(
                    root / tree.relative_root
                )
                for tree in integration.build_managed_trees(self.snapshot)
            }
            second_report = integration.write_outputs(root, self.snapshot)
            second = {
                tree.relative_root.as_posix(): _filesystem_tree(
                    root / tree.relative_root
                )
                for tree in integration.build_managed_trees(self.snapshot)
            }
            self.assertEqual(first, second)
            self.assertEqual(first_report["mode"], "write")
            self.assertEqual(second_report["mode"], "write")

            extracted = _filesystem_tree(root / integration.SOURCE_RELATIVE)
            self.assertEqual(
                extracted,
                {
                    relative: (payload.content, payload.mode)
                    for relative, payload in self.snapshot.files.items()
                },
            )
            support = _filesystem_tree(root / integration.SUPPORT_RELATIVE)
            self.assertTrue(support)
            self.assertTrue(all(mode == 0o644 for _content, mode in support.values()))
            self.assertEqual(
                json.loads(
                    support["install-manifest.json"][0].decode("utf-8")
                )["source_helpers_executed"],
                False,
            )
            support_manifest = json.loads(
                support["install-manifest.json"][0].decode("utf-8")
            )
            self.assertEqual(
                support_manifest["archive_digest_scope"], "BYTE_IDENTITY_ONLY"
            )
            self.assertEqual(
                support_manifest["provenance_attestation"], "NOT_PROVIDED"
            )
            self.assertIn(
                integration.ARCHIVE_IDENTITY_NOTICE,
                support["INTEGRATION_BOUNDARY.md"][0].decode("utf-8"),
            )

    def test_dual_root_parity_and_exact_openai_metadata(self) -> None:
        for record in self.snapshot.skills:
            left = REPO_ROOT / integration.INSTALL_ROOTS[0] / record.name
            right = REPO_ROOT / integration.INSTALL_ROOTS[1] / record.name
            self.assertEqual(_filesystem_tree(left), _filesystem_tree(right))
            interface = (left / "agents/openai.yaml").read_text(encoding="utf-8")
            fields: dict[str, str] = {}
            for line in interface.splitlines():
                if line.startswith("  ") and ": " in line:
                    key, value = line.strip().split(": ", 1)
                    if value.startswith('"'):
                        fields[key] = json.loads(value)
            self.assertEqual(fields["display_name"], record.title)
            self.assertEqual(
                fields["short_description"],
                "Apply imported Elmos billing guidance safely",
            )
            self.assertGreaterEqual(len(fields["short_description"]), 25)
            self.assertLessEqual(len(fields["short_description"]), 64)
            self.assertTrue(fields["default_prompt"].startswith(f"Use ${record.name} "))
            self.assertIn(integration.PACKAGE_NAMESPACE, fields["default_prompt"])
            self.assertIn("allow_implicit_invocation: true", interface)
            self.assertIn(
                integration.ARCHIVE_IDENTITY_NOTICE,
                (left / "SKILL.md").read_text(encoding="utf-8"),
            )

    def test_installed_validator_checks_manifest_provenance_and_overlap(self) -> None:
        report = installed_validator.validate(REPO_ROOT)
        self.assertEqual(report["decision"], "INSTALLED_ARTIFACTS_VERIFIED")
        self.assertEqual(report["archive_sha256"], integration.ARCHIVE_SHA256)
        self.assertRegex(report["installed_manifest_sha256"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(report["skills"], 18)
        self.assertEqual(report["batches"], 54)
        self.assertEqual(report["requirements"], 180)
        self.assertFalse(report["source_scripts_executed"])
        self.assertEqual(report["runtime_implementation"], "LOCAL_REFERENCE_BOUND")
        self.assertRegex(report["runtime_binding_sha256"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(report["external_evidence"], "NOT_RUN")
        self.assertEqual(report["certification"], "NOT_CERTIFIED")

    def test_installed_validator_rejects_stale_runtime_binding(self) -> None:
        with mock.patch.object(
            installed_validator.runtime_binding_builder,
            "build_document",
            return_value={"stale": True},
        ), self.assertRaisesRegex(
            installed_validator.ValidationError,
            "runtime binding is stale",
        ):
            installed_validator.validate(REPO_ROOT)

    def test_unmanaged_collision_is_atomic_and_output_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            collision = (
                root
                / integration.INSTALL_ROOTS[0]
                / integration.EXPECTED_SKILL_NAMES[0]
            )
            collision.mkdir(parents=True)
            (collision / "unmanaged.txt").write_text("owner data\n", encoding="utf-8")
            with self.assertRaisesRegex(integration.IntegrationError, "file drift"):
                integration.write_outputs(root, self.snapshot)
            self.assertFalse((root / integration.SOURCE_RELATIVE).exists())
            self.assertFalse((root / integration.SUPPORT_RELATIVE).exists())
            self.assertEqual(
                (collision / "unmanaged.txt").read_text(encoding="utf-8"),
                "owner data\n",
            )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            integration.write_outputs(root, self.snapshot)
            drift = (
                root
                / integration.INSTALL_ROOTS[1]
                / integration.EXPECTED_SKILL_NAMES[0]
                / "SKILL.md"
            )
            drift.write_bytes(drift.read_bytes() + b"drift\n")
            with self.assertRaisesRegex(integration.IntegrationError, "content drift"):
                integration.check_outputs(root, self.snapshot)

    def test_archive_validation_and_generation_never_execute_source_helpers(self) -> None:
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            subprocess, "Popen", side_effect=AssertionError("subprocess executed")
        ) as popen, mock.patch.object(
            os, "system", side_effect=AssertionError("shell executed")
        ) as system, mock.patch.object(
            runpy, "run_path", side_effect=AssertionError("source script executed")
        ) as run_path:
            snapshot = integration.validate_archive(ARCHIVE)
            integration.write_outputs(Path(directory), snapshot)
        popen.assert_not_called()
        system.assert_not_called()
        run_path.assert_not_called()


if __name__ == "__main__":
    unittest.main()
