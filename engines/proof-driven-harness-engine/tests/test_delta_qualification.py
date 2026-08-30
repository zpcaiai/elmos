from __future__ import annotations

from collections.abc import Mapping, Sequence
import copy
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
from types import ModuleType
from typing import ClassVar, cast
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parents[1]
TOOL = ROOT / "tools" / "qualify_delta.py"


def load_tool() -> ModuleType:
    specification = importlib.util.spec_from_file_location("qualify_delta", TOOL)
    if specification is None or specification.loader is None:
        raise RuntimeError("delta qualifier could not be loaded")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


class DeltaQualificationTests(unittest.TestCase):
    tool: ClassVar[ModuleType]

    @classmethod
    def setUpClass(cls) -> None:
        cls.tool = load_tool()

    def _structured(
        self,
        totals: Mapping[str, object],
        outcomes: Sequence[dict[str, object]],
    ) -> dict[str, object]:
        return {
            "schema_version": "1.0.0",
            "kind": "elmos.proof-harness.structured-unittest-results",
            "status": "PASS",
            "discovery": {
                "start_directory": "tests",
                "pattern": "test_delta_*.py",
            },
            "totals": dict(totals),
            "outcomes": list(outcomes),
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

    def _passing_outcome(
        self, selector: str, source: str, digest: str
    ) -> dict[str, object]:
        binding = {
            "selector": selector,
            "source_path": source,
            "source_sha256": digest,
        }
        return {
            **binding,
            "selector_source_binding_sha256": "sha256:"
            + self.tool.sha256(self.tool.canonical_bytes(binding)),
            "status": "PASSED",
            "duration_milliseconds": 0,
        }

    def _acceptance_payloads(self) -> tuple[bytes, bytes]:
        return (
            (REPOSITORY_ROOT / self.tool.ACCEPTANCE_BINDINGS_RELATIVE).read_bytes(),
            (REPOSITORY_ROOT / self.tool.ARCHIVE_RELATIVE).read_bytes(),
        )

    def test_repo_input_reader_is_rooted_and_no_follow(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            (root / "safe").mkdir()
            (root / "safe" / "input.txt").write_bytes(b"bound")
            payload, metadata = self.tool._safe_repo_bytes(root, Path("safe/input.txt"))
            self.assertEqual(payload, b"bound")
            self.assertTrue(stat.S_ISREG(metadata.st_mode))
            (root / "linked.txt").symlink_to(root / "safe" / "input.txt")
            with self.assertRaises(self.tool.QualificationError):
                self.tool._safe_repo_bytes(root, Path("linked.txt"))
            with self.assertRaises(self.tool.QualificationError):
                self.tool._safe_repo_bytes(root, Path("../escape"))

    def test_repo_input_reader_detects_parent_path_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            safe = root / "safe"
            replacement = root / "replacement"
            displaced = root / "displaced"
            safe.mkdir()
            replacement.mkdir()
            (safe / "input.txt").write_bytes(b"bound")
            (replacement / "input.txt").write_bytes(b"replacement")
            original_read = self.tool.os.read
            swapped = False

            def swap_after_read(descriptor: int, size: int) -> bytes:
                nonlocal swapped
                payload = cast(bytes, original_read(descriptor, size))
                if payload and not swapped:
                    safe.rename(displaced)
                    replacement.rename(safe)
                    swapped = True
                return payload

            with (
                patch.object(self.tool.os, "read", side_effect=swap_after_read),
                self.assertRaisesRegex(
                    self.tool.QualificationError, "directory binding changed"
                ),
            ):
                self.tool._safe_repo_bytes(root, Path("safe/input.txt"))
            self.assertTrue(swapped)
            self.assertEqual((displaced / "input.txt").read_bytes(), b"bound")
            self.assertEqual((safe / "input.txt").read_bytes(), b"replacement")

    def test_atomic_output_replaces_regular_file_and_rejects_link(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as value:
            root = Path(value)
            target = root / "nested" / "receipt.json"
            self.tool._atomic_write(target, b"one")
            self.tool._atomic_write(target, b"two")
            self.assertEqual(target.read_bytes(), b"two")
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            outside = root / "outside"
            outside.write_bytes(b"outside")
            linked = root / "linked"
            linked.symlink_to(outside)
            with self.assertRaises(self.tool.QualificationError):
                self.tool._atomic_write(linked, b"forbidden")
            self.assertEqual(outside.read_bytes(), b"outside")

            canary = root / "must-survive.txt"
            canary.write_bytes(b"preserved")
            with self.assertRaisesRegex(
                self.tool.QualificationError, "current directory"
            ):
                self.tool._atomic_write(Path(), b"forbidden")
            with self.assertRaises(self.tool.QualificationError):
                self.tool._atomic_write(root, b"forbidden")
            self.assertEqual(canary.read_bytes(), b"preserved")

    def test_exclusive_lock_rejects_pathname_inode_replacement(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as value:
            repo = Path(value)
            lock_path = repo / "delta.lock"
            original_flock = self.tool.fcntl.flock
            replaced = False

            def replace_after_lock(descriptor: int, operation: int) -> None:
                nonlocal replaced
                original_flock(descriptor, operation)
                lock_path.unlink()
                lock_path.write_bytes(b"replacement")
                replaced = True

            entered = False
            with (
                patch.object(self.tool, "_lock_path", return_value=lock_path),
                patch.object(self.tool.fcntl, "flock", side_effect=replace_after_lock),
                self.assertRaisesRegex(self.tool.QualificationError, "binding"),
            ):
                with self.tool._exclusive_lock(repo):
                    entered = True
            self.assertTrue(replaced)
            self.assertFalse(entered)

    def test_command_output_json_is_strict(self) -> None:
        self.assertEqual(
            self.tool._strict_json_text('{"status":"PASS"}'), {"status": "PASS"}
        )
        with self.assertRaisesRegex(self.tool.QualificationError, "duplicate JSON"):
            self.tool._strict_json_text('{"status":"FAIL","status":"PASS"}')
        with self.assertRaisesRegex(self.tool.QualificationError, "non-finite"):
            self.tool._strict_json_text('{"tests":NaN}')

    def test_engine_inventory_is_bounded_and_excludes_prior_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            engine = Path(value)
            runtime = engine / "src" / "elmos_proof_harness" / "delta.py"
            runtime.parent.mkdir(parents=True)
            runtime.write_bytes(b"runtime")
            receipt = engine / "qualification" / "delta-v3.1" / "receipt.json"
            receipt.parent.mkdir(parents=True)
            receipt.write_bytes(b"old")
            inventory = self.tool.engine_inventory(engine)
            self.assertEqual(
                [item["path"] for item in inventory],
                ["src/elmos_proof_harness/delta.py"],
            )
            (engine / "linked.py").symlink_to(runtime)
            with self.assertRaises(self.tool.QualificationError):
                self.tool.engine_inventory(engine)

    def test_structured_totals_reject_boolean_or_coerced_counts(self) -> None:
        totals = {
            "selected": 1,
            "passed": 1,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "expected_failures": 0,
            "unexpected_successes": 0,
        }
        raw = {"returncode": 0}
        digest = "sha256:" + "a" * 64
        parsed = self._structured(
            totals,
            [self._passing_outcome("suite.test_a", "tests/a.py", digest)],
        )
        self.assertEqual(
            self.tool._assert_structured(
                "tests",
                raw,
                parsed,
                start_directory="tests",
                pattern="test_delta_*.py",
                expected_sources={"tests/a.py": digest},
            )["passed"],
            1,
        )
        parsed["totals"] = totals | {"passed": True}
        with self.assertRaises(self.tool.QualificationError):
            self.tool._assert_structured(
                "tests",
                raw,
                parsed,
                start_directory="tests",
                pattern="test_delta_*.py",
                expected_sources={"tests/a.py": digest},
            )
        parsed["totals"] = totals | {"passed": "1"}
        with self.assertRaises(self.tool.QualificationError):
            self.tool._assert_structured(
                "tests",
                raw,
                parsed,
                start_directory="tests",
                pattern="test_delta_*.py",
                expected_sources={"tests/a.py": digest},
            )

    def test_qualification_test_inventory_is_fixed_and_complete(self) -> None:
        def row(path: Path) -> dict[str, object]:
            return {"path": path.relative_to(self.tool.ENGINE_RELATIVE).as_posix()}

        inventory = [
            row(self.tool.ACCEPTANCE_BINDINGS_RELATIVE),
            *(row(path) for path in self.tool.REQUIRED_ENGINE_DELTA_TESTS),
        ]
        inputs = self.tool.qualification_inputs(inventory)
        self.assertIn(self.tool.ACCEPTANCE_BINDINGS_RELATIVE, inputs)
        self.assertIn(
            self.tool.ENGINE_RELATIVE / "tests/test_delta_contract_closure.py",
            self.tool.REQUIRED_ENGINE_DELTA_TESTS,
        )
        for path in self.tool.REQUIRED_ENGINE_DELTA_TESTS:
            self.assertIn(path, inputs)

        with_optional = [
            *inventory,
            row(self.tool.OPTIONAL_ENGINE_DELTA_TESTS[0]),
        ]
        self.assertIn(
            self.tool.OPTIONAL_ENGINE_DELTA_TESTS[0],
            self.tool.qualification_inputs(with_optional),
        )

        with self.assertRaisesRegex(
            self.tool.QualificationError, "test inventory drifted"
        ):
            self.tool.qualification_inputs(inventory[2:])
        unexpected = self.tool.ENGINE_RELATIVE / "tests/test_delta_fake.py"
        with self.assertRaisesRegex(
            self.tool.QualificationError, "test inventory drifted"
        ):
            self.tool.qualification_inputs([*inventory, row(unexpected)])

    def test_acceptance_binding_is_exact_13_by_8_static_traceability(self) -> None:
        binding_payload, archive_payload = self._acceptance_payloads()
        binding = json.loads(binding_payload)
        validated = self.tool._load_acceptance_bindings(
            binding_payload,
            archive_payload,
        )
        self.assertEqual(validated["skills"], 13)
        self.assertEqual(validated["scenarios_per_skill"], 8)
        self.assertEqual(validated["scenarios"], 104)
        self.assertEqual(len(validated["cases"]), 104)
        self.assertEqual(
            len({case["acceptance_id"] for case in validated["cases"]}),
            104,
        )
        self.assertEqual(
            len({skill["source_acceptance"]["sha256"] for skill in binding["skills"]}),
            13,
        )
        selectors = [
            selector
            for case in validated["cases"]
            for selector in case["repository_test_selectors"]
        ]
        self.assertGreater(len(selectors), len(set(selectors)))
        self.assertFalse(
            binding["binding_semantics"]["static_mapping_is_execution_evidence"]
        )
        self.assertTrue(
            all(
                "local_result" not in case
                for skill in binding["skills"]
                for case in skill["cases"]
            )
        )

    def test_acceptance_binding_rejects_identity_source_and_boundary_drift(
        self,
    ) -> None:
        binding_payload, archive_payload = self._acceptance_payloads()
        baseline = json.loads(binding_payload)
        mutations = []

        incomplete = copy.deepcopy(baseline)
        incomplete["skills"][0]["cases"].pop()
        mutations.append(incomplete)

        duplicate_id = copy.deepcopy(baseline)
        duplicate_id["skills"][0]["cases"][1]["acceptance_id"] = duplicate_id["skills"][
            0
        ]["cases"][0]["acceptance_id"]
        mutations.append(duplicate_id)

        bad_source = copy.deepcopy(baseline)
        bad_source["skills"][0]["source_acceptance"]["sha256"] = "sha256:" + "0" * 64
        mutations.append(bad_source)

        false_execution_claim = copy.deepcopy(baseline)
        false_execution_claim["binding_semantics"][
            "static_mapping_is_execution_evidence"
        ] = True
        mutations.append(false_execution_claim)

        external_overclaim = copy.deepcopy(baseline)
        external_overclaim["skills"][0]["cases"][0]["target_environment"] = "PASSED"
        mutations.append(external_overclaim)

        duplicate_selector = copy.deepcopy(baseline)
        selectors = duplicate_selector["skills"][0]["cases"][0][
            "repository_test_selectors"
        ]
        selectors.append(selectors[0])
        mutations.append(duplicate_selector)

        for index, mutation in enumerate(mutations):
            with (
                self.subTest(index=index),
                self.assertRaises(self.tool.QualificationError),
            ):
                self.tool._load_acceptance_bindings(
                    self.tool.json_bytes(mutation),
                    archive_payload,
                )

        altered_archive = archive_payload[:-1] + bytes([archive_payload[-1] ^ 1])
        with self.assertRaisesRegex(
            self.tool.QualificationError,
            "archive identity drifted",
        ):
            self.tool._load_acceptance_bindings(binding_payload, altered_archive)

    def test_acceptance_results_require_every_bound_selector_to_pass(self) -> None:
        binding_payload, archive_payload = self._acceptance_payloads()
        validated = self.tool._load_acceptance_bindings(
            binding_payload,
            archive_payload,
        )
        selectors = sorted(
            {
                selector
                for case in validated["cases"]
                for selector in case["repository_test_selectors"]
            }
        )
        outcomes = [
            self._passing_outcome(
                selector,
                "engines/proof-driven-harness-engine/tests/"
                + selector.split(".", 1)[0]
                + ".py",
                "sha256:" + self.tool.sha256(selector.encode()),
            )
            for selector in selectors
        ]
        result = self.tool._assert_acceptance_results(validated, outcomes)
        self.assertEqual(result["local_cases"]["passed"], 104)
        self.assertEqual(result["local_cases"]["p0_passed"], 89)
        self.assertEqual(result["local_cases"]["p1_passed"], 15)
        self.assertEqual(len(result["case_results"]), 104)
        self.assertEqual(result["target_environment"], "NOT_RUN")
        self.assertEqual(result["independent_verification"], "NOT_RUN")
        self.assertEqual(result["certification"], "NOT_CERTIFIED")
        self.assertTrue(
            all(
                case["local_result"] == "PASSED"
                and case["local_evidence_boundary"] == "LOCAL_EXECUTED_SELF_ATTESTED"
                and case["target_environment"] == "NOT_RUN"
                and case["certification"] == "NOT_CERTIFIED"
                for case in result["case_results"]
            )
        )

        with self.assertRaisesRegex(
            self.tool.QualificationError,
            "selector did not pass",
        ):
            self.tool._assert_acceptance_results(validated, outcomes[1:])

        failed = copy.deepcopy(outcomes)
        failed[0]["status"] = "FAILED"
        with self.assertRaisesRegex(
            self.tool.QualificationError,
            "selector did not pass",
        ):
            self.tool._assert_acceptance_results(validated, failed)

        with self.assertRaisesRegex(
            self.tool.QualificationError,
            "duplicate selectors",
        ):
            self.tool._assert_acceptance_results(validated, [*outcomes, outcomes[0]])

    def test_structured_results_cover_every_fixed_source(self) -> None:
        digest_a = "sha256:" + "a" * 64
        digest_b = "sha256:" + "b" * 64

        totals = {
            "selected": 2,
            "passed": 2,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "expected_failures": 0,
            "unexpected_successes": 0,
        }
        parsed = self._structured(
            totals,
            [
                self._passing_outcome("suite.test_a", "tests/a.py", digest_a),
                self._passing_outcome("suite.test_b", "tests/b.py", digest_b),
            ],
        )
        raw = {"returncode": 0}
        self.tool._assert_structured(
            "tests",
            raw,
            parsed,
            start_directory="tests",
            pattern="test_delta_*.py",
            expected_sources={"tests/a.py": digest_a, "tests/b.py": digest_b},
        )
        parsed["outcomes"] = [
            self._passing_outcome("suite.test_a", "tests/a.py", digest_a),
            self._passing_outcome("suite.test_a2", "tests/a.py", digest_a),
        ]
        with self.assertRaisesRegex(
            self.tool.QualificationError, "every fixed test source"
        ):
            self.tool._assert_structured(
                "tests",
                raw,
                parsed,
                start_directory="tests",
                pattern="test_delta_*.py",
                expected_sources={
                    "tests/a.py": digest_a,
                    "tests/b.py": digest_b,
                },
            )

    def test_installation_check_cannot_overclaim_external_evidence(self) -> None:
        raw = {"returncode": 0}
        parsed = {
            "schema_version": "1.0.0",
            "package": f"{self.tool.PACKAGE_NAME}@{self.tool.PACKAGE_VERSION}",
            "archive": {
                "sha256": self.tool.ARCHIVE_SHA256,
                "bytes": self.tool.ARCHIVE_BYTES,
            },
            "action": "check",
            "installation": {"status": "PASS"},
            "implementation_status": "DECLARED_RUNTIME_UNQUALIFIED",
            "external_runtime_status": "NOT_RUN",
            "certification_status": "NOT_CERTIFIED",
        }
        self.tool._assert_installation_check(raw, parsed)
        for field, value in (
            ("external_runtime_status", "PASS"),
            ("certification_status", "CERTIFIED"),
        ):
            with self.subTest(field=field):
                tampered = dict(parsed)
                tampered[field] = value
                with self.assertRaises(self.tool.QualificationError):
                    self.tool._assert_installation_check(raw, tampered)

    def test_subprocess_environment_does_not_inherit_secrets(self) -> None:
        with (
            tempfile.TemporaryDirectory() as value,
            patch.dict(
                os.environ,
                {"ELMOS_TEST_SECRET": "must-not-leak", "PATH": "/usr/bin:/bin"},
                clear=False,
            ),
        ):
            environment = self.tool._environment(Path(value))
        self.assertNotIn("ELMOS_TEST_SECRET", environment)
        self.assertEqual(environment["PYTHONDONTWRITEBYTECODE"], "1")
        self.assertEqual(environment["UV_OFFLINE"], "1")


if __name__ == "__main__":
    unittest.main()
