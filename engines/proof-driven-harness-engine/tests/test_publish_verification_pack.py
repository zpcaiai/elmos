from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PUBLISHER_PATH = (
    REPOSITORY_ROOT
    / "engines/proof-driven-harness-engine/tools/publish_verification_pack.py"
)
SPEC = importlib.util.spec_from_file_location(
    "proof_harness_verification_pack_publisher",
    PUBLISHER_PATH,
)
assert SPEC is not None and SPEC.loader is not None
publisher = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = publisher
SPEC.loader.exec_module(publisher)
# Batch 35 validators have a repository-owned JSON Schema fallback so the
# qualification suite remains deterministic when its network-denied runner
# cannot resolve third-party wheels.
BATCH35_PYTHON = [sys.executable]


def _write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"expected JSON object: {path}")
    return value


class SyntheticQualificationRepository:
    """Exact receipt fixture; no source-package executable is ever invoked."""

    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="proof-harness-v3-pack-test-"
        )
        self.root = Path(self.temporary.name)
        self._materialize_inputs()
        self._write_raw_logs_and_receipt()

    def close(self) -> None:
        self.temporary.cleanup()

    def _materialize_inputs(self) -> None:
        sources = (
            publisher.ARCHIVE_RELATIVE,
            publisher.QUALIFIER_RELATIVE,
            publisher.STRUCTURED_RUNNER_RELATIVE,
            publisher.PUBLISHER_RELATIVE,
            publisher.PUBLISHER_TEST_RELATIVE,
            publisher.IMPORTER_RELATIVE,
            publisher.IMPORTER_TEST_RELATIVE,
        )
        for relative in sources:
            _copy(REPOSITORY_ROOT / relative, self.root / relative)

    def _write_raw_logs_and_receipt(self) -> None:
        raw_references: list[dict[str, object]] = []
        selectors = {
            "qualification/raw/engine-tests.json": [
                (
                    "test_publish_verification_pack."
                    "ProofDrivenHarnessVerificationPackPublisherTests."
                    "test_tampered_receipt_fails_closed"
                ),
                (
                    "test_publish_verification_pack."
                    "ProofDrivenHarnessVerificationPackPublisherTests."
                    "test_symlink_output_fails_closed_without_escape"
                ),
            ],
            "qualification/raw/package-integration-tests.json": [
                (
                    "test_integration.ProofDrivenHarnessArchiveTests."
                    "test_archive_audit_uses_one_in_memory_snapshot_and_detects_path_swap"
                ),
                (
                    "test_integration.ProofDrivenHarnessArchiveTests."
                    "test_traversal_member_fails_closed"
                ),
                (
                    "test_integration.ProofDrivenHarnessArchiveTests."
                    "test_unicode_casefold_collision_fails_closed"
                ),
                (
                    "test_integration.ProofDrivenHarnessArchiveTests."
                    "test_symlink_encryption_and_ratio_fail_closed"
                ),
                (
                    "test_integration.ProofDrivenHarnessInstallationTests."
                    "test_dirfd_publication_rejects_symlink_parent"
                ),
                (
                    "test_integration.ProofDrivenHarnessInstallationTests."
                    "test_dirfd_publication_detects_parent_swap_during_rename"
                ),
                (
                    "test_integration.ProofDrivenHarnessQualificationTests."
                    "test_only_exact_digest_bound_receipt_promotes_status"
                ),
            ],
        }
        totals = {
            "selected": 0,
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "expected_failures": 0,
            "unexpected_successes": 0,
        }
        python_executable = Path(sys.executable).resolve(strict=True)
        python_digest = "sha256:" + hashlib.sha256(
            python_executable.read_bytes()
        ).hexdigest()
        for raw_path, fixed_argv in publisher.RAW_LOG_COMMANDS.items():
            selected = selectors.get(raw_path, [])
            structured: dict[str, object] | None = None
            if selected:
                if "engine-tests" in raw_path:
                    source_relative = publisher.PUBLISHER_TEST_RELATIVE
                else:
                    source_relative = publisher.IMPORTER_TEST_RELATIVE
                source_payload = (self.root / source_relative).read_bytes()
                source_digest = "sha256:" + hashlib.sha256(source_payload).hexdigest()
                outcomes: list[dict[str, object]] = []
                for selector in selected:
                    binding = {
                        "selector": selector,
                        "source_path": source_relative.as_posix(),
                        "source_sha256": source_digest,
                    }
                    outcomes.append(
                        {
                            **binding,
                            "selector_source_binding_sha256": "sha256:"
                            + hashlib.sha256(
                                publisher.canonical_bytes(binding)
                            ).hexdigest(),
                            "status": "PASSED",
                            "duration_milliseconds": 1,
                        }
                    )
                command_totals = {
                    **{key: 0 for key in totals},
                    "selected": len(outcomes),
                    "passed": len(outcomes),
                }
                for key in totals:
                    totals[key] += command_totals[key]
                structured = {
                    "schema_version": "1.0.0",
                    "kind": "elmos.proof-harness.structured-unittest-results",
                    "status": "PASS",
                    "discovery": {
                        "start_directory": fixed_argv[4],
                        "pattern": fixed_argv[6],
                    },
                    "totals": command_totals,
                    "outcomes": outcomes,
                    "runner_output": "synthetic fixture; not qualification evidence",
                    "captured_stdout": "",
                    "captured_stderr": "",
                    "evidence_boundary": {
                        "classification": "LOCAL_EXECUTED_SELF_ATTESTED",
                        "external_evidence": "NOT_RUN",
                        "independent_verification": "NOT_RUN",
                        "certification": "NOT_CERTIFIED",
                    },
                }
                stdout = json.dumps(structured, sort_keys=True)
                tool_relative = publisher.STRUCTURED_RUNNER_RELATIVE
            else:
                stdout = '{"status":"PASS","mode":"check"}\n'
                tool_relative = publisher.IMPORTER_RELATIVE
            tool_payload = (self.root / tool_relative).read_bytes()
            record = {
                "schema_version": "1.0.0",
                "name": Path(raw_path).stem,
                "argv": [sys.executable, *fixed_argv],
                "cwd": ".",
                "returncode": 0,
                "timed_out": False,
                "wall_clock_milliseconds": 1,
                "stdout": stdout,
                "stderr": "",
                "execution_environment": {
                    "schema_version": "1.0.0",
                    "os": {
                        "system": platform.system() or "synthetic",
                        "release": platform.release() or "synthetic",
                        "version": platform.version() or "synthetic",
                        "machine": platform.machine() or "synthetic",
                    },
                    "python": {
                        "implementation": platform.python_implementation(),
                        "version": platform.python_version(),
                        "cache_tag": sys.implementation.cache_tag,
                        "executable": str(python_executable),
                        "executable_sha256": python_digest,
                    },
                    "tool": {
                        "path": tool_relative.as_posix(),
                        "version": publisher.PACKAGE_VERSION,
                        "sha256": "sha256:"
                        + hashlib.sha256(tool_payload).hexdigest(),
                    },
                    "packages": {
                        "psycopg": "NOT_INSTALLED",
                        "psycopg-binary": "NOT_INSTALLED",
                    },
                    "postgresql": {
                        "status": "NOT_APPLICABLE_TO_COMMAND",
                        "required_version": "17.5",
                    },
                    "evidence_boundary": {
                        "classification": "LOCAL_EXECUTED_SELF_ATTESTED",
                        "external_evidence": "NOT_RUN",
                        "independent_verification": "NOT_RUN",
                        "certification": "NOT_CERTIFIED",
                    },
                },
            }
            payload = publisher.canonical_bytes(record) + b"\n"
            repository_path = publisher.ENGINE_ROOT / Path(raw_path)
            _write(self.root / repository_path, payload)
            raw_references.append(
                {
                    "path": raw_path,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "bytes": len(payload),
                }
            )

        with publisher.repository_anchor(self.root) as (
            absolute,
            root_fd,
            root_identity,
        ):
            records = publisher.engine_inventory_at(root_fd)
            publisher.assert_repository_anchor(absolute, root_identity)
        qualifier = (self.root / publisher.QUALIFIER_RELATIVE).read_bytes()
        receipt = {
            "schema_version": "1.1.0",
            "kind": "elmos.proof-driven-harness-v3.local-qualification",
            "status": "PASS",
            "package": {
                "name": publisher.PACKAGE_NAME,
                "version": publisher.PACKAGE_VERSION,
                "archive_sha256": publisher.ARCHIVE_SHA256,
            },
            "engine": {
                "root": publisher.ENGINE_ROOT.as_posix(),
                "tree_sha256": hashlib.sha256(
                    publisher.canonical_bytes(list(records))
                ).hexdigest(),
                "files": list(records),
                "skill_count": len(publisher.SKILL_NAMES),
                "skill_names_sha256": hashlib.sha256(
                    publisher.canonical_bytes(list(publisher.SKILL_NAMES))
                ).hexdigest(),
                "component_count": len(publisher.COMPONENT_IDS),
                "component_ids_sha256": hashlib.sha256(
                    publisher.canonical_bytes(list(publisher.COMPONENT_IDS))
                ).hexdigest(),
            },
            "tests": {
                "status": "PASS",
                **totals,
                "raw_logs": raw_references,
            },
            "postgresql17": {
                "status": "NOT_RUN",
                "required_postgresql_version": "17.5",
                "required_psycopg_version": "3.2.13",
                "raw_log": None,
                "reason": "Synthetic publisher fixture does not execute PostgreSQL.",
            },
            "qualifier": {
                "path": publisher.QUALIFIER_RELATIVE.as_posix(),
                "sha256": hashlib.sha256(qualifier).hexdigest(),
            },
        }
        _write(
            self.root / publisher.RECEIPT_RELATIVE,
            publisher.canonical_bytes(receipt) + b"\n",
        )


class ProofDrivenHarnessVerificationPackPublisherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = SyntheticQualificationRepository()
        self.addCleanup(self.fixture.close)

    @property
    def root(self) -> Path:
        return self.fixture.root

    @property
    def pack(self) -> Path:
        return self.root / publisher.PACK_RELATIVE

    def _pack_bytes(self) -> dict[str, bytes]:
        return {
            path.relative_to(self.pack).as_posix(): path.read_bytes()
            for path in sorted(self.pack.rglob("*"))
            if path.is_file()
            and Path(path.relative_to(self.pack).as_posix())
            not in publisher.GATE_OUTPUTS
        }

    def _run_validator(self, pack: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                *BATCH35_PYTHON,
                str(
                    REPOSITORY_ROOT
                    / "scripts/batch35/validate_verification_pack.py"
                ),
                str(pack),
                "--repository-root",
                str(self.root),
            ],
            cwd=REPOSITORY_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def _run_gate(self, pack: Path) -> subprocess.CompletedProcess[str]:
        batch35 = REPOSITORY_ROOT / "scripts/batch35"
        program = (
            "from pathlib import Path; import sys; "
            f"sys.path.insert(0, {str(batch35)!r}); "
            "import run_verification_gate as gate; "
            "pack=Path(sys.argv[1]); root=Path(sys.argv[2]); "
            "sys.argv=['run_verification_gate.py', str(pack)]; "
            "raise SystemExit(gate.main(root))"
        )
        return subprocess.run(
            [*BATCH35_PYTHON, "-c", program, str(pack), str(self.root)],
            cwd=REPOSITORY_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_deterministic_generation_and_batch35_structural_validation(
        self,
    ) -> None:
        qualification = publisher.validate_qualification(self.root)
        first = publisher.build_pack_outputs(self.root, qualification)
        second = publisher.build_pack_outputs(self.root, qualification)
        self.assertEqual(first, second)

        result = publisher.publish_pack(self.root)
        self.assertEqual(result["certification_decision"], "NOT_CERTIFIED")
        self.assertEqual(result["certification_readiness"], "BLOCKED")
        published_once = self._pack_bytes()
        publisher.publish_pack(self.root)
        self.assertEqual(published_once, self._pack_bytes())

        validated = self._run_validator(self.pack)
        self.assertEqual(
            validated.returncode,
            0,
            msg=f"stdout={validated.stdout}\nstderr={validated.stderr}",
        )
        canonical_gate = self._run_gate(self.pack)
        self.assertEqual(
            canonical_gate.returncode,
            0,
            msg=f"stdout={canonical_gate.stdout}\nstderr={canonical_gate.stderr}",
        )
        gate_result = _json(self.pack / "certification/gate-result.json")
        self.assertEqual(gate_result["certification_decision"], "NOT_CERTIFIED")
        self.assertEqual(gate_result["certification_readiness"], "BLOCKED")
        self.assertFalse(gate_result["certification_requested"])
        self.assertEqual(publisher.check_pack(self.root)["status"], "PASS")

        certified_copy = self.root / "certified-request-negative"
        shutil.copytree(self.pack, certified_copy)
        manifest = _json(certified_copy / "pack.json")
        certification = _json(
            certified_copy / "certification/certification.json"
        )
        manifest["status"] = "certified"
        certification["status"] = "certified"
        (certified_copy / "pack.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (certified_copy / "certification/certification.json").write_text(
            json.dumps(certification, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        certified_gate = self._run_gate(certified_copy)
        self.assertNotEqual(certified_gate.returncode, 0)
        certified_result = _json(
            certified_copy / "certification/gate-result.json"
        )
        self.assertTrue(certified_result["certification_requested"])
        self.assertEqual(certified_result["certification_decision"], "BLOCKED")
        self.assertTrue(certified_result["failures"])

    def test_tampered_receipt_fails_closed(self) -> None:
        receipt_path = self.root / publisher.RECEIPT_RELATIVE
        receipt = _json(receipt_path)
        receipt["status"] = "FAILED"
        _write(receipt_path, publisher.canonical_bytes(receipt) + b"\n")
        with self.assertRaisesRegex(
            publisher.VerificationPackError,
            "receipt identity/status",
        ):
            publisher.publish_pack(self.root)
        self.assertFalse(self.pack.exists())

    def test_symlink_output_fails_closed_without_escape(self) -> None:
        escape = self.root / "escape"
        escape.mkdir()
        self.pack.parent.mkdir(parents=True)
        os.symlink(escape, self.pack, target_is_directory=True)
        with self.assertRaisesRegex(
            publisher.VerificationPackError,
            "linked or non-directory",
        ):
            publisher.publish_pack(self.root)
        self.assertTrue(self.pack.is_symlink())
        self.assertEqual(list(escape.iterdir()), [])

    def test_missing_receipt_fails_closed(self) -> None:
        (self.root / publisher.RECEIPT_RELATIVE).unlink()
        with self.assertRaisesRegex(
            publisher.VerificationPackError,
            "missing anchored file",
        ):
            publisher.publish_pack(self.root)
        self.assertFalse(self.pack.exists())

    def test_publication_lock_accepts_canonical_system_temp_alias(self) -> None:
        alias = self.root / "tmp-alias"
        alias.symlink_to(Path(tempfile.gettempdir()), target_is_directory=True)
        with mock.patch.object(
            publisher.tempfile, "gettempdir", return_value=str(alias)
        ):
            with publisher.publication_lock(self.root):
                pass

    def test_publication_lock_rejects_non_sticky_world_writable_directory(
        self,
    ) -> None:
        unsafe = self.root / "unsafe-temp"
        unsafe.mkdir(mode=0o777)
        unsafe.chmod(0o777)
        with mock.patch.object(
            publisher.tempfile, "gettempdir", return_value=str(unsafe)
        ):
            with self.assertRaisesRegex(
                publisher.VerificationPackError,
                "stable, owned, safe directory",
            ):
                with publisher.publication_lock(self.root):
                    pass


if __name__ == "__main__":
    unittest.main()
