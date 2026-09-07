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
        self.delta_engine_tests = tuple(
            sorted(
                (
                    *publisher.DELTA_REQUIRED_ENGINE_TESTS,
                    *(
                        path
                        for path in publisher.DELTA_OPTIONAL_ENGINE_TESTS
                        if (REPOSITORY_ROOT / path).is_file()
                    ),
                )
            )
        )
        self._materialize_inputs()
        self._write_raw_logs_and_receipt()

    def close(self) -> None:
        self.temporary.cleanup()

    def _materialize_inputs(self) -> None:
        sources = {
            publisher.ARCHIVE_RELATIVE,
            publisher.DELTA_ARCHIVE_RELATIVE,
            publisher.QUALIFIER_RELATIVE,
            publisher.DELTA_QUALIFIER_RELATIVE,
            publisher.STRUCTURED_RUNNER_RELATIVE,
            publisher.PUBLISHER_RELATIVE,
            publisher.PUBLISHER_TEST_RELATIVE,
            publisher.IMPORTER_RELATIVE,
            publisher.IMPORTER_TEST_RELATIVE,
            publisher.DELTA_IMPORTER_RELATIVE,
            publisher.DELTA_IMPORTER_TEST_RELATIVE,
            publisher.DELTA_ACCEPTANCE_BINDINGS_RELATIVE,
            *self.delta_engine_tests,
        }
        for relative in sorted(sources):
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
                (
                    "test_publish_verification_pack."
                    "ProofDrivenHarnessVerificationPackPublisherTests."
                    "test_delta_acceptance_binding_tamper_and_omission_fail_closed"
                ),
                (
                    "test_publish_verification_pack."
                    "ProofDrivenHarnessVerificationPackPublisherTests."
                    "test_delta_acceptance_receipt_selector_drift_fails_closed"
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
        python_digest = (
            "sha256:" + hashlib.sha256(python_executable.read_bytes()).hexdigest()
        )
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
                        "sha256": "sha256:" + hashlib.sha256(tool_payload).hexdigest(),
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
        self._write_delta_raw_logs_and_receipt(records)

    def _write_delta_raw_logs_and_receipt(
        self, records: tuple[dict[str, object], ...]
    ) -> None:
        raw_references: list[dict[str, object]] = []
        acceptance_payload = (
            self.root / publisher.DELTA_ACCEPTANCE_BINDINGS_RELATIVE
        ).read_bytes()
        acceptance_bindings = publisher._validate_delta_acceptance_bindings(
            acceptance_payload,
            (self.root / publisher.DELTA_ARCHIVE_RELATIVE).read_bytes(),
        )
        delta_engine_outcomes: list[dict[str, object]] = []
        aggregate = {
            "selected": 0,
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "expected_failures": 0,
            "unexpected_successes": 0,
        }
        for raw_path, fixed_argv in publisher.DELTA_RAW_LOG_COMMANDS.items():
            if raw_path.endswith("-tests.json"):
                source_relatives = (
                    self.delta_engine_tests
                    if raw_path.endswith("delta-engine-tests.json")
                    else (publisher.DELTA_IMPORTER_TEST_RELATIVE,)
                )
                outcomes: list[dict[str, object]] = []
                selectors_by_source: dict[Path, list[str]] = {
                    path: [] for path in source_relatives
                }
                if raw_path.endswith("delta-engine-tests.json"):
                    for case in acceptance_bindings["cases"]:
                        for selector in case["repository_test_selectors"]:
                            source_relative = (
                                publisher.ENGINE_ROOT
                                / "tests"
                                / f"{selector.split('.', 1)[0]}.py"
                            )
                            if selector not in selectors_by_source[source_relative]:
                                selectors_by_source[source_relative].append(selector)
                else:
                    selectors_by_source[source_relatives[0]] = [
                        f"test_delta_integration.DeltaImporter.test_boundary_{index}"
                        for index in range(13)
                    ]
                for source_index, source_relative in enumerate(source_relatives):
                    if not selectors_by_source[source_relative]:
                        selectors_by_source[source_relative].append(
                            f"{source_relative.stem}.SyntheticDelta."
                            f"test_required_source_{source_index:02d}"
                        )
                    source_payload = (self.root / source_relative).read_bytes()
                    source_digest = (
                        "sha256:" + hashlib.sha256(source_payload).hexdigest()
                    )
                    for selector in selectors_by_source[source_relative]:
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
                if raw_path.endswith("delta-engine-tests.json"):
                    delta_engine_outcomes = outcomes
                totals = {
                    **{key: 0 for key in aggregate},
                    "selected": len(outcomes),
                    "passed": len(outcomes),
                }
                for key in aggregate:
                    aggregate[key] += totals[key]
                structured = {
                    "schema_version": "1.0.0",
                    "kind": "elmos.proof-harness.structured-unittest-results",
                    "status": "PASS",
                    "discovery": {
                        "start_directory": fixed_argv[4],
                        "pattern": fixed_argv[6],
                    },
                    "totals": totals,
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
            else:
                stdout = json.dumps(
                    {
                        "action": "check",
                        "package": (
                            f"{publisher.DELTA_PACKAGE_NAME}@"
                            f"{publisher.DELTA_PACKAGE_VERSION}"
                        ),
                        "archive": {
                            "sha256": publisher.DELTA_ARCHIVE_SHA256,
                            "bytes": publisher.DELTA_ARCHIVE_BYTES,
                        },
                        "implementation_status": "LOCAL_EXECUTED_SELF_ATTESTED",
                        "external_runtime_status": "NOT_RUN",
                        "certification_status": "NOT_CERTIFIED",
                        "installation": {"status": "PASS"},
                    },
                    sort_keys=True,
                )
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
                    "python": {
                        "implementation": platform.python_implementation(),
                        "version": platform.python_version(),
                        "executable": sys.executable,
                    },
                    "os": {
                        "system": platform.system() or "synthetic",
                        "release": platform.release() or "synthetic",
                        "machine": platform.machine() or "synthetic",
                    },
                    "network": "LOOPBACK_PROXY_DENY",
                    "external_evidence": "NOT_RUN",
                    "independent_verification": "NOT_RUN",
                    "certification": "NOT_CERTIFIED",
                },
            }
            payload = publisher.json_bytes(record)
            _write(self.root / publisher.ENGINE_ROOT / raw_path, payload)
            raw_references.append(
                {
                    "name": record["name"],
                    "path": raw_path,
                    "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
                    "returncode": 0,
                }
            )

        normalized_records = [
            {
                "path": item["path"],
                "bytes": item["bytes"],
                "sha256": "sha256:" + str(item["sha256"]),
            }
            for item in records
        ]
        inputs: dict[str, dict[str, object]] = {}
        for relative in (
            publisher.DELTA_QUALIFIER_RELATIVE,
            publisher.STRUCTURED_RUNNER_RELATIVE,
            publisher.DELTA_IMPORTER_RELATIVE,
            publisher.DELTA_ACCEPTANCE_BINDINGS_RELATIVE,
            *self.delta_engine_tests,
            publisher.DELTA_IMPORTER_TEST_RELATIVE,
        ):
            payload = (self.root / relative).read_bytes()
            inputs[relative.as_posix()] = {
                "bytes": len(payload),
                "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
            }
        receipt = {
            "schema_version": "1.0.0",
            "kind": "elmos.harness-runtime-assurance-delta.local-qualification",
            "package": (
                f"{publisher.DELTA_PACKAGE_NAME}@{publisher.DELTA_PACKAGE_VERSION}"
            ),
            "base_package_version": publisher.PACKAGE_VERSION,
            "composite_version": publisher.COMPOSITE_VERSION,
            "archive_sha256": publisher.DELTA_ARCHIVE_SHA256,
            "archive_bytes": publisher.DELTA_ARCHIVE_BYTES,
            "engine": {
                "files": len(normalized_records),
                "tree_sha256": "sha256:"
                + hashlib.sha256(
                    publisher.canonical_bytes(normalized_records)
                ).hexdigest(),
                "inventory": normalized_records,
            },
            "inputs": inputs,
            "raw_logs": raw_references,
            "tests": aggregate,
            "acceptance": publisher._expected_delta_acceptance_receipt(
                acceptance_bindings,
                delta_engine_outcomes,
            ),
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
        _write(
            self.root / publisher.DELTA_RECEIPT_RELATIVE,
            publisher.json_bytes(receipt),
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
                str(REPOSITORY_ROOT / "scripts/batch35/validate_verification_pack.py"),
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

    def test_publication_lock_accepts_canonical_system_temp_alias(self) -> None:
        with tempfile.TemporaryDirectory(prefix="proof-pack-lock-target-") as temporary:
            alias = self.root / "temporary-alias"
            os.symlink(temporary, alias, target_is_directory=True)
            with mock.patch.object(
                publisher.tempfile,
                "gettempdir",
                return_value=str(alias),
            ):
                with publisher.publication_lock(self.root):
                    pass

    def test_publication_lock_rejects_linked_lock_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="proof-pack-lock-target-") as temporary:
            temporary_root = Path(temporary)
            lock_key = hashlib.sha256(
                os.fsencode(Path(os.path.abspath(self.root)))
            ).hexdigest()[:32]
            lock_path = temporary_root / f"elmos-proof-harness-pack-{lock_key}.lock"
            os.symlink(self.root / "escape-lock", lock_path)
            with mock.patch.object(
                publisher.tempfile,
                "gettempdir",
                return_value=str(temporary_root),
            ):
                with self.assertRaisesRegex(
                    publisher.VerificationPackError,
                    "cannot safely open publication lock",
                ):
                    with publisher.publication_lock(self.root):
                        pass

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
        certification = _json(certified_copy / "certification/certification.json")
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
        certified_result = _json(certified_copy / "certification/gate-result.json")
        self.assertTrue(certified_result["certification_requested"])
        self.assertEqual(certified_result["certification_decision"], "BLOCKED")
        self.assertTrue(certified_result["failures"])

    def test_every_discovered_delta_test_is_input_and_repository_bound(self) -> None:
        qualification = publisher.validate_qualification(self.root)
        expected_tests = set(self.fixture.delta_engine_tests)
        receipt_inputs = {
            Path(*Path(value).parts)
            for value in qualification.delta_receipt["inputs"]
            if Path(value).parent == publisher.ENGINE_ROOT / "tests"
            and Path(value).match(publisher.DELTA_ENGINE_TEST_PATTERN)
        }
        self.assertEqual(receipt_inputs, expected_tests)

        outputs = publisher.build_pack_outputs(self.root, qualification)
        repository_binding = json.loads(
            outputs[Path("certification/repository-binding.json")]
        )
        bindings_by_path = {
            Path(binding["path"]): binding
            for binding in repository_binding["repository_bindings"]
        }
        for path in expected_tests:
            with self.subTest(path=path):
                suffix = path.stem.removeprefix("test_delta_").replace("_", "-")
                self.assertEqual(
                    bindings_by_path[path]["role"],
                    f"delta-runtime-test-{suffix}",
                )
                self.assertEqual(
                    bindings_by_path[path]["sha256"],
                    "sha256:"
                    + hashlib.sha256((self.root / path).read_bytes()).hexdigest(),
                )

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

    def test_missing_delta_receipt_fails_closed(self) -> None:
        (self.root / publisher.DELTA_RECEIPT_RELATIVE).unlink()
        with self.assertRaisesRegex(
            publisher.VerificationPackError,
            "missing anchored file",
        ):
            publisher.publish_pack(self.root)
        self.assertFalse(self.pack.exists())

    def test_tampered_delta_receipt_fails_closed(self) -> None:
        receipt_path = self.root / publisher.DELTA_RECEIPT_RELATIVE
        receipt = _json(receipt_path)
        receipt["provider_runtime"] = "PASS"
        _write(receipt_path, publisher.json_bytes(receipt))
        with self.assertRaisesRegex(
            publisher.VerificationPackError,
            "delta qualification identity/boundary",
        ):
            publisher.publish_pack(self.root)
        self.assertFalse(self.pack.exists())

    def test_delta_archive_drift_fails_closed(self) -> None:
        archive_path = self.root / publisher.DELTA_ARCHIVE_RELATIVE
        archive = archive_path.read_bytes()
        _write(archive_path, bytes([archive[0] ^ 0x01]) + archive[1:])
        with self.assertRaisesRegex(
            publisher.VerificationPackError,
            "delta source archive identity",
        ):
            publisher.publish_pack(self.root)
        self.assertFalse(self.pack.exists())

    def test_delta_acceptance_binding_tamper_and_omission_fail_closed(self) -> None:
        binding_path = self.root / publisher.DELTA_ACCEPTANCE_BINDINGS_RELATIVE
        archive_payload = (self.root / publisher.DELTA_ARCHIVE_RELATIVE).read_bytes()
        binding = _json(binding_path)

        tampered = json.loads(json.dumps(binding))
        tampered["skills"][0]["source_acceptance"]["sha256"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(
            publisher.VerificationPackError,
            "acceptance source binding drifted",
        ):
            publisher._validate_delta_acceptance_bindings(
                publisher.json_bytes(tampered),
                archive_payload,
            )

        omitted = json.loads(json.dumps(binding))
        omitted["skills"].pop()
        with self.assertRaisesRegex(
            publisher.VerificationPackError,
            "acceptance skill inventory drifted",
        ):
            publisher._validate_delta_acceptance_bindings(
                publisher.json_bytes(omitted),
                archive_payload,
            )

    def test_delta_acceptance_receipt_selector_drift_fails_closed(self) -> None:
        receipt_path = self.root / publisher.DELTA_RECEIPT_RELATIVE
        receipt = _json(receipt_path)
        receipt["acceptance"]["case_results"][0]["repository_test_selectors"][0] = (
            "test_delta_skills.DeltaSkillsImplementationTests.test_missing_selector"
        )
        _write(receipt_path, publisher.json_bytes(receipt))
        with self.assertRaisesRegex(
            publisher.VerificationPackError,
            "acceptance receipt evidence drifted",
        ):
            publisher.publish_pack(self.root)
        self.assertFalse(self.pack.exists())


if __name__ == "__main__":
    unittest.main()
