from __future__ import annotations

import copy
import io
import json
import os
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from tooling import integrate_proof_driven_harness_v3 as integration


REPO_ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = REPO_ROOT / integration.ARCHIVE_RELATIVE_PATH
_AUDIT: integration.ArchiveAudit | None = None


def audited_package() -> integration.ArchiveAudit:
    global _AUDIT
    if _AUDIT is None:
        _AUDIT = integration.audit_archive(ARCHIVE)
    return _AUDIT


class ProofDrivenHarnessArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.audit = audited_package()
        with zipfile.ZipFile(ARCHIVE) as archive:
            cls.infos = archive.infolist()

    def test_pinned_archive_and_all_independent_counts(self) -> None:
        self.assertEqual(cls_digest := self.audit.archive_sha256, integration.ARCHIVE_SHA256)
        self.assertEqual(len(cls_digest), 64)
        self.assertEqual(self.audit.archive_bytes, integration.EXPECTED_ARCHIVE_BYTES)
        self.assertEqual(dict(self.audit.counts), integration.EXPECTED_COUNTS)
        self.assertEqual(len(self.audit.member_hashes), integration.EXPECTED_FILE_COUNT)

    def test_unlisted_pyc_are_exact_and_quarantined(self) -> None:
        self.assertEqual(
            dict(self.audit.quarantined_pyc), integration.EXPECTED_QUARANTINED_PYC
        )
        self.assertEqual(len(self.audit.quarantined_pyc), 21)
        self.assertTrue(all(name.endswith(".pyc") for name in self.audit.quarantined_pyc))
        security = self.audit.summary()["security"]
        self.assertFalse(security["archive_content_executed"])
        self.assertTrue(security["selective_inert_data_materialized"])
        self.assertFalse(security["archive_executable_content_materialized"])
        self.assertFalse(security["archive_instruction_content_materialized"])
        self.assertEqual(
            [member["path"] for member in security["materialized_members"]],
            ["PACKAGE_MANIFEST.json", "skills/registry.json"],
        )
        for (output_name, _), member in zip(
            integration.MATERIALIZED_SOURCE_DATA,
            security["materialized_members"],
            strict=True,
        ):
            self.assertEqual(member["sha256"], self.audit.member_hashes[member["path"]])
            self.assertEqual(member["classification"], "INERT_SOURCE_DATA")
            self.assertEqual(
                member["materialized_as"],
                str(integration.DOCS_ROOT / ".source-data" / output_name),
            )

    def test_source_policy_is_not_misrepresented_as_license_or_attestation(self) -> None:
        assurance = self.audit.source_assurance()
        self.assertEqual(assurance["archive_digest_scope"], "BYTE_IDENTITY_ONLY")
        self.assertFalse(assurance["license"]["approved_license_present"])
        self.assertFalse(assurance["license"]["policy_is_approved_license"])
        self.assertFalse(assurance["license"]["policy_is_execution_authority"])
        self.assertEqual(assurance["license"]["legal_review_status"], "NOT_RUN")
        self.assertFalse(assurance["supply_chain"]["signature_present"])
        self.assertFalse(assurance["supply_chain"]["sbom_present"])
        self.assertFalse(
            assurance["supply_chain"]["provenance_attestation_present"]
        )
        self.assertFalse(assurance["commercial_distribution_authorized"])
        self.assertEqual(self.audit.summary()["source_assurance"], assurance)

    def test_archive_audit_uses_one_in_memory_snapshot_and_detects_path_swap(self) -> None:
        observed_inputs: list[object] = []
        zip_file = integration.zipfile.ZipFile

        def observe(value: object, *args: object, **kwargs: object) -> zipfile.ZipFile:
            observed_inputs.append(value)
            return zip_file(value, *args, **kwargs)

        with mock.patch.object(integration.zipfile, "ZipFile", side_effect=observe):
            audited = integration.audit_archive(ARCHIVE)
        self.assertEqual(audited.archive_sha256, integration.ARCHIVE_SHA256)
        self.assertEqual(len(observed_inputs), 1)
        self.assertIsInstance(observed_inputs[0], io.BytesIO)

        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            archive_copy = temporary_root / "source.zip"
            archive_copy.write_bytes(ARCHIVE.read_bytes())
            displaced = temporary_root / "displaced.zip"
            original_validate = integration.validate_zip_members
            swapped = False

            def swap_after_snapshot(
                infos: list[zipfile.ZipInfo],
            ) -> dict[str, zipfile.ZipInfo]:
                nonlocal swapped
                result = original_validate(infos)
                if not swapped:
                    archive_copy.rename(displaced)
                    archive_copy.symlink_to(ARCHIVE)
                    swapped = True
                return result

            with mock.patch.object(
                integration,
                "validate_zip_members",
                side_effect=swap_after_snapshot,
            ):
                with self.assertRaisesRegex(
                    integration.IntegrationError,
                    "pathname identity changed",
                ):
                    integration.audit_archive(archive_copy)

    def _mutated_infos(self, index: int, **changes: object) -> list[zipfile.ZipInfo]:
        infos = list(self.infos)
        replacement = copy.copy(infos[index])
        for key, value in changes.items():
            setattr(replacement, key, value)
        infos[index] = replacement
        return infos

    def test_traversal_member_fails_closed(self) -> None:
        bad = f"{integration.ARCHIVE_ROOT}/../escape"
        with self.assertRaisesRegex(integration.IntegrationError, "unsafe ZIP path component"):
            integration.validate_zip_members(self._mutated_infos(1, filename=bad))

    def test_unicode_casefold_collision_fails_closed(self) -> None:
        first_file = next(i for i, info in enumerate(self.infos) if not info.is_dir())
        second_file = next(
            i for i, info in enumerate(self.infos) if not info.is_dir() and i != first_file
        )
        prefix = f"{integration.ARCHIVE_ROOT}/"
        relative = self.infos[first_file].filename[len(prefix) :]
        collision = prefix + relative.swapcase()
        with self.assertRaisesRegex(integration.IntegrationError, "collision"):
            integration.validate_zip_members(
                self._mutated_infos(second_file, filename=collision)
            )

    def test_symlink_encryption_and_ratio_fail_closed(self) -> None:
        file_index = next(i for i, info in enumerate(self.infos) if not info.is_dir())
        symlink_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaisesRegex(integration.IntegrationError, "symlink or special"):
            integration.validate_zip_members(
                self._mutated_infos(file_index, external_attr=symlink_attr)
            )
        with self.assertRaisesRegex(integration.IntegrationError, "encrypted"):
            integration.validate_zip_members(
                self._mutated_infos(
                    file_index, flag_bits=self.infos[file_index].flag_bits | 1
                )
            )
        large_index = max(range(len(self.infos)), key=lambda i: self.infos[i].file_size)
        with self.assertRaisesRegex(integration.IntegrationError, "compression ratio"):
            integration.validate_zip_members(
                self._mutated_infos(large_index, compress_size=1)
            )


class ProofDrivenHarnessInstallationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.audit = audited_package()

    def test_generated_wrappers_are_repo_owned_and_dual_root_identical(self) -> None:
        qualification = integration.qualification_state(REPO_ROOT, self.audit)
        outputs = integration.build_outputs(
            REPO_ROOT,
            self.audit,
            qualification=qualification,
        )
        for skill in integration.SKILLS:
            relative_files = (
                Path("SKILL.md"),
                Path("agents/openai.yaml"),
                Path("compiled-contract.json"),
            )
            for relative in relative_files:
                left = outputs[integration.INSTALL_ROOTS[0] / skill.name / relative]
                right = outputs[integration.INSTALL_ROOTS[1] / skill.name / relative]
                self.assertEqual(left, right)
            compiled = json.loads(
                outputs[
                    integration.INSTALL_ROOTS[0]
                    / skill.name
                    / "compiled-contract.json"
                ]
            )
            self.assertEqual(compiled["runtime"]["module"], "elmos_proof_harness.skills")
            self.assertEqual(compiled["runtime"]["registry"], "SKILL_REGISTRY")
            self.assertEqual(compiled["runtime"]["entrypoint"], "SkillRuntime.execute")
            self.assertEqual(
                compiled["status"]["implementation"],
                qualification.implementation_status,
            )
            self.assertEqual(
                compiled["qualification"]["receipt_sha256"],
                qualification.receipt_sha256,
            )
            self.assertEqual(compiled["status"]["external_runtime"], "NOT_RUN")
            self.assertEqual(compiled["status"]["certification"], "NOT_CERTIFIED")
        generated_paths = "\n".join(str(path) for path in outputs)
        self.assertNotIn(".pyc", generated_paths)
        self.assertNotIn("reference-implementation", generated_paths)
        source_assurance = json.loads(
            outputs[integration.DOCS_ROOT / "source-assurance.json"]
        )
        self.assertFalse(source_assurance["commercial_distribution_authorized"])

    def test_installation_is_transactional_and_rolls_back(self) -> None:
        skill = integration.SKILLS[0]
        first = integration.INSTALL_ROOTS[0] / skill.name / "SKILL.md"
        second = integration.DOCS_ROOT / "README.md"
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            target = repo / first
            target.parent.mkdir(parents=True)
            target.write_bytes(b"preexisting-user-state\n")
            outputs = {first: b"replacement\n", second: b"new documentation\n"}
            with self.assertRaisesRegex(integration.IntegrationError, "injected"):
                integration.install_outputs(repo, outputs, failure_after=1)
            self.assertEqual(target.read_bytes(), b"preexisting-user-state\n")
            self.assertFalse((repo / second).exists())
            self.assertFalse(integration._transaction_root(repo).exists())

    def test_transactional_install_then_exact_drift_check(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            outputs = integration.build_outputs(repo, self.audit)
            result = integration.install_outputs(repo, outputs)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["skills"], 16)
            self.assertTrue(result["dual_roots_byte_identical"])
            changed = repo / integration.INSTALL_ROOTS[0] / integration.SKILLS[0].name / "SKILL.md"
            changed.write_bytes(changed.read_bytes() + b"drift\n")
            with self.assertRaisesRegex(integration.IntegrationError, "changed"):
                integration.verify_installation(repo, outputs)

    def test_dirfd_publication_rejects_symlink_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            escape = root / "escape"
            repo.mkdir()
            escape.mkdir()
            (repo / "docs").symlink_to(escape, target_is_directory=True)
            with integration._repo_anchor(repo) as (_absolute, root_fd, _identity):
                with self.assertRaisesRegex(
                    integration.IntegrationError,
                    "unsafe anchored directory component",
                ):
                    integration._atomic_write_at(
                        root_fd,
                        integration.DOCS_ROOT / "README.md",
                        b"must-not-escape\n",
                    )
            self.assertEqual(list(escape.iterdir()), [])

    def test_dirfd_publication_stays_on_pinned_root_during_path_swap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            pinned = root / "pinned"
            escape = root / "escape"
            repo.mkdir()
            escape.mkdir()
            relative = integration.DOCS_ROOT / "anchored.txt"
            with integration._repo_anchor(repo) as (absolute, root_fd, root_identity):
                repo.rename(pinned)
                repo.symlink_to(escape, target_is_directory=True)
                integration._atomic_write_at(root_fd, relative, b"anchored\n")
                self.assertEqual((pinned / relative).read_bytes(), b"anchored\n")
                self.assertFalse((escape / relative).exists())
                with self.assertRaisesRegex(
                    integration.IntegrationError,
                    "pathname identity changed",
                ):
                    integration._assert_repo_anchor(absolute, root_identity)

    def test_dirfd_publication_detects_parent_swap_during_rename(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            parent = repo / integration.DOCS_ROOT
            displaced = repo / "docs/displaced-proof-harness"
            escape = root / "escape"
            parent.mkdir(parents=True)
            escape.mkdir()
            relative = integration.DOCS_ROOT / "raced.txt"
            replace = integration.os.replace
            swapped = False

            def swap_parent_then_replace(
                source: str,
                target: str,
                **kwargs: object,
            ) -> None:
                nonlocal swapped
                if not swapped:
                    parent.rename(displaced)
                    parent.symlink_to(escape, target_is_directory=True)
                    swapped = True
                replace(source, target, **kwargs)

            with integration._repo_anchor(repo) as (_absolute, root_fd, _identity):
                with mock.patch.object(
                    integration.os,
                    "replace",
                    side_effect=swap_parent_then_replace,
                ):
                    with self.assertRaisesRegex(
                        integration.IntegrationError,
                        "unsafe anchored directory component|parent identity changed",
                    ):
                        integration._atomic_write_at(root_fd, relative, b"anchored\n")
            self.assertEqual((displaced / "raced.txt").read_bytes(), b"anchored\n")
            self.assertFalse((escape / "raced.txt").exists())

    def test_checked_in_installation_matches_compiler(self) -> None:
        outputs = integration.build_outputs(REPO_ROOT, self.audit)
        if os.environ.get("ELMOS_PROOF_HARNESS_QUALIFICATION_PHASE") == "1":
            # Q -> I -> check intentionally qualifies before installing. The
            # receipt produced by this Q run therefore cannot match the
            # wrappers from the previous receipt yet; the following I/check
            # phase verifies the checked-in installation exactly.
            self.assertEqual(len(outputs), 104)
            return
        result = integration.verify_installation(REPO_ROOT, outputs)
        self.assertEqual(result["managed_files"], len(outputs))
        self.assertEqual(result["skills"], 16)


class ProofDrivenHarnessQualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.audit = audited_package()

    def test_missing_or_invalid_receipt_remains_declared(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            missing = integration.qualification_state(repo, self.audit)
            self.assertEqual(missing.implementation_status, integration.DECLARED_STATUS)
            self.assertEqual(missing.validation, "ABSENT")
            self.assertIsNone(missing.receipt_sha256)

            receipt = repo / integration.QUALIFICATION_RELATIVE_PATH
            receipt.parent.mkdir(parents=True)
            receipt.write_text("{}\n", encoding="utf-8")
            invalid = integration.qualification_state(repo, self.audit)
            self.assertEqual(invalid.implementation_status, integration.DECLARED_STATUS)
            self.assertEqual(invalid.validation, "INVALID")
            self.assertIsNone(invalid.receipt_sha256)

    def test_qualification_inventory_excludes_generated_build_trees(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            engine = repo / integration.ENGINE_ROOT
            source = engine / "src/runtime.py"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"runtime\n")
            generated = (
                engine / "build/lib/runtime.py",
                engine / "dist/runtime.whl",
                engine / "src/runtime.egg-info/PKG-INFO",
                engine / "src/__pycache__/runtime.pyc",
            )
            for path in generated:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"generated\n")
            with integration._repo_anchor(repo) as (
                _absolute,
                root_fd,
                _identity,
            ):
                records = integration._engine_inventory_at(root_fd)
            self.assertEqual([record["path"] for record in records], ["src/runtime.py"])

    def _write_valid_receipt(self, repo: Path) -> dict[str, object]:
        engine = repo / integration.ENGINE_ROOT
        qualifier = repo / integration.QUALIFIER_RELATIVE_PATH
        qualifier.parent.mkdir(parents=True)
        qualifier.write_bytes(b"# fixed repository-owned qualifier\n")
        source = engine / "src/runtime.py"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"SKILL_REGISTRY = {}\n")

        raw_references: list[dict[str, object]] = []
        passed = 0
        for index, (raw_path, argv_tail) in enumerate(
            integration._EXPECTED_RAW_LOG_COMMANDS.items(),
            start=1,
        ):
            test_count = index if index < 3 else 0
            record = {
                "schema_version": "1.0.0",
                "name": Path(raw_path).stem,
                "argv": ["/usr/bin/python3", *argv_tail],
                "cwd": ".",
                "returncode": 0,
                "timed_out": False,
                "wall_clock_milliseconds": index,
                "stdout": f"Ran {test_count} tests in 0.001s\nOK\n" if test_count else "PASS\n",
                "stderr": "",
            }
            payload = integration._canonical_json_bytes(record) + b"\n"
            raw_file = engine / Path(raw_path)
            raw_file.parent.mkdir(parents=True, exist_ok=True)
            raw_file.write_bytes(payload)
            raw_references.append(
                {
                    "path": raw_path,
                    "sha256": integration._sha256_bytes(payload),
                    "bytes": len(payload),
                }
            )
            passed += test_count

        with integration._repo_anchor(repo) as (_absolute, root_fd, _identity):
            records = integration._engine_inventory_at(root_fd)
        skill_names = sorted(skill.name for skill in integration.SKILLS)
        component_ids = [
            f"K{kernel}-C{component:02d}"
            for kernel in range(1, 9)
            for component in range(1, 13)
        ]
        receipt = {
            "schema_version": "1.0.0",
            "kind": "elmos.proof-driven-harness-v3.local-qualification",
            "status": "PASS",
            "package": {
                "name": integration.PACKAGE_NAME,
                "version": integration.PACKAGE_VERSION,
                "archive_sha256": self.audit.archive_sha256,
            },
            "engine": {
                "root": integration.ENGINE_ROOT.as_posix(),
                "tree_sha256": integration._sha256_bytes(
                    integration._canonical_json_bytes(records)
                ),
                "files": records,
                "skill_count": len(skill_names),
                "skill_names_sha256": integration._sha256_bytes(
                    integration._canonical_json_bytes(skill_names)
                ),
                "component_count": len(component_ids),
                "component_ids_sha256": integration._sha256_bytes(
                    integration._canonical_json_bytes(component_ids)
                ),
            },
            "tests": {
                "status": "PASS",
                "passed": passed,
                "failed": 0,
                "skipped": 0,
                "raw_logs": raw_references,
            },
            "qualifier": {
                "path": integration.QUALIFIER_RELATIVE_PATH.as_posix(),
                "sha256": integration._sha256_bytes(qualifier.read_bytes()),
            },
        }
        receipt_path = repo / integration.QUALIFICATION_RELATIVE_PATH
        receipt_path.write_bytes(integration._canonical_json_bytes(receipt) + b"\n")
        return receipt

    def test_only_exact_digest_bound_receipt_promotes_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            receipt = self._write_valid_receipt(repo)
            state = integration.qualification_state(repo, self.audit)
            receipt_payload = (repo / integration.QUALIFICATION_RELATIVE_PATH).read_bytes()
            self.assertEqual(state.implementation_status, integration.QUALIFIED_STATUS)
            self.assertEqual(state.validation, "VALID")
            self.assertEqual(
                state.receipt_sha256,
                integration._sha256_bytes(receipt_payload),
            )
            outputs = integration.build_outputs(
                repo,
                self.audit,
                qualification=state,
            )
            compiled = json.loads(
                outputs[
                    integration.INSTALL_ROOTS[0]
                    / integration.SKILLS[0].name
                    / "compiled-contract.json"
                ]
            )
            self.assertEqual(
                compiled["qualification"]["receipt_sha256"],
                integration._sha256_bytes(receipt_payload),
            )
            self.assertEqual(compiled["status"]["implementation"], integration.QUALIFIED_STATUS)

            engine_file = repo / integration.ENGINE_ROOT / "src/runtime.py"
            engine_file.write_bytes(engine_file.read_bytes() + b"# drift\n")
            downgraded = integration.qualification_state(repo, self.audit)
            self.assertEqual(downgraded.implementation_status, integration.DECLARED_STATUS)
            self.assertEqual(downgraded.validation, "INVALID")
            self.assertEqual(receipt["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
