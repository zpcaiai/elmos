from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class PolyglotRouteCiReadinessTests(unittest.TestCase):
    def test_frontend_ci_binds_exact_openssl_ed25519_runtime(self) -> None:
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        frontend_job = workflow.split("  frontend-client-engine:", 1)[1].split(
            "  polyglot-route-pack-contracts:", 1
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
        self.assertIn("runs-on: macos-15", frontend_job)
        self.assertEqual(
            frontend_job.count("/opt/homebrew/Cellar/openssl@3/3.6.3/bin/openssl"), 2
        )
        self.assertIn(
            "os.path.realpath(sys.argv[1], strict=True)",
            frontend_job,
        )
        self.assertEqual(frontend_job.count("python3.11 -I -B -c"), 4)
        self.assertEqual(frontend_job.count("OPENSSL3_COMPONENT_RECEIPT"), 1)
        self.assertIn(
            "/opt/homebrew/Cellar/openssl@3/3.6.3/lib/libssl.3.dylib",
            frontend_job,
        )
        self.assertIn(
            "/opt/homebrew/Cellar/openssl@3/3.6.3/lib/libcrypto.3.dylib",
            frontend_job,
        )
        self.assertNotIn("/usr/bin/realpath", frontend_job)
        self.assertIn('test "$(/usr/bin/uname -m)" = "arm64"', frontend_job)
        self.assertIn(
            'test "$(/usr/bin/sw_vers -productVersion | /usr/bin/cut -d. -f1)" = "15"',
            frontend_job,
        )
        self.assertEqual(frontend_job.count("INSTALL_RECEIPT.json"), 1)
        self.assertIn('value.get("built_as_bottle") is True', frontend_job)
        self.assertIn('value.get("poured_from_bottle") is True', frontend_job)
        self.assertIn('source.get("tap") == "homebrew/core"', frontend_job)
        self.assertIn('source.get("spec") == "stable"', frontend_job)
        self.assertIn("packages.arm64_sequoia.jws.json", frontend_job)
        self.assertEqual(frontend_job.count("OPENSSL3_RUNNER_RECEIPT"), 2)
        self.assertEqual(frontend_job.count('test "${image_os}" = "macos15"'), 2)
        self.assertEqual(
            frontend_job.count('test "${image_version}" = "20260727.0256.1"'),
            2,
        )
        self.assertEqual(
            frontend_job.count('test "${openssl_stat}" = "555:501:80:1:878752"'),
            2,
        )
        self.assertEqual(
            frontend_job.count(
                "d0ab050d71d431be5e1372a79972361f7bcef4a7c2c5aef3e7c0ce7bac0e3ee8"
            ),
            2,
        )
        self.assertEqual(frontend_job.count("/usr/bin/stat -f"), 3)
        self.assertEqual(frontend_job.count("/usr/bin/shasum -a 256"), 3)
        self.assertGreaterEqual(
            frontend_job.count(
                "OpenSSL 3.6.3 9 Jun 2026 (Library: OpenSSL 3.6.3 9 Jun 2026)"
            ),
            2,
        )
        self.assertEqual(frontend_job.count("/usr/bin/codesign --verify --strict"), 3)
        self.assertEqual(frontend_job.count("/usr/bin/mktemp -d"), 2)
        self.assertEqual(frontend_job.count("trap '/bin/rm -rf --"), 2)
        self.assertGreaterEqual(frontend_job.count("pkeyutl -sign"), 2)
        self.assertGreaterEqual(frontend_job.count("pkeyutl -verify"), 2)
        self.assertIn(
            "printf '%s\\n' \"/opt/homebrew/Cellar/openssl@3/3.6.3/bin\" "
            '>>"${GITHUB_PATH}"',
            frontend_job,
        )
        self.assertIn('test "$(command -v openssl)" = "${openssl_bin}"', frontend_job)

    def test_ci_hydrates_locked_rust_analyzer_before_offline_execution(self) -> None:
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        native_runner = (
            ROOT / "engines/polyglot-route-engine/src/elmos_polyglot_route/native.py"
        ).read_text(encoding="utf-8")

        route_engine_job = workflow.split("  polyglot-route-engine:", 1)[1].split(
            "  polyglot-routes:", 1
        )[0]
        route_gate_job = workflow.split("  polyglot-routes:", 1)[1].split(
            "  sql-dialect-engine:", 1
        )[0]
        route_pack_job = workflow.split("  polyglot-route-pack-contracts:", 1)[1].split(
            "  polyglot-route-engine:", 1
        )[0]
        cargo_fetch = route_engine_job.index("cargo fetch")
        private_environment = route_engine_job.index(
            "UV_PROJECT_ENVIRONMENT=${RUNNER_TEMP}/elmos-polyglot-route-venv"
        )
        route_sync = route_engine_job.index(
            "uv --directory engines/polyglot-route-engine sync --locked"
        )
        closure_tests = route_engine_job.index(
            '"$GITHUB_WORKSPACE/tests/batch35/test_packed_replay_schema_closure.py"'
        )
        pytest_command = (
            "uv --directory engines/polyglot-route-engine run --locked pytest"
        )
        route_tests = route_engine_job.index(
            pytest_command,
            closure_tests + len(pytest_command),
        )

        self.assertLess(cargo_fetch, route_tests)
        self.assertLess(private_environment, route_sync)
        self.assertLess(route_sync, closure_tests)
        self.assertLess(closure_tests, route_tests)
        self.assertIn("timeout-minutes: 360", route_engine_job)
        self.assertIn("if: ${{ always() }}", route_gate_job)
        self.assertIn(
            'test "${{ needs.polyglot-route-pack-contracts.result }}" = "success"',
            route_gate_job,
        )
        self.assertIn(
            'test "${{ needs.polyglot-route-engine.result }}" = "success"',
            route_gate_job,
        )
        self.assertEqual(
            route_engine_job.count(
                '"$GITHUB_WORKSPACE/tests/batch35/test_packed_replay_schema_closure.py"'
            ),
            1,
        )
        route_pack_sync = route_pack_job.index(
            "uv --directory engines/polyglot-route-engine sync --locked"
        )
        batch29 = route_pack_job.index("make b29-skills-test")
        matrix = route_pack_job.index(
            "python scripts/operations/validate_translation_route_matrix.py"
        )
        route_gates = route_pack_job.index(
            'python scripts/batch29/run_route_gate.py "$route"'
        )
        self.assertIn("timeout-minutes: 360", route_pack_job)
        self.assertLess(route_pack_sync, batch29)
        self.assertLess(batch29, matrix)
        self.assertLess(matrix, route_gates)
        self.assertNotIn("make b29-skills-test", route_engine_job)
        self.assertIn("cargo fetch \\", route_engine_job)
        self.assertIn("--locked \\", route_engine_job)
        self.assertIn(
            "--manifest-path engines/polyglot-route-engine/native/rust/Cargo.toml",
            route_engine_job,
        )
        self.assertIn('"--offline"', native_runner)
        self.assertIn('"--locked"', native_runner)


if __name__ == "__main__":
    unittest.main()
