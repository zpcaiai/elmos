from __future__ import annotations

import copy
import io
import json
from pathlib import Path
import stat
import tempfile
from typing import Any, ClassVar
import unittest
from unittest import mock
import zipfile

from tooling import integrate_harness_runtime_assurance_delta as integration


REPO_ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = REPO_ROOT / integration.ARCHIVE_RELATIVE_PATH
_AUDIT: integration.ArchiveAudit | None = None


def audited_delta() -> integration.ArchiveAudit:
    global _AUDIT
    if _AUDIT is None:
        _AUDIT = integration.audit_archive(ARCHIVE)
    return _AUDIT


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode()


class DeltaArchiveBoundaryTests(unittest.TestCase):
    audit: ClassVar[integration.ArchiveAudit]
    infos: ClassVar[list[zipfile.ZipInfo]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.audit = audited_delta()
        with zipfile.ZipFile(ARCHIVE) as archive:
            cls.infos = archive.infolist()

    def _mutated_infos(self, index: int, **changes: object) -> list[zipfile.ZipInfo]:
        infos = list(self.infos)
        replacement = copy.copy(infos[index])
        for key, value in changes.items():
            setattr(replacement, key, value)
        infos[index] = replacement
        return infos

    def test_pinned_identity_and_exact_counts(self) -> None:
        self.assertEqual(self.audit.archive_sha256, integration.ARCHIVE_SHA256)
        self.assertEqual(self.audit.archive_bytes, integration.ARCHIVE_BYTES)
        self.assertEqual(len(self.audit.member_hashes), integration.EXPECTED_FILES)
        self.assertEqual(
            len(self.audit.payload_hashes), integration.EXPECTED_PAYLOAD_FILES
        )
        self.assertEqual(len(self.audit.schemas), integration.EXPECTED_SCHEMAS)
        self.assertEqual(len(self.audit.examples), integration.EXPECTED_SCHEMAS)
        self.assertEqual(
            set(self.audit.source_assets), set(integration.SOURCE_ASSET_TARGETS)
        )

    def test_audit_uses_one_snapshot_and_detects_path_swap(self) -> None:
        observed: list[object] = []
        zip_file = integration.zipfile.ZipFile

        def observe(value: Any, *args: Any, **kwargs: Any) -> zipfile.ZipFile:
            observed.append(value)
            return zip_file(value, *args, **kwargs)

        with mock.patch.object(integration.zipfile, "ZipFile", side_effect=observe):
            integration.audit_archive(ARCHIVE)
        self.assertEqual(len(observed), 1)
        self.assertIsInstance(observed[0], io.BytesIO)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "delta.zip"
            source.write_bytes(ARCHIVE.read_bytes())
            displaced = root / "displaced.zip"
            original = integration._validate_infos
            swapped = False

            def swap_after_snapshot(
                infos: list[zipfile.ZipInfo],
            ) -> dict[str, zipfile.ZipInfo]:
                nonlocal swapped
                result = original(infos)
                if not swapped:
                    source.rename(displaced)
                    source.symlink_to(ARCHIVE)
                    swapped = True
                return result

            with mock.patch.object(
                integration, "_validate_infos", side_effect=swap_after_snapshot
            ):
                with self.assertRaisesRegex(
                    integration.IntegrationError, "pathname identity changed"
                ):
                    integration.audit_archive(source)

    def test_traversal_casefold_special_encryption_and_ratio_fail_closed(self) -> None:
        first = 0
        second = 1
        prefix = integration.ARCHIVE_ROOT + "/"
        relative = self.infos[first].filename.removeprefix(prefix)
        with self.assertRaisesRegex(integration.IntegrationError, "unsafe ZIP path"):
            integration._validate_infos(
                self._mutated_infos(first, filename=prefix + "../escape")
            )
        with self.assertRaisesRegex(integration.IntegrationError, "collision"):
            integration._validate_infos(
                self._mutated_infos(second, filename=prefix + relative.swapcase())
            )
        with self.assertRaisesRegex(integration.IntegrationError, "special"):
            integration._validate_infos(
                self._mutated_infos(
                    first,
                    external_attr=(stat.S_IFLNK | 0o777) << 16,
                )
            )
        with self.assertRaisesRegex(integration.IntegrationError, "encrypted"):
            integration._validate_infos(
                self._mutated_infos(
                    first,
                    flag_bits=self.infos[first].flag_bits | 1,
                )
            )
        largest = max(range(len(self.infos)), key=lambda i: self.infos[i].file_size)
        with self.assertRaisesRegex(integration.IntegrationError, "compression ratio"):
            integration._validate_infos(self._mutated_infos(largest, compress_size=1))

    def test_strict_json_rejects_duplicate_and_nonfinite_values(self) -> None:
        with self.assertRaisesRegex(integration.IntegrationError, "duplicate JSON key"):
            integration._strict_json(b'{"a":1,"a":2}', "duplicate.json")
        with self.assertRaisesRegex(integration.IntegrationError, "non-finite"):
            integration._strict_json(b'{"a":NaN}', "nan.json")

    def test_outputs_remain_bound_to_audited_snapshot(self) -> None:
        with mock.patch.object(
            integration,
            "_read_stable",
            side_effect=AssertionError("build_outputs reopened an input"),
        ):
            outputs = integration.build_outputs(
                self.audit,
                status="DECLARED_RUNTIME_UNQUALIFIED",
            )
        self.assertEqual(set(outputs), set(integration._expected_output_paths()))
        self.assertNotIn(
            integration.ENGINE_ROOT
            / "migrations/V304__harness_runtime_assurance_delta.sql",
            outputs,
        )
        boundary = json.loads(outputs[integration.DELTA_ROOT / "source-boundary.json"])
        self.assertFalse(boundary["source_migration"]["materialized"])
        self.assertFalse(boundary["source_migration"]["executed"])
        self.assertEqual(
            boundary["declarative_source_assets"]["classification"],
            "UNTRUSTED_DATA_NOT_RUNTIME_AUTHORITY",
        )


class DeltaTransactionalInstallTests(unittest.TestCase):
    outputs: ClassVar[dict[Path, bytes]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.outputs = integration.build_outputs(
            audited_delta(),
            status="DECLARED_RUNTIME_UNQUALIFIED",
        )

    def _changed_outputs(self) -> dict[Path, bytes]:
        outputs = dict(self.outputs)
        name = integration.EXPECTED_SKILLS[0][1]
        for root in (Path(".agents/skills"), Path("agent-skills/runtime")):
            path = root / name / "SKILL.md"
            outputs[path] = outputs[path] + b"\ntransaction-test\n"
        return outputs

    def test_install_check_and_dual_roots_are_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            result = integration.install_outputs(repo, self.outputs)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["files"], len(self.outputs))
            self.assertEqual(result["skills"], integration.EXPECTED_EXTENSION_SKILLS)
            self.assertTrue(result["dual_roots_byte_identical"])
            self.assertEqual(
                integration.verify_installation(repo, self.outputs), result
            )
            self.assertFalse((repo / integration.TRANSACTION_ROOT).exists())

    def test_cleanup_authority_cannot_target_cwd_or_arbitrary_directories(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            victim = repo / "victim"
            victim.mkdir()
            canary = victim / "must-survive.txt"
            canary.write_text("preserved\n", encoding="utf-8")
            transaction = integration.TRANSACTION_ROOT / ("a" * 32)
            transaction_path = repo / transaction
            transaction_path.parent.mkdir(parents=True, mode=0o700)
            transaction_path.mkdir(mode=0o700)
            (transaction_path / "transaction-only.txt").write_text(
                "safe-to-remove\n", encoding="utf-8"
            )

            with integration._repo_anchor(repo) as (_absolute, root_fd, _identity):
                for unsafe in (
                    Path(),
                    Path("."),
                    Path("victim"),
                    integration.TRANSACTION_ROOT,
                    integration.TRANSACTION_ROOT / "not-a-transaction-id",
                    transaction / "nested",
                ):
                    with (
                        self.subTest(unsafe=unsafe),
                        self.assertRaises(integration.IntegrationError),
                    ):
                        integration._remove_tree_at(root_fd, unsafe)
                with self.assertRaises(integration.IntegrationError):
                    integration._remove_empty_directory_at(root_fd, Path())
                with self.assertRaisesRegex(
                    integration.IntegrationError, "binding changed"
                ):
                    integration._remove_directory_contents_at(
                        root_fd, root_fd, transaction
                    )
                integration._remove_tree_at(root_fd, transaction)
                integration._remove_empty_directory_at(
                    root_fd, integration.TRANSACTION_ROOT
                )

            self.assertEqual(canary.read_text(encoding="utf-8"), "preserved\n")
            self.assertFalse(transaction_path.exists())

    def test_transaction_journal_is_bound_to_id_and_complete_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            expected = integration._expected_output_paths()
            with integration._repo_anchor(repo) as (_absolute, root_fd, _identity):
                transaction, journal = integration._create_transaction_at(
                    root_fd, expected
                )
                journal["transaction_id"] = "0" * 32
                integration._write_journal_at(
                    root_fd, transaction / "journal.json", journal
                )
                with self.assertRaisesRegex(
                    integration.IntegrationError, "invalid transaction journal"
                ):
                    integration._recover_transactions_at(root_fd, expected)

                journal["transaction_id"] = transaction.name
                journal["state"] = "COMMITTED"
                integration._write_journal_at(
                    root_fd, transaction / "journal.json", journal
                )
                with self.assertRaisesRegex(
                    integration.IntegrationError, "incomplete committed transaction"
                ):
                    integration._recover_transactions_at(root_fd, expected)

                journal["state"] = "ROLLED_BACK"
                integration._write_journal_at(
                    root_fd, transaction / "journal.json", journal
                )
                integration._recover_transactions_at(root_fd, expected)
            self.assertFalse((repo / integration.TRANSACTION_ROOT).exists())

    def test_exclusive_lock_rejects_pathname_inode_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            lock_path = repo / "delta.lock"
            original_flock = integration.fcntl.flock
            replaced = False

            def replace_after_lock(descriptor: int, operation: int) -> None:
                nonlocal replaced
                original_flock(descriptor, operation)
                lock_path.unlink()
                lock_path.write_bytes(b"replacement")
                replaced = True

            entered = False
            with (
                mock.patch.object(integration, "_lock_path", return_value=lock_path),
                mock.patch.object(
                    integration.fcntl, "flock", side_effect=replace_after_lock
                ),
                self.assertRaisesRegex(integration.IntegrationError, "binding"),
            ):
                with integration._exclusive_lock(repo):
                    entered = True
            self.assertTrue(replaced)
            self.assertFalse(entered)

    def test_injected_failure_rolls_back_every_published_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            integration.install_outputs(repo, self.outputs)
            changed = self._changed_outputs()
            with self.assertRaisesRegex(integration.IntegrationError, "injected"):
                integration.install_outputs(repo, changed, failure_after=1)
            integration.verify_installation(repo, self.outputs)
            self.assertFalse((repo / integration.TRANSACTION_ROOT).exists())

    def test_precommit_qualification_revalidation_failure_rolls_back(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            integration.install_outputs(repo, self.outputs)
            changed = self._changed_outputs()

            def reject_stale_qualification() -> None:
                raise integration.IntegrationError(
                    "qualification binding changed during integration"
                )

            with self.assertRaisesRegex(
                integration.IntegrationError, "qualification binding changed"
            ):
                integration.install_outputs(
                    repo,
                    changed,
                    precommit_validate=reject_stale_qualification,
                )
            integration.verify_installation(repo, self.outputs)
            self.assertFalse((repo / integration.TRANSACTION_ROOT).exists())

    def test_interrupted_rollback_is_recovered_on_next_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            integration.install_outputs(repo, self.outputs)
            changed = self._changed_outputs()
            with mock.patch.object(
                integration,
                "_rollback_transaction_at",
                side_effect=integration.IntegrationError("simulated process loss"),
            ):
                with self.assertRaisesRegex(
                    integration.IntegrationError, "rollback failed"
                ):
                    integration.install_outputs(repo, changed, failure_after=1)
            self.assertTrue((repo / integration.TRANSACTION_ROOT).exists())
            integration.install_outputs(repo, self.outputs)
            integration.verify_installation(repo, self.outputs)
            self.assertFalse((repo / integration.TRANSACTION_ROOT).exists())

    def test_extra_file_and_content_drift_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            integration.install_outputs(repo, self.outputs)
            extra = repo / integration.DELTA_ROOT / "unmanaged.txt"
            extra.write_text("unmanaged\n", encoding="utf-8")
            with self.assertRaisesRegex(integration.IntegrationError, "extra="):
                integration.verify_installation(repo, self.outputs)
            extra.unlink()
            empty = repo / integration.DELTA_ROOT / "unexpected-empty-directory"
            empty.mkdir()
            with self.assertRaisesRegex(
                integration.IntegrationError, "unexpected managed directory"
            ):
                integration.verify_installation(repo, self.outputs)
            empty.rmdir()
            target = repo / next(iter(sorted(self.outputs)))
            target.write_bytes(target.read_bytes() + b"drift")
            with self.assertRaisesRegex(
                integration.IntegrationError, "content drifted"
            ):
                integration.verify_installation(repo, self.outputs)

    def test_symlink_parent_never_escapes_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            escape = root / "escape"
            repo.mkdir()
            escape.mkdir()
            (repo / ".agents").symlink_to(escape, target_is_directory=True)
            with self.assertRaisesRegex(
                integration.IntegrationError, "unsafe anchored directory"
            ):
                integration.install_outputs(repo, self.outputs)
            self.assertEqual(list(escape.iterdir()), [])

    def test_anchored_reader_detects_parent_path_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            safe = repo / "safe"
            replacement = repo / "replacement"
            displaced = repo / "displaced"
            safe.mkdir()
            replacement.mkdir()
            (safe / "input.txt").write_bytes(b"bound")
            (replacement / "input.txt").write_bytes(b"replacement")
            original_read = integration.os.read
            swapped = False

            def swap_after_read(descriptor: int, size: int) -> bytes:
                nonlocal swapped
                payload = original_read(descriptor, size)
                if payload and not swapped:
                    safe.rename(displaced)
                    replacement.rename(safe)
                    swapped = True
                return payload

            with integration._repo_anchor(repo) as (_absolute, root_fd, _identity):
                with (
                    mock.patch.object(
                        integration.os, "read", side_effect=swap_after_read
                    ),
                    self.assertRaisesRegex(
                        integration.IntegrationError, "parent changed"
                    ),
                ):
                    integration._read_at(
                        root_fd, Path("safe/input.txt"), missing_ok=False
                    )
            self.assertTrue(swapped)
            self.assertEqual((displaced / "input.txt").read_bytes(), b"bound")
            self.assertEqual((safe / "input.txt").read_bytes(), b"replacement")

    def test_repository_path_swap_writes_only_to_pinned_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            pinned = root / "pinned"
            escape = root / "escape"
            repo.mkdir()
            escape.mkdir()
            original = integration._write_at
            swapped = False

            def swap_then_write(
                root_fd: int,
                relative: Path,
                data: bytes,
                mode: int = 0o644,
            ) -> None:
                nonlocal swapped
                if not swapped and integration.TRANSACTION_ROOT not in relative.parents:
                    repo.rename(pinned)
                    repo.symlink_to(escape, target_is_directory=True)
                    swapped = True
                original(root_fd, relative, data, mode)

            with mock.patch.object(
                integration,
                "_write_at",
                side_effect=swap_then_write,
            ):
                with self.assertRaisesRegex(
                    integration.IntegrationError, "pathname identity changed"
                ):
                    integration.install_outputs(repo, self.outputs)
            self.assertEqual(list(escape.iterdir()), [])

    def test_partial_or_dual_root_divergent_outputs_are_rejected(self) -> None:
        first = next(iter(self.outputs))
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(
                integration.IntegrationError, "inventory drifted"
            ):
                integration.install_outputs(
                    Path(temporary), {first: self.outputs[first]}
                )
        divergent = dict(self.outputs)
        name = integration.EXPECTED_SKILLS[0][1]
        divergent[Path(".agents/skills") / name / "SKILL.md"] += b"different"
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(
                integration.IntegrationError, "dual Skill roots"
            ):
                integration.install_outputs(Path(temporary), divergent)

    def test_run_validates_qualification_only_inside_exclusive_lock(self) -> None:
        active = False
        observations: list[bool] = []

        @integration.contextmanager
        def locked(_repo_root: Path):
            nonlocal active
            active = True
            try:
                yield
            finally:
                active = False

        def status(_repo_root: Path, _audit: integration.ArchiveAudit) -> str:
            observations.append(active)
            return "DECLARED_RUNTIME_UNQUALIFIED"

        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(
                integration, "audit_archive", return_value=audited_delta()
            ),
            mock.patch.object(integration, "_exclusive_lock", side_effect=locked),
            mock.patch.object(integration, "_receipt_status", side_effect=status),
        ):
            result = integration.run(
                integration.argparse.Namespace(
                    repo_root=Path(temporary),
                    archive=ARCHIVE,
                    audit=True,
                    install=False,
                    check=False,
                )
            )
        self.assertEqual(result["action"], "audit")
        self.assertEqual(observations, [True, True])


class DeltaReceiptValidationTests(unittest.TestCase):
    audit: ClassVar[integration.ArchiveAudit]

    @classmethod
    def setUpClass(cls) -> None:
        cls.audit = audited_delta()

    def _structured_result(
        self,
        *,
        sources: dict[str, tuple[str, list[str]]],
        start_directory: str,
        pattern: str,
    ) -> dict[str, object]:
        outcomes = []
        for source_path, (source_sha256, selectors) in sources.items():
            for selector in selectors:
                binding = {
                    "selector": selector,
                    "source_path": source_path,
                    "source_sha256": source_sha256,
                }
                outcomes.append(
                    {
                        **binding,
                        "selector_source_binding_sha256": "sha256:"
                        + integration._sha256(integration._canonical_bytes(binding)),
                        "status": "PASSED",
                        "duration_milliseconds": 0,
                    }
                )
        selected = len(outcomes)
        return {
            "schema_version": "1.0.0",
            "kind": "elmos.proof-harness.structured-unittest-results",
            "status": "PASS",
            "discovery": {
                "start_directory": start_directory,
                "pattern": pattern,
            },
            "totals": {
                "selected": selected,
                "passed": selected,
                "failed": 0,
                "errors": 0,
                "skipped": 0,
                "expected_failures": 0,
                "unexpected_successes": 0,
            },
            "outcomes": outcomes,
            "runner_output": "",
            "captured_stdout": "",
            "captured_stderr": "",
            "evidence_boundary": {
                "classification": "LOCAL_EXECUTED_SELF_ATTESTED",
                "external_evidence": "NOT_RUN",
                "independent_verification": "NOT_RUN",
                "certification": "NOT_CERTIFIED",
            },
        }

    def _raw(
        self, name: str, argv_tail: tuple[str, ...], stdout: object
    ) -> dict[str, object]:
        return {
            "schema_version": "1.0.0",
            "name": name,
            "argv": ["/usr/bin/python3", *argv_tail],
            "cwd": ".",
            "returncode": 0,
            "timed_out": False,
            "wall_clock_milliseconds": 1,
            "stdout": json.dumps(stdout, sort_keys=True),
            "stderr": "",
            "execution_environment": {
                "python": {},
                "os": {},
                "network": "LOOPBACK_PROXY_DENY",
                "external_evidence": "NOT_RUN",
                "independent_verification": "NOT_RUN",
                "certification": "NOT_CERTIFIED",
            },
        }

    def _qualified_repo(self, root: Path) -> dict[str, object]:
        engine_test_paths = tuple(
            sorted(
                (
                    *integration.REQUIRED_ENGINE_DELTA_TESTS,
                    *integration.OPTIONAL_ENGINE_DELTA_TESTS,
                )
            )
        )
        qualification_inputs = (
            *integration.STATIC_QUALIFICATION_INPUTS[:4],
            *engine_test_paths,
            integration.STATIC_QUALIFICATION_INPUTS[4],
        )
        for index, relative in enumerate(qualification_inputs):
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if relative == integration.ACCEPTANCE_BINDINGS_PATH:
                target.write_bytes((REPO_ROOT / relative).read_bytes())
            else:
                target.write_bytes(f"qualification-input-{index}\n".encode())
        delta_runtime = (
            root / integration.ENGINE_ROOT / "src/elmos_proof_harness/delta.py"
        )
        delta_runtime.parent.mkdir(parents=True, exist_ok=True)
        delta_runtime.write_bytes(b"# repository-owned delta runtime\n")

        inputs: dict[str, dict[str, int | str]] = {}
        for relative in qualification_inputs:
            payload = (root / relative).read_bytes()
            inputs[relative.as_posix()] = {
                "bytes": len(payload),
                "sha256": "sha256:" + integration._sha256(payload),
            }
        importer_test = integration.STATIC_QUALIFICATION_INPUTS[4].as_posix()
        acceptance_payload = (root / integration.ACCEPTANCE_BINDINGS_PATH).read_bytes()
        acceptance_bindings = integration._validate_acceptance_bindings(
            acceptance_payload,
            self.audit,
        )
        selectors_by_source: dict[str, list[str]] = {
            path.as_posix(): [] for path in engine_test_paths
        }
        for case in acceptance_bindings["cases"]:
            for selector in case["repository_test_selectors"]:
                source = (
                    integration.ENGINE_ROOT
                    / "tests"
                    / f"{selector.split('.', 1)[0]}.py"
                ).as_posix()
                if selector not in selectors_by_source[source]:
                    selectors_by_source[source].append(selector)
        for index, (source, selectors) in enumerate(selectors_by_source.items()):
            if not selectors:
                selectors.append(f"tests.DeltaSupport.test_required_source_{index}")
        importer_selectors = [
            f"tests.DeltaImporter.test_boundary_{index}" for index in range(12)
        ]
        engine_result = self._structured_result(
            sources={
                source: (str(inputs[source]["sha256"]), selectors)
                for source, selectors in selectors_by_source.items()
            },
            start_directory="engines/proof-driven-harness-engine/tests",
            pattern=integration.ENGINE_DELTA_TEST_PATTERN,
        )
        acceptance_outcomes = {
            str(outcome["selector"]): {
                "selector": str(outcome["selector"]),
                "source_path": str(outcome["source_path"]),
                "source_sha256": str(outcome["source_sha256"]),
            }
            for outcome in engine_result["outcomes"]
        }
        acceptance_receipt = integration._expected_acceptance_receipt(
            acceptance_bindings,
            acceptance_outcomes,
        )
        importer_result = self._structured_result(
            sources={
                importer_test: (
                    str(inputs[importer_test]["sha256"]),
                    importer_selectors,
                )
            },
            start_directory="tests/proof-driven-harness-v3",
            pattern="test_delta_integration.py",
        )
        raw_specs = (
            (
                "delta-engine-tests",
                "delta-engine-tests.json",
                (
                    "engines/proof-driven-harness-engine/tools/run_structured_unittest.py",
                    "--repo-root",
                    ".",
                    "--start-directory",
                    "engines/proof-driven-harness-engine/tests",
                    "--pattern",
                    integration.ENGINE_DELTA_TEST_PATTERN,
                ),
                engine_result,
            ),
            (
                "delta-importer-tests",
                "delta-importer-tests.json",
                (
                    "engines/proof-driven-harness-engine/tools/run_structured_unittest.py",
                    "--repo-root",
                    ".",
                    "--start-directory",
                    "tests/proof-driven-harness-v3",
                    "--pattern",
                    "test_delta_integration.py",
                ),
                importer_result,
            ),
            (
                "delta-installation-check",
                "delta-installation-check.json",
                (
                    "tooling/integrate_harness_runtime_assurance_delta.py",
                    "--repo-root",
                    ".",
                    "--check",
                ),
                {
                    "schema_version": "1.0.0",
                    "package": (
                        f"{integration.PACKAGE_NAME}@{integration.PACKAGE_VERSION}"
                    ),
                    "archive": {
                        "sha256": self.audit.archive_sha256,
                        "bytes": self.audit.archive_bytes,
                    },
                    "action": "check",
                    "installation": {"status": "PASS"},
                    "implementation_status": "DECLARED_RUNTIME_UNQUALIFIED",
                    "external_runtime_status": "NOT_RUN",
                    "certification_status": "NOT_CERTIFIED",
                },
            ),
        )
        raw_rows = []
        raw_root = root / integration.ENGINE_ROOT / "qualification/delta-v3.1/raw"
        raw_root.mkdir(parents=True)
        for name, filename, argv_tail, stdout in raw_specs:
            payload = _json_bytes(self._raw(name, argv_tail, stdout))
            (raw_root / filename).write_bytes(payload)
            raw_rows.append(
                {
                    "name": name,
                    "path": f"qualification/delta-v3.1/raw/{filename}",
                    "sha256": "sha256:" + integration._sha256(payload),
                    "returncode": 0,
                }
            )
        with integration._repo_anchor(root) as (_absolute, repo_fd, _identity):
            inventory = integration._engine_inventory_at(repo_fd)
        totals = {
            key: int(engine_result["totals"][key]) + int(importer_result["totals"][key])
            for key in (
                "selected",
                "passed",
                "failed",
                "errors",
                "skipped",
                "expected_failures",
                "unexpected_successes",
            )
        }
        receipt: dict[str, object] = {
            "schema_version": "1.0.0",
            "kind": "elmos.harness-runtime-assurance-delta.local-qualification",
            "package": f"{integration.PACKAGE_NAME}@{integration.PACKAGE_VERSION}",
            "base_package_version": integration.BASE_VERSION,
            "composite_version": integration.PACKAGE_VERSION,
            "archive_sha256": self.audit.archive_sha256,
            "archive_bytes": self.audit.archive_bytes,
            "engine": {
                "files": len(inventory),
                "tree_sha256": "sha256:"
                + integration._sha256(integration._canonical_bytes(inventory)),
                "inventory": inventory,
            },
            "inputs": inputs,
            "raw_logs": raw_rows,
            "tests": totals,
            "acceptance": acceptance_receipt,
            "install_roundtrip": "PASS",
            "adapter_profile_negotiation": "PASS",
            "postgresql17": "NOT_RUN",
            "opa": "NOT_RUN",
            "provider_runtime": "NOT_RUN",
            "remote_executor": "NOT_RUN",
            "target_environment_conformance": "NOT_RUN",
            "independent_verification": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
            "implementation_status": "LOCAL_EXECUTED_SELF_ATTESTED",
            "status": "PASS",
        }
        receipt_path = root / integration.RECEIPT_PATH
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_bytes(_json_bytes(receipt))
        return receipt

    def test_complete_digest_bound_receipt_promotes_local_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            self._qualified_repo(repo)
            self.assertEqual(
                integration._receipt_status(repo, self.audit),
                "LOCAL_EXECUTED_SELF_ATTESTED",
            )

    def test_acceptance_binding_tamper_and_omission_fail_closed(self) -> None:
        payload = (REPO_ROOT / integration.ACCEPTANCE_BINDINGS_PATH).read_bytes()
        binding = json.loads(payload)

        tampered = copy.deepcopy(binding)
        tampered["skills"][0]["source_acceptance"]["sha256"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(
            integration.IntegrationError,
            "acceptance source binding drifted",
        ):
            integration._validate_acceptance_bindings(
                _json_bytes(tampered),
                self.audit,
            )

        omitted = copy.deepcopy(binding)
        omitted["skills"].pop()
        with self.assertRaisesRegex(
            integration.IntegrationError,
            "acceptance skill inventory drifted",
        ):
            integration._validate_acceptance_bindings(
                _json_bytes(omitted),
                self.audit,
            )

    def test_acceptance_receipt_selector_drift_and_missing_input_fail_closed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            receipt = self._qualified_repo(repo)
            receipt["acceptance"]["case_results"][0]["repository_test_selectors"][0] = (
                "test_delta_skills.DeltaSkillsImplementationTests.test_missing"
            )
            (repo / integration.RECEIPT_PATH).write_bytes(_json_bytes(receipt))
            self.assertEqual(
                integration._receipt_status(repo, self.audit),
                "DECLARED_RUNTIME_UNQUALIFIED",
            )

        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            self._qualified_repo(repo)
            (repo / integration.ACCEPTANCE_BINDINGS_PATH).unlink()
            self.assertEqual(
                integration._receipt_status(repo, self.audit),
                "DECLARED_RUNTIME_UNQUALIFIED",
            )

    def test_engine_input_and_raw_log_tampering_all_fail_closed(self) -> None:
        targets = (
            integration.ENGINE_ROOT / "src/elmos_proof_harness/delta.py",
            integration.QUALIFICATION_INPUTS[2],
            integration.ENGINE_ROOT
            / "qualification/delta-v3.1/raw/delta-engine-tests.json",
        )
        for target in targets:
            with (
                self.subTest(target=target),
                tempfile.TemporaryDirectory() as temporary,
            ):
                repo = Path(temporary)
                self._qualified_repo(repo)
                path = repo / target
                path.write_bytes(path.read_bytes() + b"tampered")
                self.assertEqual(
                    integration._receipt_status(repo, self.audit),
                    "DECLARED_RUNTIME_UNQUALIFIED",
                )

    def test_overclaim_and_forged_test_counts_fail_closed(self) -> None:
        for field, value in (
            ("postgresql17", "PASS"),
            ("certification", "CERTIFIED"),
            ("tests", {"selected": 25, "passed": 25}),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                repo = Path(temporary)
                receipt = self._qualified_repo(repo)
                receipt[field] = value
                (repo / integration.RECEIPT_PATH).write_bytes(_json_bytes(receipt))
                self.assertEqual(
                    integration._receipt_status(repo, self.audit),
                    "DECLARED_RUNTIME_UNQUALIFIED",
                )

    def test_coherently_rehashed_installation_overclaim_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            receipt = self._qualified_repo(repo)
            raw_path = (
                repo
                / integration.ENGINE_ROOT
                / "qualification/delta-v3.1/raw/delta-installation-check.json"
            )
            raw = json.loads(raw_path.read_bytes())
            stdout = json.loads(raw["stdout"])
            stdout["external_runtime_status"] = "PASS"
            raw["stdout"] = json.dumps(stdout, sort_keys=True)
            raw_payload = _json_bytes(raw)
            raw_path.write_bytes(raw_payload)
            for row in receipt["raw_logs"]:
                if row["name"] == "delta-installation-check":
                    row["sha256"] = "sha256:" + integration._sha256(raw_payload)
            (repo / integration.RECEIPT_PATH).write_bytes(_json_bytes(receipt))
            self.assertEqual(
                integration._receipt_status(repo, self.audit),
                "DECLARED_RUNTIME_UNQUALIFIED",
            )

    def test_missing_malformed_and_symlink_receipts_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            repo.mkdir(exist_ok=True)
            self.assertEqual(
                integration._receipt_status(repo, self.audit),
                "DECLARED_RUNTIME_UNQUALIFIED",
            )

    def test_writable_or_hardlinked_evidence_fails_closed(self) -> None:
        targets = (
            integration.RECEIPT_PATH,
            integration.ENGINE_ROOT
            / "qualification/delta-v3.1/raw/delta-engine-tests.json",
        )
        for target in targets:
            with (
                self.subTest(target=target),
                tempfile.TemporaryDirectory() as temporary,
            ):
                repo = Path(temporary)
                self._qualified_repo(repo)
                (repo / target).chmod(0o666)
                self.assertEqual(
                    integration._receipt_status(repo, self.audit),
                    "DECLARED_RUNTIME_UNQUALIFIED",
                )

        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            self._qualified_repo(repo)
            receipt = repo / integration.RECEIPT_PATH
            receipt.with_name("receipt-alias.json").hardlink_to(receipt)
            self.assertEqual(
                integration._receipt_status(repo, self.audit),
                "DECLARED_RUNTIME_UNQUALIFIED",
            )
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            self._qualified_repo(repo)
            receipt = repo / integration.RECEIPT_PATH
            receipt.unlink()
            outside = repo / "outside.json"
            outside.write_bytes(b"{}\n")
            receipt.symlink_to(outside)
            self.assertEqual(
                integration._receipt_status(repo, self.audit),
                "DECLARED_RUNTIME_UNQUALIFIED",
            )


if __name__ == "__main__":
    unittest.main()
