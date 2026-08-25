from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class PolyglotRouteCiReadinessTests(unittest.TestCase):
    def test_ci_hydrates_locked_rust_analyzer_before_offline_execution(self) -> None:
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        native_runner = (
            ROOT / "engines/polyglot-route-engine/src/elmos_polyglot_route/native.py"
        ).read_text(encoding="utf-8")

        route_job = workflow.split("  polyglot-routes:", 1)[1].split(
            "  project-synthesis:", 1
        )[0]
        cargo_fetch = route_job.index("cargo fetch")
        route_tests = route_job.index(
            "uv --directory engines/polyglot-route-engine run --locked pytest"
        )

        self.assertLess(cargo_fetch, route_tests)
        self.assertIn("cargo fetch \\", route_job)
        self.assertIn("--locked \\", route_job)
        self.assertIn(
            "--manifest-path engines/polyglot-route-engine/native/rust/Cargo.toml",
            route_job,
        )
        self.assertIn('"--offline"', native_runner)
        self.assertIn('"--locked"', native_runner)


if __name__ == "__main__":
    unittest.main()
