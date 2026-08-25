from __future__ import annotations

import hashlib
import importlib.util
import os
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ENVIRONMENT = ROOT / "scripts" / "toolchains" / "runtime_environment.py"
INSTALLER = ROOT / "scripts" / "toolchains" / "install_polyglot_route_toolchains.sh"
PIN_VERIFIER = (
    ROOT
    / "engines"
    / "polyglot-route-engine"
    / "tools"
    / "pin_kotlin_toolchain.py"
)


def _load_runtime_environment():
    spec = importlib.util.spec_from_file_location(
        "elmos_route_installer_runtime_environment",
        RUNTIME_ENVIRONMENT,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("runtime_environment module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runtime_environment = _load_runtime_environment()


def _write_fake_uname(directory: Path) -> None:
    executable = directory / "uname"
    executable.write_text(
        "#!/bin/sh\n"
        "case \"$1\" in\n"
        "  -s) printf '%s\\n' Darwin ;;\n"
        "  -m) printf '%s\\n' arm64 ;;\n"
        "  *) exit 2 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)


def _write_fake_command(directory: Path, name: str, content: str) -> Path:
    executable = directory / name
    executable.write_text(content, encoding="utf-8")
    executable.chmod(0o755)
    return executable


def _run_installer(toolchain_root: Path, fake_bin: Path) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PATH"] = os.pathsep.join((str(fake_bin), environment.get("PATH", "")))
    environment["ELMOS_POLYGLOT_ROUTE_TOOLCHAIN_ROOT"] = str(toolchain_root)
    return subprocess.run(
        [str(INSTALLER)],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_route_installer_is_selected_only_for_route_profiles(tmp_path: Path) -> None:
    route_step = [str(runtime_environment.ROUTE_INSTALLER_PATH)]

    assert route_step not in runtime_environment._install_steps("core")
    assert route_step not in runtime_environment._install_steps("synthesis")
    for profile in ("routes-macos", "all"):
        steps = runtime_environment._install_steps(profile)
        assert steps.count(route_step) == 1
        assert steps.index(route_step) > steps.index([str(runtime_environment.INSTALLER_PATH)])
        pnpm_steps = [step for step in steps if step and step[0] == "pnpm"]
        assert len(pnpm_steps) == 1
        assert "--ignore-scripts" in pnpm_steps[0]

        code, report = runtime_environment._run_install(
            runtime_environment.load_manifest(),
            profile,
            dry_run=True,
            environ={
                "PATH": os.environ.get("PATH", ""),
                "ELMOS_PROJECT_SYNTHESIS_TOOLCHAIN_ROOT": str(tmp_path / profile / "toolchains"),
            },
        )
        assert code == 0
        assert report["status"] == "DRY_RUN"
        assert route_step in report["steps"]
        assert report["managed_route_components"] == [
            "kotlin-route-2.2.20",
            "react-19.2.7-locked-packages",
        ]
        assert set(report["host_prerequisite_runtime_ids"]) == {
            "apple-clang-21",
            "objective-c-apple",
            "swift-6.3.3",
            "php-route-8.5.9",
            "flutter-3.44.1",
        }
        assert (
            "kotlin-route-2.2.20"
            not in report["host_prerequisite_runtime_ids"]
        )


def test_route_installer_is_executable_digest_pinned_and_tree_verifying() -> None:
    content = INSTALLER.read_text(encoding="utf-8")
    mode = stat.S_IMODE(INSTALLER.stat().st_mode)
    verifier = PIN_VERIFIER.read_bytes()

    assert mode == 0o755
    assert len(verifier) == 21_518
    assert hashlib.sha256(verifier).hexdigest() == (
        "60540ef44a6a8a5a2a65343868951f2dcfc0063b1cd91f1e4db46dff1b86a1ac"
    )
    assert "kotlin-compiler-${KOTLIN_VERSION}.zip" in content
    assert "81f0264c9073b5cbbdb3ff8418cf2c5dac076879fc156fa1a6462f5a5acc4420" in content
    assert "78709601" in content
    assert "60540ef44a6a8a5a2a65343868951f2dcfc0063b1cd91f1e4db46dff1b86a1ac" in content
    assert 'readonly PIN_SCRIPT_BYTES="21518"' in content
    assert "verify_pin_script_identity" in content
    assert "verify_archive_paths" in content
    assert 'unzip -Z1 "${archive}"' in content
    assert "verify_exact_install" in content
    assert "_EXPECTED_KOTLIN_TREE_SHA256" in content
    assert ".install-lock" in content
    assert 'mktemp -d "${KOTLIN_PARENT}/.elmos-polyglot-route-toolchains.XXXXXX"' in content
    assert "${TMPDIR:-/tmp}/elmos-polyglot-route-toolchains" not in content
    assert "rollback_promoted_target" in content
    assert 'mv "${KOTLIN_TARGET}" "${rollback_target}"' in content
    assert "Refusing to roll back a Kotlin target that is not the promoted directory" in content
    assert 'rm -rf -- "${KOTLIN_TARGET}"' not in content
    assert "Refusing to overwrite a non-matching Kotlin route target" in content
    assert "install_project_synthesis_toolchains.sh" not in content


def test_route_installer_rejects_conflicting_toolchain_roots(tmp_path: Path) -> None:
    environment = dict(os.environ)
    environment["ELMOS_PROJECT_SYNTHESIS_TOOLCHAIN_ROOT"] = str(
        tmp_path / "synthesis"
    )
    environment["ELMOS_POLYGLOT_ROUTE_TOOLCHAIN_ROOT"] = str(tmp_path / "routes")

    completed = subprocess.run(
        [str(INSTALLER)],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 2
    assert "toolchain roots must be identical" in completed.stderr


def test_route_installer_refuses_an_existing_nonmatching_target_without_download(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    _write_fake_uname(fake_bin)
    curl_marker = tmp_path / "curl-was-called"
    fake_curl = fake_bin / "curl"
    fake_curl.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' called >{curl_marker!s}\n"
        "exit 99\n",
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)

    toolchain_root = tmp_path / "toolchains"
    target = toolchain_root / "kotlin" / "2.2.20"
    target.mkdir(parents=True)
    sentinel = target / "user-owned.txt"
    sentinel.write_text("preserve\n", encoding="utf-8")

    completed = _run_installer(toolchain_root, fake_bin)

    assert completed.returncode == 3
    assert "Refusing to overwrite a non-matching Kotlin route target" in completed.stderr
    assert sentinel.read_text(encoding="utf-8") == "preserve\n"
    assert not curl_marker.exists()


def test_route_installer_rejects_a_bad_download_before_extraction(tmp_path: Path) -> None:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    _write_fake_uname(fake_bin)
    fake_curl = fake_bin / "curl"
    fake_curl.write_text(
        "#!/bin/sh\n"
        "destination=''\n"
        "while [ \"$#\" -gt 0 ]; do\n"
        "  if [ \"$1\" = '--output' ]; then shift; destination=$1; fi\n"
        "  shift\n"
        "done\n"
        "[ -n \"$destination\" ] || exit 2\n"
        "printf '%s\\n' tampered >\"$destination\"\n",
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)
    toolchain_root = tmp_path / "toolchains"

    completed = _run_installer(toolchain_root, fake_bin)

    assert completed.returncode == 3
    assert "Kotlin archive identity mismatch" in completed.stderr
    assert not (toolchain_root / "kotlin" / "2.2.20").exists()
    assert not (toolchain_root / "kotlin" / "2.2.20.install-lock").exists()


def test_route_installer_rolls_back_only_its_promoted_directory_on_postcheck_failure(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    _write_fake_uname(fake_bin)
    _write_fake_command(
        fake_bin,
        "curl",
        "#!/bin/sh\n"
        "destination=''\n"
        "while [ \"$#\" -gt 0 ]; do\n"
        "  if [ \"$1\" = '--output' ]; then shift; destination=$1; fi\n"
        "  shift\n"
        "done\n"
        "[ -n \"$destination\" ] || exit 2\n"
        "printf '%s\\n' fake-archive >\"$destination\"\n",
    )
    _write_fake_command(
        fake_bin,
        "wc",
        "#!/bin/sh\nprintf '%s\\n' 78709601\n",
    )
    _write_fake_command(
        fake_bin,
        "shasum",
        "#!/bin/sh\n"
        "path=''\n"
        "for argument in \"$@\"; do path=$argument; done\n"
        "case \"$path\" in\n"
        "  *pin_kotlin_toolchain.py) digest=60540ef44a6a8a5a2a65343868951f2dcfc0063b1cd91f1e4db46dff1b86a1ac ;;\n"
        "  */bin/kotlinc) digest=90750c977cc043dd2b05c69dd4e052c10377554925dd5a155e74ef732be28c7d ;;\n"
        "  */lib/kotlin-compiler.jar) digest=8546feb440ec2d59e00d475936523fcd3f528e21c7e8eb8a95e6de5044a6d496 ;;\n"
        "  */lib/kotlin-stdlib.jar) digest=8836ccffd3585fadda9901244b20d42901d2f3cd581058d8434e2ffabcf3a3e7 ;;\n"
        "  *) digest=81f0264c9073b5cbbdb3ff8418cf2c5dac076879fc156fa1a6462f5a5acc4420 ;;\n"
        "esac\n"
        "printf '%s  %s\\n' \"$digest\" \"$path\"\n",
    )
    _write_fake_command(
        fake_bin,
        "unzip",
        "#!/bin/sh\n"
        "if [ \"$1\" = '-Z1' ]; then\n"
        "  printf '%s\\n' kotlinc/ kotlinc/bin/ kotlinc/bin/kotlinc kotlinc/bin/kotlin kotlinc/lib/ kotlinc/lib/kotlin-compiler.jar kotlinc/lib/kotlin-stdlib.jar kotlinc/build.txt\n"
        "  exit 0\n"
        "fi\n"
        "destination=''\n"
        "while [ \"$#\" -gt 0 ]; do\n"
        "  if [ \"$1\" = '-d' ]; then shift; destination=$1; fi\n"
        "  shift\n"
        "done\n"
        "[ -n \"$destination\" ] || exit 2\n"
        "mkdir -p \"$destination/kotlinc/bin\" \"$destination/kotlinc/lib\"\n"
        "printf x >\"$destination/kotlinc/bin/kotlinc\"\n"
        "printf x >\"$destination/kotlinc/bin/kotlin\"\n"
        "printf x >\"$destination/kotlinc/lib/kotlin-compiler.jar\"\n"
        "printf x >\"$destination/kotlinc/lib/kotlin-stdlib.jar\"\n"
        "printf '%s\\n' 2.2.20-release-333 >\"$destination/kotlinc/build.txt\"\n",
    )
    _write_fake_command(
        fake_bin,
        "python3.12",
        "#!/bin/sh\n"
        "case \"$2\" in\n"
        "  */.elmos-polyglot-route-toolchains.*/unpack/kotlinc) ;;\n"
        "  *) exit 19 ;;\n"
        "esac\n"
        "printf '%s\\n' \\\n"
        "  \"_EXPECTED_KOTLIN_VERSION = 'kotlinc-jvm 2.2.20 (JRE 21.0.11)'\" \\\n"
        "  \"_EXPECTED_KOTLINC_EXECUTABLE_SHA256 = '90750c977cc043dd2b05c69dd4e052c10377554925dd5a155e74ef732be28c7d'\" \\\n"
        "  \"_EXPECTED_KOTLIN_COMPILER_JAR_SHA256 = '8546feb440ec2d59e00d475936523fcd3f528e21c7e8eb8a95e6de5044a6d496'\" \\\n"
        "  \"_EXPECTED_KOTLIN_STDLIB_JAR_SHA256 = '8836ccffd3585fadda9901244b20d42901d2f3cd581058d8434e2ffabcf3a3e7'\" \\\n"
        "  \"_EXPECTED_KOTLIN_TREE_SHA256 = '0f6e2cea7d2dd94f63e84a3f4be5c8252cb3a53f2abbd19fa4165fc2665082b8'\" \\\n"
        "  '_EXPECTED_KOTLIN_TREE_RECORD_COUNT = 123' \\\n"
        "  '_EXPECTED_KOTLIN_TREE_FILE_COUNT = 118' \\\n"
        "  '_EXPECTED_KOTLIN_TREE_DIRECTORY_COUNT = 5' \\\n"
        "  '_EXPECTED_KOTLIN_TREE_BYTES = 85861305' \\\n"
        "  \"_EXPECTED_KOTLIN_BUILD_NUMBER = '2.2.20-release-333'\"\n",
    )

    toolchain_root = tmp_path / "toolchains"
    completed = _run_installer(toolchain_root, fake_bin)
    kotlin_parent = toolchain_root / "kotlin"

    assert completed.returncode == 3
    assert "failed its post-promotion verification" in completed.stderr
    assert "Rolled back the newly promoted Kotlin route target" in completed.stderr
    assert not (kotlin_parent / "2.2.20").exists()
    assert not (kotlin_parent / "2.2.20.install-lock").exists()
    assert list(kotlin_parent.glob(".elmos-polyglot-route-toolchains.*")) == []
