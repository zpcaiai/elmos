from __future__ import annotations

import ast
import importlib.util
import re
import subprocess
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _supported_route_languages() -> tuple[str, ...]:
    models_path = (
        ROOT
        / "engines/polyglot-route-engine/src/elmos_polyglot_route/models.py"
    )
    module = ast.parse(models_path.read_text(encoding="utf-8"))
    for node in module.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "SUPPORTED_LANGUAGES"
        ):
            value = ast.literal_eval(node.value)
            if isinstance(value, tuple) and all(isinstance(item, str) for item in value):
                return value
    raise AssertionError("SUPPORTED_LANGUAGES literal was not found")


def _repository_matrix_test_inventory() -> tuple[frozenset[str], frozenset[str]]:
    matrix_path = (
        ROOT
        / "engines/polyglot-route-engine/tests"
        / "test_repository_pipeline_language_matrix.py"
    )
    module = ast.parse(matrix_path.read_text(encoding="utf-8"))
    parameterized: set[str] = set()
    invariants: set[str] = set()
    for node in module.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue
        has_parametrize = any(
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "parametrize"
            for decorator in node.decorator_list
        )
        (parameterized if has_parametrize else invariants).add(node.name)
    if not parameterized or not invariants:
        raise AssertionError("repository matrix tests need parameterized and invariant nodes")
    return frozenset(parameterized), frozenset(invariants)


class PolyglotRouteCiReadinessTests(unittest.TestCase):
    def test_route_host_shells_do_not_mask_command_substitution_failures(self) -> None:
        for relative in (
            "scripts/toolchains/prepare_apple_route_ci_host.sh",
            "scripts/toolchains/install_polyglot_route_ci_toolchains.sh",
        ):
            script = (ROOT / relative).read_text(encoding="utf-8")
            completed = subprocess.run(
                ["/bin/bash", "-n"],
                input=script,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("set -euo pipefail", script)
            self.assertIsNone(
                re.search(
                    r"(?m)^\s*(?:readonly|local|declare(?:\s+-[A-Za-z]+)?)"
                    r"\s+[A-Za-z_][A-Za-z0-9_]*\s*=.*\$\(",
                    script,
                ),
                f"{relative} masks a command-substitution failure in a declaration",
            )

        prepare = (
            ROOT / "scripts/toolchains/prepare_apple_route_ci_host.sh"
        ).read_text(encoding="utf-8")
        installer = (
            ROOT / "scripts/toolchains/install_polyglot_route_ci_toolchains.sh"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'HOST_SYSTEM="$(/usr/bin/uname -s)"\nreadonly HOST_SYSTEM',
            prepare,
        )
        self.assertIn(
            'HOMEBREW_PREFIX="$(brew --prefix)"\nreadonly HOMEBREW_PREFIX',
            installer,
        )
        self.assertNotIn("done < <(brew list --formula)", installer)
        self.assertIn(
            'installed_formula_inventory="$(brew list --formula)"\n'
            "    readonly installed_formula_inventory",
            installer,
        )
        self.assertIn('done <<<"${installed_formula_inventory}"', installer)
        self.assertIn('if token == "openssl@3":', installer)
        self.assertIn('if source.count(overwrite) != 1:', installer)
        self.assertIn('source.replace(overwrite, "force: true", 1)', installer)
        self.assertIn(
            "libnghttp2/1.69.0/lib/libnghttp2.14.dylib|444|184240|"
            "9e14b36e03a09a83341d716f5bc38ed1be1fe5ef2ec74ba4c19fb20a5962615c",
            installer,
        )

        node_inventory_block = (
            '  if [[ "${token}" == "node" ]]; then'
            + installer.split('  if [[ "${token}" == "node" ]]; then', 1)[1]
            .split("\n  fi\n", 1)[0]
            + "\n  fi"
        )
        injected = subprocess.run(
            ["/bin/bash"],
            input=(
                "set -euo pipefail\n"
                "brew() {\n"
                '  if [[ "$1" == "list" && "$2" == "--formula" ]]; then\n'
                "    return 37\n"
                "  fi\n"
                "  return 0\n"
                "}\n"
                "probe() {\n"
                '  local token="node"\n'
                f"{node_inventory_block}\n"
                "  printf 'FAILURE_WAS_MASKED\\n'\n"
                "}\n"
                "probe\n"
            ),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(injected.returncode, 37, injected.stderr)
        self.assertNotIn("FAILURE_WAS_MASKED", injected.stdout)

    def test_frontend_ci_binds_exact_openssl_ed25519_runtime(self) -> None:
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        verifier = (
            ROOT / "scripts/toolchains/verify_openssl3_ci_runtime.py"
        ).read_text(encoding="utf-8")
        frontend_job = workflow.split("  frontend-client-engine:", 1)[1].split(
            "  polyglot-route-pack-contracts:", 1
        )[0]

        root_seal = frontend_job.index("- name: Root-seal OpenSSL 3 Ed25519 runtime")
        bind_runtime = frontend_job.index("- name: Bind OpenSSL 3 Ed25519 runtime")
        verify_runtime = frontend_job.index("- name: Verify bound OpenSSL runtime")
        frontend_tests = frontend_job.index("- name: Test Frontend Client Engine")
        formal_replay = frontend_job.index(
            "- name: Replay complete Batch 32 and Batch 35 formal gates"
        )
        bind_step = frontend_job.split(
            "- name: Bind OpenSSL 3 Ed25519 runtime", 1
        )[1].split("- name: Verify bound OpenSSL runtime", 1)[0]
        root_seal_step = frontend_job.split(
            "- name: Root-seal OpenSSL 3 Ed25519 runtime", 1
        )[1].split("- name: Set up Node.js 26.0.0", 1)[0]
        verify_step = frontend_job.split(
            "- name: Verify bound OpenSSL runtime", 1
        )[1].split("- name: Replay complete Batch 32 and Batch 35 formal gates", 1)[0]

        self.assertLess(root_seal, frontend_tests)
        self.assertLess(frontend_tests, bind_runtime)
        self.assertLess(bind_runtime, verify_runtime)
        self.assertLess(verify_runtime, formal_replay)
        self.assertNotIn("brew install openssl@3", frontend_job)
        self.assertIn("runs-on: macos-15", frontend_job)
        self.assertGreaterEqual(
            frontend_job.count("/opt/homebrew/Cellar/openssl@3/3.6.3/bin/openssl"),
            2,
        )
        self.assertIn(
            "os.path.realpath(sys.argv[1], strict=True)",
            frontend_job,
        )
        self.assertEqual(
            frontend_job.count(
                "python3.11 -I -B scripts/toolchains/verify_openssl3_ci_runtime.py"
            ),
            2,
        )
        for step in (bind_step, verify_step):
            self.assertEqual(
                step.count(
                    "python3.11 -I -B scripts/toolchains/verify_openssl3_ci_runtime.py"
                ),
                1,
            )
            before_verifier = step.split(
                "python3.11 -I -B scripts/toolchains/verify_openssl3_ci_runtime.py",
                1,
            )[0]
            self.assertNotIn('"${openssl_bin}" version', before_verifier)
            self.assertNotIn("$(openssl version)", before_verifier)
        self.assertEqual(frontend_job.count("--seal --image-os"), 1)
        self.assertIn(
            "/usr/bin/sudo -- /usr/bin/python3 -I -B -",
            root_seal_step,
        )
        self.assertIn(
            '--image-os "${ImageOS}" --image-version "${ImageVersion}"',
            root_seal_step,
        )
        self.assertIn(
            "<scripts/toolchains/verify_openssl3_ci_runtime.py",
            root_seal_step,
        )
        self.assertNotIn("python3.11", root_seal_step)
        self.assertNotIn("scripts/toolchains/verify_openssl3_ci_runtime.py --seal", root_seal_step)
        self.assertNotIn("/usr/bin/sudo", bind_step)
        self.assertNotIn("--seal", verify_step)
        self.assertIn("OPENSSL3_RUNTIME_RECEIPT", verifier)
        self.assertIn("OPENSSL3_ROOT_SEAL_RECEIPT", verifier)
        self.assertIn(
            "/opt/homebrew/Cellar/openssl@3/3.6.3/lib/libssl.3.dylib",
            verifier,
        )
        self.assertIn(
            "/opt/homebrew/Cellar/openssl@3/3.6.3/lib/libcrypto.3.dylib",
            verifier,
        )
        self.assertNotIn("/usr/bin/realpath", frontend_job)
        self.assertEqual(frontend_job.count("INSTALL_RECEIPT.json"), 1)
        self.assertIn('value.get("built_as_bottle") is True', frontend_job)
        self.assertIn('value.get("poured_from_bottle") is True', frontend_job)
        self.assertIn('source.get("tap") == "homebrew/core"', frontend_job)
        self.assertIn('source.get("spec") == "stable"', frontend_job)
        self.assertIn("packages.arm64_sequoia.jws.json", frontend_job)
        for pinned_value in (
            "20260829.0321.1",
            "15.7.9",
            "24G830",
            "fac6e4f037e8e9c184485de80f23df3816c0c6d8428b20a7703b6f339a72a83c",
            "5f15ad8c8519304aad18b06105f367e21d75e0812eb300e904bb3b9271ce0d0d",
            "256172ed0500c7af6f9d633b317fffe6efae0cae456eacc283a87cb2474317fb",
            "b2920ada65fae0087ed680e1cfc58c8e21a20a9a41cfc068ef4cff31eac43bd3",
            "a8f03e63667ae72e9928cafa28a677fe8cafd9c065f3ddf8c8e451682b7c59bd",
        ):
            self.assertIn(pinned_value, verifier)
        for required_control in (
            "O_NOFOLLOW",
            "opened_before = os.fstat(descriptor)",
            "opened_after = os.fstat(descriptor)",
            "before = _stable_runtime_file_receipts()",
            "after = _stable_runtime_file_receipts()",
            "OpenSSL runtime files changed during guarded external command",
            '"CODESIGN_ALLOCATE"',
            '"/usr/bin/codesign", "--verify", "--strict"',
            '"/usr/bin/otool", "-L"',
            '"/usr/bin/otool", "-D"',
            'environment["DYLD_PRINT_LIBRARIES"] = "1"',
            "before = _runtime_receipt()",
            "after = _runtime_receipt()",
            '"pkeyutl",',
            '"-sign",',
            '"-verify",',
            "UNSEALED_FILE_PROFILES",
            "SEALED_DIRECTORY_PROFILES",
            "UNSEALED_OPT_LINK_PROFILE",
            "SEALED_OPT_LINK_PROFILE",
            "os.fchown(descriptor, 0, 0)",
            "os.fchmod(descriptor, 0o755)",
            "os.chown(OPT_LINK, 0, 0, follow_symlinks=False)",
            "writable OpenSSL descriptor survived root sealing",
            "OpenSSL runtime root sealing requires effective uid 0",
        ):
            self.assertIn(required_control, verifier)
        self.assertIn(
            "inherited OpenSSL or dynamic-loader override is forbidden",
            verifier,
        )
        self.assertIn("OpenSSL runtime changed during verification", verifier)
        self.assertLess(
            verifier.index("forbidden_environment ="),
            verifier.index("before = _runtime_receipt()"),
        )
        self.assertIn(
            "printf '%s\\n' \"/opt/homebrew/Cellar/openssl@3/3.6.3/bin\" "
            '>>"${GITHUB_PATH}"',
            frontend_job,
        )
        self.assertIn('test "$(command -v openssl)" = "${openssl_bin}"', frontend_job)
        for step in (root_seal_step, bind_step):
            self.assertIn(
                'test "$(/usr/bin/sw_vers -productVersion)" = "15.7.9"',
                step,
            )
            self.assertIn(
                'test "$(/usr/bin/sw_vers -buildVersion)" = "24G830"',
                step,
            )

    def test_openssl_normal_profile_requires_root_sealed_authority(self) -> None:
        verifier_path = ROOT / "scripts/toolchains/verify_openssl3_ci_runtime.py"
        spec = importlib.util.spec_from_file_location(
            "elmos_openssl3_ci_runtime_sealed_profiles",
            verifier_path,
        )
        assert spec is not None and spec.loader is not None
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)

        self.assertEqual(len(verifier.FILE_PROFILES), 3)
        self.assertEqual(len(verifier.UNSEALED_FILE_PROFILES), 3)
        self.assertEqual(len(verifier.HOST_PROFILES), 2)
        for path, profile in verifier.FILE_PROFILES.items():
            self.assertEqual((profile["uid"], profile["gid"]), (0, 0))
            self.assertEqual(
                profile["sha256"],
                verifier.UNSEALED_FILE_PROFILES[path]["sha256"],
            )
        self.assertEqual(verifier.SEALED_OPT_LINK_PROFILE["uid"], 0)
        self.assertEqual(verifier.SEALED_OPT_LINK_PROFILE["gid"], 0)
        self.assertEqual(
            verifier.SEALED_OPT_LINK_PROFILE["target"],
            "../Cellar/openssl@3/3.6.3",
        )
        self.assertTrue(
            all(
                profile == {"mode": "0755", "uid": 0, "gid": 0}
                for profile in verifier.SEALED_DIRECTORY_PROFILES.values()
            )
        )
        self.assertEqual(
            verifier.UNSEALED_DIRECTORY_PROFILES[Path("/opt/homebrew")],
            {"mode": "0755", "uid": 501, "gid": 80},
        )

    def test_openssl_seal_mode_is_root_only_and_uses_explicit_image(self) -> None:
        verifier_path = ROOT / "scripts/toolchains/verify_openssl3_ci_runtime.py"
        spec = importlib.util.spec_from_file_location(
            "elmos_openssl3_ci_runtime_seal_mode",
            verifier_path,
        )
        assert spec is not None and spec.loader is not None
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)

        with (
            mock.patch.object(verifier.os, "geteuid", return_value=501),
            self.assertRaisesRegex(RuntimeError, "requires effective uid 0"),
        ):
            verifier._seal_runtime()

        arguments = verifier._parse_arguments(
            [
                "--seal",
                "--image-os",
                "macos15",
                "--image-version",
                "20260829.0321.1",
            ]
        )
        self.assertTrue(arguments.seal)
        self.assertEqual(arguments.image_os, "macos15")
        self.assertEqual(arguments.image_version, "20260829.0321.1")

    def test_openssl_host_contract_pins_product_and_build(self) -> None:
        verifier_path = ROOT / "scripts/toolchains/verify_openssl3_ci_runtime.py"
        spec = importlib.util.spec_from_file_location(
            "elmos_openssl3_ci_runtime_host_contract",
            verifier_path,
        )
        assert spec is not None and spec.loader is not None
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        product = subprocess.CompletedProcess(
            args=["/usr/bin/sw_vers", "-productVersion"],
            returncode=0,
            stdout="15.7.9\n",
            stderr="",
        )
        build = subprocess.CompletedProcess(
            args=["/usr/bin/sw_vers", "-buildVersion"],
            returncode=0,
            stdout="24G830\n",
            stderr="",
        )

        with (
            mock.patch.object(verifier.sys, "platform", "darwin"),
            mock.patch.object(
                verifier.os,
                "uname",
                return_value=mock.Mock(machine="arm64"),
            ),
            mock.patch.object(verifier, "_run", side_effect=(product, build)) as run_mock,
        ):
            verifier._verify_host("macos15", "20260829.0321.1")

        self.assertEqual(run_mock.call_count, 2)
        with (
            mock.patch.object(verifier.sys, "platform", "darwin"),
            mock.patch.object(
                verifier.os,
                "uname",
                return_value=mock.Mock(machine="arm64"),
            ),
            self.assertRaisesRegex(RuntimeError, "hosted image identity mismatch"),
        ):
            verifier._verify_host("macos15", "drifted")

    def test_openssl_runtime_guard_rechecks_all_three_files(self) -> None:
        verifier_path = ROOT / "scripts/toolchains/verify_openssl3_ci_runtime.py"
        spec = importlib.util.spec_from_file_location(
            "elmos_openssl3_ci_runtime_guard_verifier",
            verifier_path,
        )
        assert spec is not None and spec.loader is not None
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        completed = subprocess.CompletedProcess(
            args=["/usr/bin/otool", "-L", str(verifier.OPENSSL)],
            returncode=0,
            stdout="ok\n",
            stderr="",
        )
        stable_receipts = tuple(
            {"path": str(path), "inode": index}
            for index, path in enumerate(verifier.FILE_PROFILES, start=1)
        )

        with (
            mock.patch.object(
                verifier,
                "_stable_runtime_file_receipts",
                side_effect=(stable_receipts, stable_receipts),
            ) as receipt_mock,
            mock.patch.object(verifier, "_run", return_value=completed) as run_mock,
        ):
            observed = verifier._run_with_runtime_guard(
                list(completed.args), environment={"PATH": "/usr/bin"}
            )

        self.assertIs(observed, completed)
        self.assertEqual(receipt_mock.call_count, 2)
        run_mock.assert_called_once_with(
            list(completed.args), environment={"PATH": "/usr/bin"}
        )
        self.assertEqual(len(stable_receipts), 3)
        self.assertEqual(
            tuple(receipt["path"] for receipt in stable_receipts),
            tuple(str(path) for path in verifier.FILE_PROFILES),
        )

        drifted_receipts = (
            {**stable_receipts[0], "inode": 999},
            *stable_receipts[1:],
        )
        with (
            mock.patch.object(
                verifier,
                "_stable_runtime_file_receipts",
                side_effect=(stable_receipts, drifted_receipts),
            ),
            mock.patch.object(verifier, "_run", return_value=completed),
            self.assertRaisesRegex(
                RuntimeError,
                "runtime files changed during guarded external command",
            ),
        ):
            verifier._run_with_runtime_guard(
                list(completed.args), environment={"PATH": "/usr/bin"}
            )

    def test_openssl_root_seal_rejects_retained_writable_descriptor(self) -> None:
        verifier_path = ROOT / "scripts/toolchains/verify_openssl3_ci_runtime.py"
        spec = importlib.util.spec_from_file_location(
            "elmos_openssl3_ci_runtime_descriptor_guard",
            verifier_path,
        )
        assert spec is not None and spec.loader is not None
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        path = str(verifier.OPENSSL)
        completed = subprocess.CompletedProcess(
            args=["/usr/sbin/lsof"],
            returncode=0,
            stdout=f"p123\nf9\nau\nn{path}\n",
            stderr="",
        )
        with (
            mock.patch.object(verifier.subprocess, "run", return_value=completed),
            self.assertRaisesRegex(
                RuntimeError,
                "writable OpenSSL descriptor survived root sealing",
            ),
        ):
            verifier._reject_inherited_writable_file_descriptors()

    def test_openssl_verifier_rejects_codesign_allocate_override(self) -> None:
        verifier_path = ROOT / "scripts/toolchains/verify_openssl3_ci_runtime.py"
        spec = importlib.util.spec_from_file_location(
            "elmos_openssl3_ci_runtime_environment_verifier",
            verifier_path,
        )
        assert spec is not None and spec.loader is not None
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)

        self.assertEqual(
            verifier._forbidden_environment_names(
                {
                    "CODESIGN_ALLOCATE": "/private/tmp/untrusted",
                    "DYLD_INSERT_LIBRARIES": "/private/tmp/lib.dylib",
                    "PATH": "/usr/bin:/bin",
                }
            ),
            {"CODESIGN_ALLOCATE", "DYLD_INSERT_LIBRARIES"},
        )

    def test_openssl_actual_load_trace_rejects_shadow_libraries(self) -> None:
        verifier_path = ROOT / "scripts/toolchains/verify_openssl3_ci_runtime.py"
        spec = importlib.util.spec_from_file_location(
            "elmos_openssl3_ci_runtime_verifier",
            verifier_path,
        )
        assert spec is not None and spec.loader is not None
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        valid_trace = "\n".join(
            (
                f"dyld[1]: {verifier.LIBSSL}",
                f"dyld[1]: {verifier.LIBCRYPTO}",
            )
        )
        verifier._verify_actual_load_trace(valid_trace)

        with self.assertRaisesRegex(RuntimeError, "actual-load closure mismatch"):
            verifier._verify_actual_load_trace(
                valid_trace + "\ndyld[1]: /private/tmp/libssl.3.dylib"
            )

    def test_ci_hydrates_locked_rust_analyzer_before_offline_execution(self) -> None:
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        native_runner = (
            ROOT / "engines/polyglot-route-engine/src/elmos_polyglot_route/native.py"
        ).read_text(encoding="utf-8")

        route_engine_job = workflow.split(
            "  polyglot-route-engine-core:", 1
        )[1].split(
            "  polyglot-route-engine-matrix:", 1
        )[0]
        route_matrix_job = workflow.split(
            "  polyglot-route-engine-matrix:", 1
        )[1].split(
            "  polyglot-route-engine:", 1
        )[0]
        route_engine_gate_job = workflow.split(
            "  polyglot-route-engine:", 1
        )[1].split(
            "  polyglot-routes:", 1
        )[0]
        route_gate_job = workflow.split("  polyglot-routes:", 1)[1].split(
            "  sql-dialect-engine:", 1
        )[0]
        route_pack_job = workflow.split("  polyglot-route-pack-contracts:", 1)[1].split(
            "  polyglot-route-engine-core:", 1
        )[0]
        cargo_fetch = route_engine_job.index("cargo fetch")
        native_core_build = route_engine_job.index(
            "--manifest-path native/rust-core/Cargo.toml"
        )
        private_environment = route_engine_job.index(
            "UV_PROJECT_ENVIRONMENT=${RUNNER_TEMP}/elmos-polyglot-route-venv"
        )
        route_sync = route_engine_job.index(
            "uv --directory engines/polyglot-route-engine sync --locked"
        )
        closure_tests = route_engine_job.index(
            '"$GITHUB_WORKSPACE/tests/batch35/test_packed_replay_schema_closure.py"'
        )
        core_partition = route_engine_job.index(
            "all_test_files = sorted(tests_root.rglob(\"test_*.py\"))"
        )
        diagnostic_command = (
            'python -I -B "${GITHUB_WORKSPACE}/scripts/toolchains/'
            'diagnose_apple_route_ci.py"'
        )
        apple_diagnostic = route_engine_job.index(diagnostic_command)
        host_preparation = route_engine_job.index(
            "scripts/toolchains/prepare_apple_route_ci_host.sh"
        )
        route_provision = route_engine_job.index(
            "scripts/toolchains/install_polyglot_route_ci_toolchains.sh"
        )
        route_workers = route_engine_job + route_matrix_job
        all_route_jobs = route_pack_job + route_workers

        self.assertLess(cargo_fetch, core_partition)
        self.assertLess(cargo_fetch, native_core_build)
        self.assertLess(native_core_build, core_partition)
        self.assertLess(private_environment, route_sync)
        self.assertLess(route_sync, closure_tests)
        self.assertLess(closure_tests, core_partition)
        self.assertLess(host_preparation, apple_diagnostic)
        self.assertLess(route_sync, apple_diagnostic)
        self.assertLess(apple_diagnostic, route_provision)
        self.assertLess(apple_diagnostic, closure_tests)
        self.assertEqual(
            route_workers.count(diagnostic_command),
            2,
        )
        self.assertEqual(route_workers.count("--verify-jsonl"), 1)
        self.assertEqual(
            all_route_jobs.count(
                "scripts/toolchains/prepare_apple_route_ci_host.sh"
            ),
            3,
        )
        for job in (route_pack_job, route_engine_job, route_matrix_job):
            prepare = job.index("scripts/toolchains/prepare_apple_route_ci_host.sh")
            provision = job.index(
                "scripts/toolchains/install_polyglot_route_ci_toolchains.sh"
            )
            self.assertLess(prepare, provision)
        self.assertIn('--verify-jsonl "${diagnostic}"', route_engine_job)
        self.assertIn("timeout-minutes: 240", route_engine_job)
        self.assertNotIn("--ignore", route_engine_job)
        self.assertNotIn("--deselect", route_engine_job)
        self.assertIn(
            'matrix_file = tests_root / "test_repository_pipeline_language_matrix.py"',
            route_engine_job,
        )
        self.assertIn(
            "if not core_test_files or len(core_test_files) + 1 != len(all_test_files)",
            route_engine_job,
        )
        parameterized_tests, invariant_tests = _repository_matrix_test_inventory()
        selected_invariants = frozenset(
            re.findall(
                r"test_repository_pipeline_language_matrix\.py::(test_[A-Za-z0-9_]+)",
                route_engine_job,
            )
        )
        functions_block = route_matrix_job.split("functions = (", 1)[1].split(
            ")", 1
        )[0]
        selected_parameterized = frozenset(
            re.findall(r'"(test_[A-Za-z0-9_]+)"', functions_block)
        )
        self.assertEqual(selected_invariants, invariant_tests)
        self.assertEqual(selected_parameterized, parameterized_tests)
        self.assertEqual(
            selected_invariants | selected_parameterized,
            invariant_tests | parameterized_tests,
        )
        self.assertNotIn("pytest-xdist", route_workers)
        self.assertNotIn("--numprocesses", route_workers)
        self.assertNotIn("--dist", route_workers)
        self.assertNotRegex(route_workers, r'(?<![A-Za-z0-9_])-n(?:\s|["\'])')
        self.assertEqual(
            route_workers.count(
                '"$GITHUB_WORKSPACE/tests/batch35/test_packed_replay_schema_closure.py"'
            ),
            1,
        )
        self.assertEqual(
            route_workers.count(
                "uv --directory engines/polyglot-route-engine run --locked ruff check src tests"
            ),
            1,
        )
        self.assertEqual(
            route_workers.count(
                "uv --directory engines/polyglot-route-engine run --locked mypy src"
            ),
            1,
        )
        self.assertIn("name: Directed route engine qualification", route_engine_gate_job)
        self.assertIn("if: ${{ always() }}", route_engine_gate_job)
        self.assertIn("- polyglot-route-engine-core", route_engine_gate_job)
        self.assertIn("- polyglot-route-engine-matrix", route_engine_gate_job)
        self.assertIn(
            'test "${{ needs.polyglot-route-engine-core.result }}" = "success"',
            route_engine_gate_job,
        )
        self.assertIn(
            'test "${{ needs.polyglot-route-engine-matrix.result }}" = "success"',
            route_engine_gate_job,
        )
        self.assertIn("name: Directed language route contracts", route_gate_job)
        self.assertIn("if: ${{ always() }}", route_gate_job)
        self.assertIn(
            'test "${{ needs.polyglot-route-pack-contracts.result }}" = "success"',
            route_gate_job,
        )
        self.assertIn(
            'test "${{ needs.polyglot-route-engine.result }}" = "success"',
            route_gate_job,
        )
        self.assertNotIn("polyglot-route-engine-core", route_gate_job)
        self.assertNotIn("polyglot-route-engine-matrix", route_gate_job)
        route_pack_sync = route_pack_job.index(
            "uv --directory engines/polyglot-route-engine sync --locked"
        )
        batch29 = route_pack_job.index("make b29-skills-test")
        matrix = route_pack_job.index(
            "python scripts/operations/validate_translation_route_matrix.py"
        )
        active_route_execution = route_pack_job.index(
            "--route-set nine-language-complete-72"
        )
        php_route_execution = route_pack_job.index(
            "--route-set php-php85-active-completion-18"
        )
        route_gates = route_pack_job.index(
            "from route_sets import CORE_ROUTE_KEYS, V3_EXACT_ROUTE_KEYS"
        )
        active_route_set = route_pack_job.index(
            "--verify-route-set thirteen-language-complete-156"
        )
        historical_route_set = route_pack_job.index(
            "--verify-route-set eleven-language-complete-110"
        )
        self.assertIn("timeout-minutes: 360", route_pack_job)
        self.assertLess(route_pack_sync, batch29)
        self.assertLess(batch29, matrix)
        self.assertLess(matrix, active_route_execution)
        self.assertLess(active_route_execution, php_route_execution)
        self.assertLess(php_route_execution, route_gates)
        self.assertLess(route_gates, active_route_set)
        self.assertLess(active_route_set, historical_route_set)
        self.assertIn(
            '[sys.executable, str(gate), str(Path("routes") / route_key)]',
            route_pack_job,
        )
        self.assertIn(
            "for route_key in (*CORE_ROUTE_KEYS, *V3_EXACT_ROUTE_KEYS)",
            route_pack_job,
        )
        self.assertNotIn("for route in routes/*/", route_pack_job)
        self.assertEqual(all_route_jobs.count("swift package resolve"), 3)
        self.assertEqual(
            all_route_jobs.count("git diff --exit-code -- Package.resolved"),
            3,
        )
        self.assertNotIn("make b29-skills-test", route_engine_job)
        self.assertIn("cargo fetch \\", route_engine_job)
        self.assertIn("--locked \\", route_engine_job)
        self.assertIn(
            "--manifest-path engines/polyglot-route-engine/native/rust/Cargo.toml",
            route_engine_job,
        )
        self.assertIn("fail-fast: false", route_matrix_job)
        self.assertIn("needs: polyglot-route-engine-core", route_matrix_job)
        self.assertIn("max-parallel: 4", route_matrix_job)
        self.assertIn("timeout-minutes: 240", route_matrix_job)
        source_matrix = route_matrix_job.split("source_language:", 1)[1].split(
            "    steps:", 1
        )[0]
        configured_sources = tuple(
            line.strip()[2:]
            for line in source_matrix.splitlines()
            if line.strip().startswith("- ")
        )
        self.assertEqual(configured_sources, _supported_route_languages())
        expected_matrix_nodes = {
            (function_name, source, target)
            for function_name in parameterized_tests
            for source in configured_sources
            for target in configured_sources
            if source != target
        }
        self.assertEqual(len(expected_matrix_nodes), 312)
        self.assertEqual(len(expected_matrix_nodes) + len(invariant_tests), 315)
        self.assertIn(
            'if len(selectors) != 24 or len(set(selectors)) != 24:',
            route_matrix_job,
        )
        self.assertIn(
            'if source not in SUPPORTED_LANGUAGES:',
            route_matrix_job,
        )
        self.assertNotIn("-k", route_matrix_job)
        self.assertNotIn("--deselect", route_matrix_job)
        self.assertNotIn("continue-on-error", route_matrix_job)
        self.assertNotIn("--maxfail", route_matrix_job)
        self.assertNotIn("allow-failure", route_matrix_job)
        self.assertIn("cargo fetch \\", route_matrix_job)
        matrix_sync = route_matrix_job.index(
            "uv --directory engines/polyglot-route-engine sync --locked"
        )
        matrix_execute = route_matrix_job.index(
            '[sys.executable, "-m", "pytest", *selectors]'
        )
        self.assertLess(matrix_sync, matrix_execute)
        self.assertIn('"--offline"', native_runner)
        self.assertIn('"--locked"', native_runner)


if __name__ == "__main__":
    unittest.main()
