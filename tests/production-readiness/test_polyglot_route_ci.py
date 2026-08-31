from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class PolyglotRouteCiReadinessTests(unittest.TestCase):
    def test_frontend_ci_binds_exact_openssl_ed25519_runtime(self) -> None:
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        frontend_job = workflow.split("  frontend-client-engine:", 1)[1].split(
            "  polyglot-routes:", 1
        )[0]

        bind_runtime = frontend_job.index("- name: Bind OpenSSL 3 Ed25519 runtime")
        verify_runtime = frontend_job.index("- name: Verify bound OpenSSL runtime")
        frontend_tests = frontend_job.index("- name: Test Frontend Client Engine")
        formal_replay = frontend_job.index(
            "- name: Replay complete Batch 32 and Batch 35 formal gates"
        )

        self.assertLess(frontend_tests, bind_runtime)
        self.assertLess(bind_runtime, verify_runtime)
        self.assertLess(verify_runtime, formal_replay)
        self.assertNotIn("brew install openssl@3", frontend_job)
        self.assertEqual(
            frontend_job.count(
                "/opt/homebrew/Cellar/openssl@3/3.6.3/bin/openssl"
            ),
            2,
        )
        self.assertIn(
            "os.path.realpath(sys.argv[1], strict=True)",
            frontend_job,
        )
        self.assertEqual(frontend_job.count("python3.11 -I -B -c"), 2)
        self.assertNotIn("/usr/bin/realpath", frontend_job)
        self.assertGreaterEqual(
            frontend_job.count(
                "OpenSSL 3.6.3 9 Jun 2026 (Library: OpenSSL 3.6.3 9 Jun 2026)"
            ),
            2,
        )
        self.assertEqual(
            frontend_job.count("/usr/bin/codesign --verify --strict"), 2
        )
        self.assertEqual(frontend_job.count("/usr/bin/mktemp -d"), 2)
        self.assertEqual(frontend_job.count("trap '/bin/rm -rf --"), 2)
        self.assertGreaterEqual(frontend_job.count("pkeyutl -sign"), 2)
        self.assertGreaterEqual(frontend_job.count("pkeyutl -verify"), 2)
        self.assertIn(
            'printf \'%s\\n\' "/opt/homebrew/Cellar/openssl@3/3.6.3/bin" '
            '>>"${GITHUB_PATH}"',
            frontend_job,
        )
        self.assertIn(
            'test "$(command -v openssl)" = "${openssl_bin}"', frontend_job
        )

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
