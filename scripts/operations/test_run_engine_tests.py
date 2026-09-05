from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SUBJECT_PATH = Path(__file__).with_name("run_engine_tests.py")
SPEC = importlib.util.spec_from_file_location("run_engine_tests_subject", SUBJECT_PATH)
assert SPEC is not None and SPEC.loader is not None
subject = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = subject
SPEC.loader.exec_module(subject)


class EngineTestRegistryTests(unittest.TestCase):
    def test_registry_covers_every_engine_and_nested_database_test_surface(self) -> None:
        engines = subject.load_registry()

        self.assertEqual(42, len(engines))
        self.assertEqual(44, sum(len(value["steps"]) for value in engines.values()))
        self.assertEqual(
            {"maven", "pytest"},
            {step["kind"] for step in engines["database-data-engine"]["steps"]},
        )
        self.assertEqual(
            {"maven", "pytest"},
            {step["kind"] for step in engines["security-compliance-engine"]["steps"]},
        )
        self.assertEqual(
            "modules/composite-modernization",
            engines["composite-engine"]["steps"][0]["module"],
        )
        self.assertEqual(
            ["tests/database-bigdata-skills"],
            engines["database-bigdata-engine"]["steps"][0]["tests"],
        )

    def test_every_pytest_command_keeps_repository_cwd_and_clears_addopts(self) -> None:
        engines = subject.load_registry()
        run_root = Path("/tmp/elmos-engine-test-unit")

        for engine, contract in engines.items():
            for step in contract["steps"]:
                if step["kind"] != "pytest":
                    continue
                command = subject.build_command(
                    engine,
                    step,
                    run_root,
                    uv="uv",
                    maven="mvn",
                    dotnet="dotnet",
                )
                with self.subTest(engine=engine, step=step["name"]):
                    self.assertNotIn("--directory", command)
                    self.assertNotIn("-q", command)
                    self.assertIn("-o", command)
                    self.assertIn("addopts=", command)
                    self.assertIn("-p", command)
                    self.assertIn("no:cacheprovider", command)
                    if step.get("project") is not None:
                        self.assertIn("--project", command)

    def test_duplicate_json_keys_are_rejected_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "registry.json"
            path.write_text(
                '{"schema_version":"a","schema_version":"b","engines":{}}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(subject.RegistryError, "duplicate JSON key"):
                subject.load_registry(path)

    def test_missing_engine_registry_entry_is_rejected(self) -> None:
        document = json.loads(subject.DEFAULT_REGISTRY.read_text(encoding="utf-8"))
        document["engines"].pop("functional-assurance-engine")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "registry.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(subject.RegistryError, "missing=.*functional-assurance"):
                subject.load_registry(path)

    def test_path_escape_is_rejected(self) -> None:
        document = json.loads(subject.DEFAULT_REGISTRY.read_text(encoding="utf-8"))
        document["engines"]["functional-assurance-engine"]["steps"][0]["tests"] = [
            "../outside"
        ]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "registry.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(subject.RegistryError, "repository-confined"):
                subject.load_registry(path)


class EngineTestResultClassificationTests(unittest.TestCase):
    def test_green_pytest_requires_a_real_summary(self) -> None:
        verdict, summary = subject.classify_pytest(
            0,
            "================ 15 passed in 0.14s ================\n",
        )
        self.assertEqual("PASSED", verdict)
        self.assertEqual("15 passed in 0.14s", summary)

        verdict, summary = subject.classify_pytest(
            0,
            "32 passed, 1 warning in 26.60s\n",
        )
        self.assertEqual("PASSED", verdict)
        self.assertEqual("32 passed, 1 warning in 26.60s", summary)

        verdict, summary = subject.classify_pytest(0, "........ [100%]\n")
        self.assertEqual("NO_SUMMARY", verdict)
        self.assertIsNone(summary)

    def test_collection_and_internal_errors_are_not_normal_failures(self) -> None:
        self.assertEqual(
            ("COLLECTION_ERROR", None),
            subject.classify_pytest(2, "ERROR collecting tests/test_import.py\n"),
        )
        self.assertEqual(
            ("PYTEST_INTERNAL_ERROR", None),
            subject.classify_pytest(3, "INTERNALERROR> teardown failed\n"),
        )
        self.assertEqual(
            ("NO_TESTS_COLLECTED", None),
            subject.classify_pytest(5, "no tests ran in 0.01s\n"),
        )

    def test_nul_bytes_cannot_hide_failure_lines(self) -> None:
        output = (
            "tamper evidence \x00 remains text\n"
            "FAILED tests/test_a.py::test_one - AssertionError\n"
            "1 failed, 1 passed in 0.02s\n"
        )
        verdict, summary = subject.classify_pytest(1, output)
        self.assertEqual("FAILED", verdict)
        self.assertEqual("1 failed, 1 passed in 0.02s", summary)

    def test_failed_summary_cannot_pass_even_with_zero_exit(self) -> None:
        self.assertEqual(
            ("FAILED", "1 failed in 0.01s"),
            subject.classify_pytest(0, "1 failed in 0.01s\n"),
        )

    def test_dependency_resolution_failure_is_environment_without_summary(self) -> None:
        self.assertEqual(
            ("ENVIRONMENT", None),
            subject.classify_pytest(
                1,
                "No solution found when resolving dependencies\n",
            ),
        )

    def test_skipped_only_suite_is_explicit(self) -> None:
        self.assertEqual(
            ("PASSED_WITH_SKIPS", "2 skipped in 0.03s"),
            subject.classify_pytest(0, "2 skipped in 0.03s\n"),
        )
        self.assertEqual(
            ("PASSED_WITH_SKIPS", "1 xfailed in 0.03s"),
            subject.classify_pytest(0, "1 xfailed in 0.03s\n"),
        )

    def test_timeout_and_missing_executable_are_distinct(self) -> None:
        self.assertEqual(
            ("TIMEOUT", None),
            subject.classify_pytest(None, "", timed_out=True),
        )
        self.assertEqual("ENVIRONMENT", subject.classify_command(None, "cannot start"))


if __name__ == "__main__":
    unittest.main()
