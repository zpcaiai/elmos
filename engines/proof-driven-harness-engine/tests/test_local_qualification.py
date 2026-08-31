from __future__ import annotations

import importlib.metadata
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import tempfile
from types import ModuleType
from typing import ClassVar
import unittest
from unittest.mock import call, patch


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parents[1]
TOOL = ROOT / "tools" / "qualify_local.py"
RUNNER_TOOL = ROOT / "tools" / "run_structured_unittest.py"


def load_tool() -> ModuleType:
    specification = importlib.util.spec_from_file_location("qualify_local", TOOL)
    if specification is None or specification.loader is None:
        raise RuntimeError("local qualifier could not be loaded")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def load_runner() -> ModuleType:
    specification = importlib.util.spec_from_file_location(
        "run_structured_unittest_for_test",
        RUNNER_TOOL,
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("structured runner could not be loaded")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


class LocalQualificationTests(unittest.TestCase):
    tool: ClassVar[ModuleType]
    runner: ClassVar[ModuleType]

    @classmethod
    def setUpClass(cls) -> None:
        cls.tool = load_tool()
        cls.runner = load_runner()

    def test_structured_runner_source_binds_setup_class_errors(self) -> None:
        error = unittest.suite._ErrorHolder(  # type: ignore[attr-defined]
            f"setUpClass ({__name__}.LocalQualificationTests)"
        )
        result = self.runner.StructuredResult(
            io.StringIO(),
            True,
            2,
            repository_root=REPOSITORY_ROOT,
        )
        binding = result._source_binding(error)
        self.assertEqual(binding["selector"], error.id())
        self.assertEqual(
            binding["source_path"],
            Path(__file__).resolve().relative_to(REPOSITORY_ROOT).as_posix(),
        )

    def test_execution_environment_preserves_virtualenv_invocation_path(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            invocation = Path(value) / "python"
            invocation.symlink_to(Path(os.sys.executable).resolve(strict=True))
            with patch.object(self.tool.sys, "executable", str(invocation)):
                environment = self.tool._execution_environment(
                    REPOSITORY_ROOT,
                    RUNNER_TOOL.relative_to(REPOSITORY_ROOT),
                )

        self.assertEqual(
            environment["python"]["executable"],
            str(invocation.absolute()),
        )

    def _postgres_bin(self, root: Path) -> Path:
        bin_root = root / "postgresql-17.5" / "bin"
        bin_root.mkdir(parents=True)
        for name in ("initdb", "pg_ctl", "psql", "postgres"):
            (bin_root / name).write_bytes(f"fixture:{name}".encode())
        return bin_root

    def _version_runner(
        self,
        bin_root: Path,
        *,
        overrides: dict[str, str] | None = None,
    ):
        versions = overrides or {}

        def run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
            name = Path(argv[0]).name
            output = versions.get(
                name,
                f"{name} (PostgreSQL) 17.5 (Homebrew)",
            )
            return subprocess.CompletedProcess(
                [str(bin_root / name), "--version"],
                0,
                stdout=(output + "\n").encode(),
                stderr=b"",
            )

        return run

    def test_initdb_version_parser_accepts_vendor_suffix_without_widening(self) -> None:
        accepted = {
            "initdb (PostgreSQL) 17.5": "17.5",
            "initdb (PostgreSQL) 17.5 (Homebrew)": "17.5",
            "initdb (PostgreSQL) 17.5 (vendor-build)": "17.5",
        }
        for output, expected in accepted.items():
            with self.subTest(output=output):
                self.assertEqual(self.tool._initdb_major_minor(output), expected)

        for output in (
            "initdb (PostgreSQL) 17.5 unbounded-suffix",
            "initdb (PostgreSQL) 17.5.1",
            "initdb (PostgreSQL) 17.5 (nested(vendor))",
            "postgres (PostgreSQL) 17.5 (Homebrew)",
            "initdb (PostgreSQL) 17.5\nforged",
        ):
            with self.subTest(output=output):
                self.assertIsNone(self.tool._initdb_major_minor(output))

        for name in self.tool.POSTGRES_TOOL_NAMES:
            output = f"{name} (PostgreSQL) 17.5 (Homebrew)"
            self.assertEqual(
                self.tool._postgres_tool_major_minor(name, output),
                "17.5",
            )
            self.assertIsNone(
                self.tool._postgres_tool_major_minor(
                    name,
                    "initdb (PostgreSQL) 17.5 (Homebrew)",
                )
                if name != "initdb"
                else self.tool._postgres_tool_major_minor(
                    name,
                    "pg_ctl (PostgreSQL) 17.5 (Homebrew)",
                )
            )

    def test_postgres_preflight_accepts_homebrew_and_exact_driver_tuple(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            bin_root = self._postgres_bin(Path(value))
            with (
                patch.dict(
                    os.environ,
                    {"ELMOS_TEST_POSTGRES17_BIN": str(bin_root)},
                    clear=False,
                ),
                patch.object(
                    self.tool.subprocess,
                    "run",
                    side_effect=self._version_runner(bin_root),
                ) as version_run,
                patch.object(
                    self.tool.importlib.metadata,
                    "version",
                    return_value=self.tool.PSYCOPG_VERSION,
                ) as metadata_version,
            ):
                environment, extra = self.tool._postgres17_preflight(
                    REPOSITORY_ROOT
                )

        self.assertEqual(environment["status"], "AVAILABLE_EXACT")
        self.assertEqual(environment["observed_version"], "17.5")
        self.assertEqual(
            environment["version_output"],
            "initdb (PostgreSQL) 17.5 (Homebrew)",
        )
        self.assertEqual(environment["psycopg_version"], "3.2.13")
        self.assertEqual(environment["psycopg_binary_version"], "3.2.13")
        self.assertEqual(
            metadata_version.call_args_list,
            [call("psycopg"), call("psycopg-binary")],
        )
        self.assertEqual(
            extra,
            {"ELMOS_TEST_POSTGRES17_BIN": str(bin_root.resolve())},
        )
        self.assertEqual(version_run.call_count, 4)
        self.assertEqual(
            [item["name"] for item in environment["tools"]],
            list(self.tool.POSTGRES_TOOL_NAMES),
        )
        self.assertTrue(
            all(item["observed_version"] == "17.5" for item in environment["tools"])
        )

    def test_postgres_preflight_rejects_wrong_version_before_driver_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            bin_root = self._postgres_bin(Path(value))
            for wrong_tool, output in (
                ("initdb", "initdb (PostgreSQL) 16.5"),
                ("pg_ctl", "pg_ctl (PostgreSQL) 17.6 (Homebrew)"),
                ("psql", "psql (PostgreSQL) 17.50"),
                ("postgres", "postgres (PostgreSQL) 17.5.1"),
            ):
                with self.subTest(wrong_tool=wrong_tool, output=output):
                    with (
                        patch.dict(
                            os.environ,
                            {"ELMOS_TEST_POSTGRES17_BIN": str(bin_root)},
                            clear=False,
                        ),
                        patch.object(
                            self.tool.subprocess,
                            "run",
                            side_effect=self._version_runner(
                                bin_root,
                                overrides={wrong_tool: output},
                            ),
                        ),
                        patch.object(
                            self.tool.importlib.metadata,
                            "version",
                        ) as metadata_version,
                        self.assertRaisesRegex(
                            self.tool.QualificationError,
                            "requires exact PostgreSQL 17.5",
                        ),
                    ):
                        self.tool._postgres17_preflight(REPOSITORY_ROOT)
                    metadata_version.assert_not_called()

    def test_postgres_preflight_rejects_missing_driver_distribution(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            bin_root = self._postgres_bin(Path(value))
            for missing_name in ("psycopg", "psycopg-binary"):
                with self.subTest(missing_name=missing_name):
                    def distribution_version(name: str) -> str:
                        if name == missing_name:
                            raise importlib.metadata.PackageNotFoundError(name)
                        return self.tool.PSYCOPG_VERSION

                    with (
                        patch.dict(
                            os.environ,
                            {"ELMOS_TEST_POSTGRES17_BIN": str(bin_root)},
                            clear=False,
                        ),
                        patch.object(
                            self.tool.subprocess,
                            "run",
                            side_effect=self._version_runner(bin_root),
                        ),
                        patch.object(
                            self.tool.importlib.metadata,
                            "version",
                            side_effect=distribution_version,
                        ),
                        self.assertRaisesRegex(
                            self.tool.QualificationError,
                            "requires psycopg and psycopg-binary",
                        ),
                    ):
                        self.tool._postgres17_preflight(REPOSITORY_ROOT)

    def test_postgres_preflight_rejects_wrong_driver_version(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            bin_root = self._postgres_bin(Path(value))
            with (
                patch.dict(
                    os.environ,
                    {"ELMOS_TEST_POSTGRES17_BIN": str(bin_root)},
                    clear=False,
                ),
                patch.object(
                    self.tool.subprocess,
                    "run",
                    side_effect=self._version_runner(bin_root),
                ),
                patch.object(
                    self.tool.importlib.metadata,
                    "version",
                    side_effect=("3.2.13", "3.2.12"),
                ),
                self.assertRaisesRegex(
                    self.tool.QualificationError,
                    "requires exact psycopg/psycopg-binary 3.2.13",
                ),
            ):
                self.tool._postgres17_preflight(REPOSITORY_ROOT)

    def test_postgres_preflight_reports_missing_toolchain(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            missing = Path(value) / "missing-postgresql-bin"
            with (
                patch.dict(
                    os.environ,
                    {"ELMOS_TEST_POSTGRES17_BIN": str(missing)},
                    clear=False,
                ),
                self.assertRaisesRegex(
                    self.tool.QualificationError,
                    "PostgreSQL 17.5 tools were not found",
                ),
            ):
                self.tool._postgres17_preflight(REPOSITORY_ROOT)

    def test_required_postgres_preflight_fails_before_any_test_command(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            repository_root = Path(value)
            archive = repository_root / (
                "skills/subskills/"
                "elmos-proof-driven-agentic-harness-repository-semantic-compiler-v3.0.0.zip"
            )
            archive.parent.mkdir(parents=True)
            archive.write_bytes(b"fixture archive")
            engine_root = repository_root / self.tool.ENGINE_RELATIVE
            engine_root.mkdir(parents=True)
            (engine_root / "fixture.txt").write_bytes(b"engine fixture")
            with (
                patch.object(
                    self.tool,
                    "ARCHIVE_SHA256",
                    self.tool.sha256_bytes(b"fixture archive"),
                ),
                patch.object(
                    self.tool,
                    "_postgres17_preflight",
                    side_effect=self.tool.QualificationError("preflight blocked"),
                ),
                patch.object(self.tool, "_run_fixed_command") as run_command,
                self.assertRaisesRegex(self.tool.QualificationError, "preflight blocked"),
            ):
                self.tool.qualify(repository_root, postgres17_mode="require")
            run_command.assert_not_called()

    def test_required_postgres_rechecks_toolchain_after_execution(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            repository_root = Path(value)
            archive = repository_root / (
                "skills/subskills/"
                "elmos-proof-driven-agentic-harness-repository-semantic-compiler-v3.0.0.zip"
            )
            archive.parent.mkdir(parents=True)
            archive.write_bytes(b"fixture archive")
            engine_root = repository_root / self.tool.ENGINE_RELATIVE
            raw_directory = engine_root / "qualification/raw"
            raw_directory.mkdir(parents=True)
            before = {
                "status": "AVAILABLE_EXACT",
                "required_version": "17.5",
                "tools": [{"name": "initdb", "sha256": "sha256:" + "a" * 64}],
            }
            after = {
                **before,
                "tools": [{"name": "initdb", "sha256": "sha256:" + "b" * 64}],
            }
            totals = {
                "selected": 1,
                "passed": 1,
                "failed": 0,
                "errors": 0,
                "skipped": 0,
                "expected_failures": 0,
                "unexpected_successes": 0,
            }
            command_result = (
                {
                    "path": "qualification/raw/fixture.json",
                    "sha256": "0" * 64,
                    "bytes": 1,
                },
                totals,
                True,
            )
            with (
                patch.object(
                    self.tool,
                    "ARCHIVE_SHA256",
                    self.tool.sha256_bytes(b"fixture archive"),
                ),
                patch.object(self.tool, "engine_inventory", return_value=[]),
                patch.object(
                    self.tool,
                    "_ensure_private_output_tree",
                    return_value=(engine_root / "qualification", raw_directory),
                ),
                patch.object(
                    self.tool,
                    "_postgres17_preflight",
                    side_effect=(
                        (before, {"ELMOS_TEST_POSTGRES17_BIN": "/fixture/bin"}),
                        (after, {"ELMOS_TEST_POSTGRES17_BIN": "/fixture/bin"}),
                    ),
                ) as preflight,
                patch.object(
                    self.tool,
                    "_run_fixed_command",
                    return_value=command_result,
                ) as run_command,
                self.assertRaisesRegex(
                    self.tool.QualificationError,
                    "toolchain identity changed",
                ),
            ):
                self.tool.qualify(repository_root, postgres17_mode="require")
            self.assertEqual(preflight.call_count, 2)
            self.assertEqual(run_command.call_count, 4)


if __name__ == "__main__":
    unittest.main()
