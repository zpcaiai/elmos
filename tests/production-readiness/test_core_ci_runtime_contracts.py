from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _job(workflow: str, name: str, next_name: str) -> str:
    return workflow.split(f"  {name}:\n", 1)[1].split(f"  {next_name}:\n", 1)[0]


class CoreCiRuntimeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    def test_project_synthesis_builds_native_solver_before_python_tests(self) -> None:
        job = _job(self.workflow, "project-synthesis", "project-synthesis-acceptance")
        rust = job.index("- name: Set up Rust 1.89.0")
        native = job.index("- name: Build native dependency solver")
        tests = job.index("- name: Verify Project Synthesis")

        self.assertLess(rust, native)
        self.assertLess(native, tests)
        self.assertIn("cargo build --locked --release", job)
        self.assertIn("--manifest-path native/rust-core/Cargo.toml", job)

    def test_web_console_binds_chinadb_runtime_after_python_312_consumers(self) -> None:
        job = _job(self.workflow, "web-console", "precision-migration-b01-44")
        polyglot_sync = job.index("uv --directory engines/polyglot-route-engine sync --locked --no-dev")
        qr_test = job.index("- name: Verify WeChat Native QR encoder")
        chinadb = job.index("- name: Set up exact ChinaDB preflight runtime")
        web_check = job.index("- name: Type-check and build")

        self.assertLess(polyglot_sync, chinadb)
        self.assertLess(qr_test, chinadb)
        self.assertLess(chinadb, web_check)
        self.assertIn('python-version: "3.14.6"', job)
        self.assertEqual(job.count("platform.python_version()"), 2)
        self.assertIn(
            "uv --directory engines/database-data-engine/sql-transpiler run --locked",
            job,
        )

    def test_every_web_check_binds_the_exact_chinadb_runtime(self) -> None:
        jobs = (
            _job(self.workflow, "web-console", "precision-migration-b01-44"),
            _job(
                self.workflow,
                "precision-migration-b01-44",
                "web-console-generation",
            ),
            _job(self.workflow, "web-console-generation", "web-console-runner-e2e"),
        )
        for job in jobs:
            with self.subTest(job=job.splitlines()[1].strip()):
                runtime = job.index("- name: Set up exact ChinaDB preflight runtime")
                check = job.index("pnpm --dir apps/web-console check")
                self.assertLess(runtime, check)
                self.assertIn('python-version: "3.14.6"', job)
                self.assertIn(
                    "uv --directory engines/database-data-engine/sql-transpiler run --locked",
                    job,
                )

    def test_web_api_handlers_are_complete_behind_bounded_vercel_entrypoints(self) -> None:
        api_root = ROOT / "apps/web-console/app/api"
        entrypoints = {
            path.relative_to(api_root).as_posix()
            for path in api_root.rglob("route.ts")
        }
        self.assertEqual({"[[...path]]/route.ts", "frt/catalog/route.ts"}, entrypoints)

        handlers = {
            "./" + path.relative_to(api_root).as_posix().removesuffix(".ts")
            for path in api_root.rglob("_route.ts")
        }
        registry = (api_root / "_routeRegistry.ts").read_text(encoding="utf-8")
        imports = set(re.findall(r'import \* as route\d+ from "([^\"]+)";', registry))
        self.assertEqual(handlers, imports)
        self.assertEqual(len(handlers), registry.count(" as ApiRouteModule },"))
        self.assertNotIn("continue-on-error", registry)


if __name__ == "__main__":
    unittest.main()
