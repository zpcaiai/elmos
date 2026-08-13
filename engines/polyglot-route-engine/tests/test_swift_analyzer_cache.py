from __future__ import annotations

import copy
import hashlib
import os
import stat
import subprocess
from pathlib import Path

import pytest

from elmos_polyglot_route import native
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.toolchains import ExactToolchain

_OBJECT_STORE_TEST_BYTES = b"standalone-object"
_OBJECT_STORE_TEST_CONTENT_SHA256 = "sha256:e574d8cfa92c7d75a6f50893003add458b47bf5aefea19b64f9cd9a2c07847fb"
_OBJECT_STORE_TEST_MANIFEST_SHA256 = "sha256:ae7cd6e625930ceeb0cddf1767067a8810a74e84e225c9524ab9368d4ee5f531"


def _object_store_test_manifest() -> tuple[tuple[object, ...], ...]:
    assert "sha256:" + hashlib.sha256(_OBJECT_STORE_TEST_BYTES).hexdigest() == _OBJECT_STORE_TEST_CONTENT_SHA256
    return (
        ("info", "directory", 1, 11, stat.S_IFDIR | 0o755, os.getuid(), os.getgid(), 2, None, None),
        ("pack", "directory", 1, 12, stat.S_IFDIR | 0o755, os.getuid(), os.getgid(), 2, None, None),
        (
            "pack/pack-test.pack",
            "file",
            1,
            13,
            stat.S_IFREG | 0o644,
            os.getuid(),
            os.getgid(),
            1,
            len(_OBJECT_STORE_TEST_BYTES),
            _OBJECT_STORE_TEST_CONTENT_SHA256,
        ),
    )


def _write_object_store_test_fixture(objects: Path) -> Path:
    info = objects / "info"
    pack = objects / "pack"
    info.mkdir(parents=True)
    pack.mkdir()
    info.chmod(0o755)
    pack.chmod(0o755)
    object_file = pack / "pack-test.pack"
    object_file.write_bytes(_OBJECT_STORE_TEST_BYTES)
    object_file.chmod(0o644)
    return object_file


def _swift_toolchain() -> ExactToolchain:
    return ExactToolchain(
        "swift",
        "test-swift",
        "/test/swiftc",
        "/test/swift",
        profile=("platform=test",),
        executable_sha256="swiftc-digest",
        auxiliary_sha256="swift-driver-digest",
    )


def _swift_probe_environment(root: Path) -> dict[str, str]:
    return {
        "PATH": os.pathsep.join(
            str(path)
            for path in (
                native._SWIFT_TOOLCHAIN_ROOT / "usr/bin",
                Path("/usr/bin"),
                Path("/bin"),
                Path("/usr/sbin"),
                Path("/sbin"),
            )
        ),
        "HOME": str((root / "home").resolve()),
        "TMPDIR": str((root / "tmp").resolve()),
        "LANG": "C",
        "LC_ALL": "C",
        "TZ": "UTC",
        "NO_COLOR": "1",
        "CLICOLOR": "0",
        "SOURCE_DATE_EPOCH": "0",
        "ZERO_AR_DATE": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        "TEST_TELEMETRY_DIR": str((root / "home" / ".elmos-go-telemetry").resolve()),
        "XDG_CACHE_HOME": str((root / "home" / ".cache").resolve()),
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "SWIFT_DETERMINISTIC_HASHING": "1",
    }


def _install_mocked_swift_network_probe_runtime(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    *,
    probe_stdout: str = "NETWORK_DENIED:1\n",
    compiler_after: dict[str, object] | None = None,
    sdk_after: tuple[object, ...] | None = None,
) -> tuple[list[list[str]], dict[str, object]]:
    compiler = {
        "role": "clang",
        "path": str(native._SWIFT_TOOLCHAIN_ROOT / "usr/bin/clang"),
        "resolved_path": str(native._SWIFT_TOOLCHAIN_ROOT / "usr/bin/clang"),
        "link_target": None,
        "sha256": "sha256:" + "a" * 64,
        "bytes": 1,
        "mode": "0755",
        "uid": 0,
        "gid": 0,
        "nlink": 1,
    }
    compiler_receipts = iter((copy.deepcopy(compiler), copy.deepcopy(compiler_after or compiler)))
    sdk_identity = ("sdk", "stable")
    sdk_identities = iter((sdk_identity, sdk_after or sdk_identity))
    sandbox = {
        "path": str(native._SANDBOX_EXEC),
        "sha256": "sha256:" + native._SANDBOX_EXEC_SHA256,
        "bytes": native._SANDBOX_EXEC_BYTES,
        "mode": "0755",
        "uid": 0,
        "gid": 0,
        "nlink": 1,
    }
    verifier = {
        "path": str(native._CODESIGN),
        "sha256": "sha256:" + native._CODESIGN_SHA256,
        "bytes": native._CODESIGN_BYTES,
        "mode": "0755",
        "uid": 0,
        "gid": 0,
        "nlink": 1,
    }
    probe_root = root / "network-probe-execution"
    sealed = probe_root / native._SANDBOX_NETWORK_PROBE_BINARY_NAME
    binary = {
        "name": native._SANDBOX_NETWORK_PROBE_BINARY_NAME,
        "path": str(sealed),
        "sha256": "sha256:" + native._SANDBOX_NETWORK_PROBE_BINARY_SHA256,
        "bytes": native._SANDBOX_NETWORK_PROBE_BINARY_BYTES,
        "mode": "0500",
        "uid": os.getuid(),
        "gid": os.getgid(),
        "nlink": 1,
        "device": 1,
        "inode": 2,
    }
    seal = {
        "policy": "private-nonwritable-execution-root-v1",
        "root": str(probe_root),
        "mode": "0500",
        "uid": os.getuid(),
        "gid": os.getgid(),
        "device": 1,
        "inode": 1,
        "binary": copy.deepcopy(binary),
    }
    mach_o = {
        "architecture": "arm64",
        "file_type": "MH_EXECUTE",
        "uuid": native._SANDBOX_NETWORK_PROBE_UUID,
        "cdhash_full": native._SANDBOX_NETWORK_PROBE_CDHASH_FULL,
        "linked_libraries": list(native._SANDBOX_NETWORK_PROBE_LINKED_LIBRARIES),
    }
    commands: list[list[str]] = []

    def verified_system_tool(path: Path, **_kwargs: object) -> tuple[dict[str, object], tuple[str, str]]:
        receipt = sandbox if path == native._SANDBOX_EXEC else verifier
        return copy.deepcopy(receipt), (str(path), "stable")

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(list(command))
        assert command[0] not in {"/usr/bin/xcrun", "/usr/bin/git", "/usr/bin/python3"}
        assert kwargs["environment"] == _swift_probe_environment(root)
        if "-std=c17" in command:
            assert kwargs["input_text"] == native._SANDBOX_NETWORK_PROBE_SOURCE
            return subprocess.CompletedProcess(command, 0, "", "")
        assert command[-1] == str(sealed)
        return subprocess.CompletedProcess(command, 0, probe_stdout, "")

    monkeypatch.setattr(native, "_verified_swift_system_tool", verified_system_tool)
    monkeypatch.setattr(native, "_verify_swift_sandbox_signature", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(native, "_swift_network_probe_compiler_receipt", lambda: next(compiler_receipts))
    monkeypatch.setattr(native, "_swift_network_probe_sdk_identity", lambda: next(sdk_identities))
    monkeypatch.setattr(
        native,
        "_verify_swift_network_probe_binary",
        lambda *_args, **_kwargs: (copy.deepcopy(binary), copy.deepcopy(mach_o)),
    )
    monkeypatch.setattr(
        native,
        "_seal_swift_network_probe_binary",
        lambda *_args, **_kwargs: (sealed, copy.deepcopy(seal), copy.deepcopy(mach_o)),
    )
    monkeypatch.setattr(
        native,
        "_verify_swift_network_probe_seal",
        lambda *_args, **_kwargs: (copy.deepcopy(binary), copy.deepcopy(mach_o)),
    )
    monkeypatch.setattr(native, "_run_swift_build_step", run)
    return commands, compiler


def test_swift_dependency_cache_key_binds_exact_version_revision_and_tree() -> None:
    assert native._swift_dependency_cache_key() == (
        f"swift-syntax-{native._SWIFT_DEPENDENCY_CACHE_KEY_SCHEMA}-"
        f"{native._SWIFT_SYNTAX_VERSION}-{native._SWIFT_SYNTAX_REVISION}-"
        f"{native._SWIFT_SYNTAX_TREE_SHA256}"
    )
    assert native._SWIFT_DEPENDENCY_CACHE_SCHEMA == "swift-dependencies-standalone-v2"


def test_swift_git_metadata_manifest_retries_one_directory_timestamp_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    metadata_root = repository / ".git"
    metadata_root.mkdir(parents=True)
    (metadata_root / "HEAD").write_text("pinned\n", encoding="utf-8")
    calls = 0

    def chain(_path: Path, _failure: str) -> tuple[tuple[object, ...], ...]:
        nonlocal calls
        calls += 1
        timestamp = 1 if calls == 1 else 2
        return (
            (
                str(metadata_root),
                1,
                2,
                stat.S_IFDIR | 0o700,
                os.getuid(),
                os.getgid(),
                timestamp,
                timestamp,
            ),
        )

    monkeypatch.setattr(native, "_verify_secure_directory_chain", chain)

    receipt = native._swift_git_metadata_manifest(repository, require_worktree=True)

    assert receipt["file_count"] == 1
    assert receipt["bytes"] == len(b"pinned\n")
    assert calls == 6


def test_swift_git_metadata_manifest_rejects_persistent_directory_timestamp_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    metadata_root = repository / ".git"
    metadata_root.mkdir(parents=True)
    (metadata_root / "HEAD").write_text("pinned\n", encoding="utf-8")
    calls = 0

    def chain(_path: Path, _failure: str) -> tuple[tuple[object, ...], ...]:
        nonlocal calls
        calls += 1
        return (
            (
                str(metadata_root),
                1,
                2,
                stat.S_IFDIR | 0o700,
                os.getuid(),
                os.getgid(),
                calls,
                calls,
            ),
        )

    monkeypatch.setattr(native, "_verify_secure_directory_chain", chain)

    with pytest.raises(RouteError, match="^SWIFT_ANALYZER_DEPENDENCY_GIT_METADATA_CHANGED$"):
        native._swift_git_metadata_manifest(repository, require_worktree=True)

    assert calls == 6


def test_swift_git_metadata_manifest_rejects_file_inode_or_content_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    metadata_root = repository / ".git"
    metadata_root.mkdir(parents=True)
    head = metadata_root / "HEAD"
    head.write_text("pinned\n", encoding="utf-8")
    calls = 0
    identity = (
        (
            str(metadata_root),
            1,
            2,
            stat.S_IFDIR | 0o700,
            os.getuid(),
            os.getgid(),
            1,
            1,
        ),
    )

    def chain(_path: Path, _failure: str) -> tuple[tuple[object, ...], ...]:
        nonlocal calls
        calls += 1
        if calls == 3:
            replacement = metadata_root / "HEAD.replacement"
            replacement.write_text("changed\n", encoding="utf-8")
            replacement.replace(head)
        return identity

    monkeypatch.setattr(native, "_verify_secure_directory_chain", chain)

    with pytest.raises(RouteError, match="^SWIFT_ANALYZER_DEPENDENCY_GIT_METADATA_CHANGED$"):
        native._swift_git_metadata_manifest(repository, require_worktree=True)

    assert calls == 4


def test_swift_toolchain_receipt_revalidation_rejects_any_full_object_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = _swift_toolchain()
    monkeypatch.setattr(
        native,
        "_swift_build_closure_receipt",
        lambda: {"schema": "test-swift-build-closure"},
    )
    monkeypatch.setattr(native, "exact_toolchain", lambda _language: expected)
    assert native._require_current_swift_toolchain(expected) == expected

    drifted = ExactToolchain(
        expected.language,
        expected.version,
        expected.executable,
        expected.auxiliary,
        profile=(*expected.profile, "sdk-path=/forged"),
        executable_sha256=expected.executable_sha256,
        auxiliary_sha256=expected.auxiliary_sha256,
    )
    monkeypatch.setattr(native, "exact_toolchain", lambda _language: drifted)
    with pytest.raises(
        RouteError,
        match="SWIFT_ANALYZER_TOOLCHAIN_CHANGED_DURING_BUILD",
    ):
        native._require_current_swift_toolchain(expected)


def test_swift_build_revalidates_toolchain_before_and_after_driver_execution() -> None:
    source = Path(native.__file__).read_text(encoding="utf-8")
    start = source.index("def _build_swift_analyzer(")
    end = source.index("\ndef _swift_toolchain_identity(", start)
    build_source = source[start:end]
    first = build_source.index("_require_current_swift_toolchain(toolchain)")
    network_before = build_source.index("_require_current_swift_network_execution_identity(", first)
    driver = build_source.index("_run_swift_build_step(", network_before)
    network_after = build_source.index(
        "_require_current_swift_network_execution_identity(",
        network_before + 1,
    )
    second = build_source.index(
        "_require_current_swift_toolchain(toolchain, expected_receipt=toolchain_receipt)",
        network_after,
    )
    receipt = build_source.index("canonical_identity =", second)
    build_error_capture = build_source.index("except RouteError as error:", driver)
    build_error_raise = build_source.index("raise build_error", network_after)
    assert first < network_before < driver < build_error_capture < network_after
    assert network_after < build_error_raise < second < receipt
    assert build_source.count("_require_current_swift_network_execution_identity(") == 2
    assert build_source.count("_require_current_swift_toolchain(") == 2


def test_swift_toolchain_revalidation_rejects_build_closure_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = _swift_toolchain()
    closure = {"schema": "baseline"}
    monkeypatch.setattr(native, "exact_toolchain", lambda _language: expected)
    monkeypatch.setattr(native, "_swift_build_closure_receipt", lambda: dict(closure))
    baseline = native._swift_toolchain_receipt(expected)
    closure["schema"] = "drifted"
    with pytest.raises(
        RouteError,
        match="SWIFT_ANALYZER_TOOLCHAIN_CHANGED_DURING_BUILD",
    ):
        native._require_current_swift_toolchain(
            expected,
            expected_receipt=baseline,
        )


def test_swift_git_receipt_ignores_hostile_xcrun_and_system_launchers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []
    file_receipt = {
        "path": str(native._APPLE_GIT),
        "sha256": "sha256:" + native._APPLE_GIT_SHA256,
        "bytes": native._APPLE_GIT_BYTES,
        "mode": "0755",
        "uid": 0,
        "gid": 0,
        "nlink": 1,
    }

    monkeypatch.setattr(
        native,
        "_verified_swift_xcode_regular_file",
        lambda *_args, **_kwargs: (copy.deepcopy(file_receipt), ("xcode-git", "stable")),
    )

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(list(command))
        if command[0] == "/usr/bin/xcrun":
            return subprocess.CompletedProcess(command, 0, "/usr/bin/git\n/usr/bin/python3\n", "")
        assert command[0] not in {"/usr/bin/git", "/usr/bin/python3"}
        return subprocess.CompletedProcess(command, 0, native._APPLE_GIT_VERSION + "\n", "")

    monkeypatch.setattr(native, "_run_swift_build_step", run)

    receipt = native._verify_apple_git(tmp_path, {"PATH": "/hostile"})

    assert receipt == {
        "path": str(native._APPLE_GIT),
        "sha256": "sha256:" + native._APPLE_GIT_SHA256,
        "version": native._APPLE_GIT_VERSION,
    }
    assert commands == [[str(native._APPLE_GIT), "--version"]]


def test_swift_dependency_clone_is_local_without_hardlinks_or_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    commands: list[list[str]] = []

    monkeypatch.setattr(native, "_verify_swift_git_repository", lambda *args, **kwargs: {"verified": True})
    identities = iter(
        (
            frozenset({(1, 1)}),
            frozenset({(1, 1)}),
            frozenset({(2, 2)}),
        )
    )
    monkeypatch.setattr(native, "_regular_file_identities", lambda _root: next(identities))

    def run_git(
        arguments: list[str],
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        command = [str(native._APPLE_GIT), *arguments]
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(native, "_run_verified_apple_git", run_git)

    assert native._clone_verified_swift_dependency(
        source,
        destination,
        root=tmp_path,
        environment={},
        source_has_worktree=True,
    ) == {"verified": True}
    clone = commands[0]
    assert all(command[0] == str(native._APPLE_GIT) for command in commands)
    assert all(command[0] not in {"/usr/bin/xcrun", "/usr/bin/git", "/usr/bin/python3"} for command in commands)
    assert clone[1:5] == ["clone", "--no-local", "--no-hardlinks", "--no-checkout"]
    assert "https://" not in " ".join(part.lower() for part in clone)
    assert "http://" not in " ".join(part.lower() for part in clone)
    assert commands[1][-3:] == ["remote", "remove", "origin"]
    assert commands[2][-3:] == ["checkout", "--detach", native._SWIFT_SYNTAX_REVISION]


def test_swift_dependency_clone_rejects_source_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    receipts = iter(
        (
            {"state": "source-before"},
            {"state": "destination"},
            {"state": "source-after"},
        )
    )
    identities = iter((frozenset({(1, 1)}), frozenset({(1, 1)})))
    monkeypatch.setattr(native, "_verify_swift_git_repository", lambda *_args, **_kwargs: next(receipts))
    monkeypatch.setattr(native, "_regular_file_identities", lambda _root: next(identities))
    monkeypatch.setattr(
        native,
        "_run_verified_apple_git",
        lambda arguments, **_kwargs: subprocess.CompletedProcess(arguments, 0, "", ""),
    )

    with pytest.raises(
        RouteError,
        match="^SWIFT_ANALYZER_DEPENDENCY_SOURCE_CHANGED_DURING_CLONE$",
    ):
        native._clone_verified_swift_dependency(
            source,
            destination,
            root=tmp_path,
            environment={},
            source_has_worktree=True,
        )


def test_swift_standalone_object_store_accepts_private_complete_storage(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    objects = repository / ".git" / "objects"
    object_file = _write_object_store_test_fixture(objects)

    _chain, identities = native._swift_standalone_object_store_identity(
        repository,
        environment={},
        require_worktree=True,
    )

    metadata = object_file.lstat()
    assert identities == frozenset({(metadata.st_dev, metadata.st_ino)})


def test_swift_standalone_object_store_rejects_alternates(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    info = repository / ".git" / "objects" / "info"
    info.mkdir(parents=True)
    (info / "alternates").write_text("/live/engine/.build/objects\n", encoding="utf-8")

    with pytest.raises(
        RouteError,
        match="^SWIFT_ANALYZER_DEPENDENCY_ALTERNATE_OBJECT_STORE_FORBIDDEN$",
    ):
        native._swift_standalone_object_store_identity(
            repository,
            environment={},
            require_worktree=True,
        )


def test_swift_standalone_object_store_rejects_hardlinked_objects(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    pack = repository / ".git" / "objects" / "pack"
    pack.mkdir(parents=True)
    first = pack / "pack-test.pack"
    first.write_bytes(b"shared-object")
    os.link(first, pack / "pack-test-copy.pack")

    with pytest.raises(
        RouteError,
        match="^SWIFT_ANALYZER_DEPENDENCY_REPOSITORY_UNSAFE$",
    ):
        native._swift_standalone_object_store_identity(
            repository,
            environment={},
            require_worktree=True,
        )


def test_swift_standalone_object_store_rejects_missing_storage(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    (repository / ".git").mkdir(parents=True)

    with pytest.raises(
        RouteError,
        match="^SWIFT_ANALYZER_DEPENDENCY_OBJECT_STORE_UNSAFE$",
    ):
        native._swift_standalone_object_store_identity(
            repository,
            environment={},
            require_worktree=True,
        )


def test_swift_standalone_object_store_rejects_entry_count_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    objects = repository / ".git" / "objects"
    _write_object_store_test_fixture(objects)
    monkeypatch.setattr(native, "_SWIFT_DEPENDENCY_OBJECT_STORE_MAXIMUM_ENTRIES", 2)

    with pytest.raises(
        RouteError,
        match="^SWIFT_ANALYZER_DEPENDENCY_OBJECT_STORE_ENTRY_LIMIT_EXCEEDED$",
    ):
        native._swift_standalone_object_store_identity(
            repository,
            environment={},
            require_worktree=True,
        )


def test_swift_standalone_object_store_rejects_aggregate_byte_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    objects = repository / ".git" / "objects"
    _write_object_store_test_fixture(objects)
    monkeypatch.setattr(
        native,
        "_SWIFT_DEPENDENCY_OBJECT_STORE_MAXIMUM_BYTES",
        len(_OBJECT_STORE_TEST_BYTES) - 1,
    )

    with pytest.raises(
        RouteError,
        match="^SWIFT_ANALYZER_DEPENDENCY_OBJECT_STORE_BYTE_LIMIT_EXCEEDED$",
    ):
        native._swift_standalone_object_store_identity(
            repository,
            environment={},
            require_worktree=True,
        )


def test_swift_standalone_object_store_rejects_directory_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    objects = repository / ".git" / "objects"
    (objects / "info").mkdir(parents=True)
    original = native._swift_object_store_manifest
    calls = 0

    def drift(root: Path) -> tuple[tuple[object, ...], ...]:
        nonlocal calls
        observed = original(root)
        calls += 1
        if calls == 1:
            (root / "drifted-object").write_bytes(b"changed")
        return observed

    monkeypatch.setattr(native, "_swift_object_store_manifest", drift)

    with pytest.raises(
        RouteError,
        match="^SWIFT_ANALYZER_DEPENDENCY_OBJECT_STORE_CHANGED$",
    ):
        native._swift_standalone_object_store_identity(
            repository,
            environment={},
            require_worktree=True,
        )


def test_swift_repository_verification_accepts_fsck_timestamp_only_churn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    objects = repository / ".git" / "objects"
    _write_object_store_test_fixture(objects)
    dependency = {
        "sha256": "sha256:" + native._SWIFT_SYNTAX_TREE_SHA256,
        "file_count": native._SWIFT_SYNTAX_TREE_FILE_COUNT,
        "bytes": native._SWIFT_SYNTAX_TREE_BYTES,
    }
    metadata = {"sha256": "sha256:metadata", "file_count": 3, "bytes": 4}
    monkeypatch.setattr(native, "_swift_git_metadata_manifest", lambda *_args, **_kwargs: metadata)
    monkeypatch.setattr(native, "_swift_dependency_tree", lambda _repository: dependency)

    def run_git(
        arguments: list[str],
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        if "fsck" in arguments:
            transient = objects / "fsck-transient.lock"
            transient.write_bytes(b"transient")
            transient.unlink()
        output = "" if arguments[-1] == "remote" else native._SWIFT_SYNTAX_REVISION + "\n"
        return subprocess.CompletedProcess(arguments, 0, output, "")

    monkeypatch.setattr(native, "_run_verified_apple_git", run_git)

    receipt = native._verify_swift_git_repository(
        repository,
        root=tmp_path,
        environment={},
        require_worktree=True,
    )

    assert receipt["object_store"] == {
        "policy": native._SWIFT_DEPENDENCY_OBJECT_STORE_POLICY,
        "alternates": False,
        "hardlinks": False,
        "manifest_schema": native._SWIFT_DEPENDENCY_OBJECT_STORE_MANIFEST_SCHEMA,
        "entry_count": 3,
        "file_count": 1,
        "bytes": len(_OBJECT_STORE_TEST_BYTES),
        "manifest_sha256": _OBJECT_STORE_TEST_MANIFEST_SHA256,
    }


@pytest.mark.parametrize("drift_kind", ("path", "content", "inode"))
def test_swift_repository_verification_rejects_object_store_manifest_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    drift_kind: str,
) -> None:
    repository = tmp_path / "repository"
    objects = repository / ".git" / "objects"
    object_file = _write_object_store_test_fixture(objects)
    pack = object_file.parent
    dependency = {
        "sha256": "sha256:" + native._SWIFT_SYNTAX_TREE_SHA256,
        "file_count": native._SWIFT_SYNTAX_TREE_FILE_COUNT,
        "bytes": native._SWIFT_SYNTAX_TREE_BYTES,
    }
    monkeypatch.setattr(
        native,
        "_swift_git_metadata_manifest",
        lambda *_args, **_kwargs: {"sha256": "sha256:metadata", "file_count": 3, "bytes": 4},
    )
    monkeypatch.setattr(native, "_swift_dependency_tree", lambda _repository: dependency)

    def run_git(
        arguments: list[str],
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        if "fsck" in arguments:
            if drift_kind == "path":
                (pack / "pack-added.pack").write_bytes(b"added-object")
            elif drift_kind == "content":
                object_file.write_bytes(b"tampered-content")
            else:
                replacement = pack / "replacement.pack"
                replacement.write_bytes(object_file.read_bytes())
                os.replace(replacement, object_file)
        output = "" if arguments[-1] == "remote" else native._SWIFT_SYNTAX_REVISION + "\n"
        return subprocess.CompletedProcess(arguments, 0, output, "")

    monkeypatch.setattr(native, "_run_verified_apple_git", run_git)

    with pytest.raises(
        RouteError,
        match="^SWIFT_ANALYZER_DEPENDENCY_OBJECT_STORE_CHANGED$",
    ):
        native._verify_swift_git_repository(
            repository,
            root=tmp_path,
            environment={},
            require_worktree=True,
        )


def test_swift_repository_verification_binds_standalone_object_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    concrete_manifest = _object_store_test_manifest()
    object_store = ((concrete_manifest, frozenset({(1, 13)})),) * 2
    stores = iter(object_store)
    commands: list[list[str]] = []
    dependency = {
        "sha256": "sha256:" + native._SWIFT_SYNTAX_TREE_SHA256,
        "file_count": native._SWIFT_SYNTAX_TREE_FILE_COUNT,
        "bytes": native._SWIFT_SYNTAX_TREE_BYTES,
    }
    metadata = {"sha256": "sha256:metadata", "file_count": 3, "bytes": 4}

    monkeypatch.setattr(native, "_verify_secure_directory_chain", lambda *_args: ())
    monkeypatch.setattr(
        native,
        "_swift_standalone_object_store_identity",
        lambda *_args, **_kwargs: next(stores),
    )
    monkeypatch.setattr(native, "_swift_git_metadata_manifest", lambda *_args, **_kwargs: metadata)
    monkeypatch.setattr(native, "_swift_dependency_tree", lambda _repository: dependency)

    def run_git(
        arguments: list[str],
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        commands.append(list(arguments))
        output = native._SWIFT_SYNTAX_REVISION + "\n" if arguments[-1] != "remote" else ""
        return subprocess.CompletedProcess(arguments, 0, output, "")

    monkeypatch.setattr(native, "_run_verified_apple_git", run_git)

    receipt = native._verify_swift_git_repository(
        repository,
        root=tmp_path,
        environment={},
        require_worktree=True,
    )

    assert receipt == {
        **dependency,
        "git_metadata": metadata,
        "object_store": {
            "policy": native._SWIFT_DEPENDENCY_OBJECT_STORE_POLICY,
            "alternates": False,
            "hardlinks": False,
            "manifest_schema": native._SWIFT_DEPENDENCY_OBJECT_STORE_MANIFEST_SCHEMA,
            "entry_count": 3,
            "file_count": 1,
            "bytes": len(_OBJECT_STORE_TEST_BYTES),
            "manifest_sha256": _OBJECT_STORE_TEST_MANIFEST_SHA256,
        },
    }
    assert commands == [
        ["-C", str(repository), "rev-parse", f"{native._SWIFT_SYNTAX_REVISION}^{{commit}}"],
        ["-C", str(repository), "fsck", "--strict", "--full", "--no-dangling"],
        ["-C", str(repository), "remote"],
        ["-C", str(repository), "rev-parse", "HEAD"],
    ]


def test_swift_dependency_cache_without_verified_offline_seed_is_not_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = tmp_path / "package"
    root = tmp_path / "root"
    cache_base = tmp_path / "cache"
    package.mkdir()
    root.mkdir()
    monkeypatch.setattr(native, "_swift_dependency_cache_base", lambda: cache_base)
    monkeypatch.setattr(native, "_swift_dependency_cache_home", lambda: tmp_path)

    with pytest.raises(RouteError, match="SWIFT_ANALYZER_DEPENDENCY_OFFLINE_SEED_NOT_RUN"):
        native._ensure_swift_dependency_cache(package, root, {})


def test_swift_dependency_cache_rejects_path_outside_bound_account_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = tmp_path / "package"
    root = tmp_path / "root"
    account_home = tmp_path / "account-home"
    cache_base = tmp_path / "outside-cache"
    for directory in (package, root, account_home):
        directory.mkdir()
    monkeypatch.setattr(native, "_swift_dependency_cache_base", lambda: cache_base)
    monkeypatch.setattr(native, "_swift_dependency_cache_home", lambda: account_home)

    with pytest.raises(RouteError, match="SWIFT_ANALYZER_DEPENDENCY_CACHE_PATH_ESCAPE"):
        native._ensure_swift_dependency_cache(package, root, {})


def test_verified_swift_dependency_cache_receipt_binds_all_identity_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = tmp_path / "package"
    root = tmp_path / "root"
    cache_base = tmp_path / "cache"
    cache = cache_base / native._swift_dependency_cache_key()
    for directory in (package, root, cache):
        directory.mkdir(parents=True, exist_ok=True)
    dependency = {
        "sha256": "sha256:" + native._SWIFT_SYNTAX_TREE_SHA256,
        "file_count": native._SWIFT_SYNTAX_TREE_FILE_COUNT,
        "bytes": native._SWIFT_SYNTAX_TREE_BYTES,
    }
    monkeypatch.setattr(native, "_swift_dependency_cache_base", lambda: cache_base)
    monkeypatch.setattr(native, "_swift_dependency_cache_home", lambda: tmp_path)
    monkeypatch.setattr(native, "_verify_swift_git_repository", lambda *args, **kwargs: dependency)

    observed_cache, receipt = native._ensure_swift_dependency_cache(package, root, {})

    assert observed_cache == cache
    assert receipt == {
        "cache_key": native._swift_dependency_cache_key(),
        "cache_schema": native._SWIFT_DEPENDENCY_CACHE_SCHEMA,
        "object_store_policy": native._SWIFT_DEPENDENCY_OBJECT_STORE_POLICY,
        "identity": native._SWIFT_DEPENDENCY_IDENTITY,
        "version": native._SWIFT_SYNTAX_VERSION,
        "revision": native._SWIFT_SYNTAX_REVISION,
        "seed": native._SWIFT_DEPENDENCY_CACHE_SEED,
        **dependency,
    }
    assert set(receipt) == {
        "cache_key",
        "cache_schema",
        "object_store_policy",
        "identity",
        "version",
        "revision",
        "seed",
        "sha256",
        "file_count",
        "bytes",
    }
    with pytest.raises(
        RouteError,
        match="SWIFT_ANALYZER_DEPENDENCY_CACHE_RECEIPT_INVALID",
    ):
        native._swift_dependency_cache_receipt(
            cache_base / "forged-cache",
            native._swift_dependency_cache_key(),
            dependency,
        )


def test_swift_dependency_mirror_receipt_is_portable_and_binds_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = tmp_path / "package"
    root = tmp_path / "root"
    cache_base = tmp_path / "cache"
    cache = cache_base / native._swift_dependency_cache_key()
    package.mkdir()
    root.mkdir()
    dependency = {
        "sha256": "sha256:" + native._SWIFT_SYNTAX_TREE_SHA256,
        "file_count": native._SWIFT_SYNTAX_TREE_FILE_COUNT,
        "bytes": native._SWIFT_SYNTAX_TREE_BYTES,
    }
    monkeypatch.setattr(native, "_swift_dependency_cache_base", lambda: cache_base)
    cache_receipt = native._swift_dependency_cache_receipt(
        cache,
        native._swift_dependency_cache_key(),
        dependency,
    )
    git_identity = {
        "path": str(native._APPLE_GIT),
        "sha256": "sha256:" + native._APPLE_GIT_SHA256,
        "version": native._APPLE_GIT_VERSION,
    }
    monkeypatch.setattr(native, "_verify_secure_directory_chain", lambda *_args: ())
    monkeypatch.setattr(native, "_verify_apple_git", lambda *_args: git_identity)
    monkeypatch.setattr(
        native,
        "_ensure_swift_dependency_cache",
        lambda *_args: (cache, cache_receipt),
    )
    monkeypatch.setattr(
        native,
        "_clone_verified_swift_dependency",
        lambda *_args, **_kwargs: dependency,
    )
    monkeypatch.setattr(
        native,
        "_verify_swift_git_repository",
        lambda *_args, **_kwargs: dependency,
    )

    _mirror, receipt = native._prepare_swift_dependency_mirror(package, root, {})

    assert receipt == {
        "seed": native._SWIFT_DEPENDENCY_CACHE_SEED,
        "cache": cache_receipt,
        "git": git_identity,
        "identity": native._SWIFT_DEPENDENCY_IDENTITY,
        "version": native._SWIFT_SYNTAX_VERSION,
        "revision": native._SWIFT_SYNTAX_REVISION,
        **dependency,
    }
    assert "absolute_path" not in receipt["cache"]
    assert receipt["cache"]["cache_key"] == native._swift_dependency_cache_key()


def test_swift_dependency_cache_rejects_symlinked_content_address(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = tmp_path / "package"
    root = tmp_path / "root"
    cache_base = tmp_path / "cache"
    outside = tmp_path / "outside"
    for directory in (package, root, cache_base, outside):
        directory.mkdir()
    (cache_base / native._swift_dependency_cache_key()).symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(native, "_swift_dependency_cache_base", lambda: cache_base)
    monkeypatch.setattr(native, "_swift_dependency_cache_home", lambda: tmp_path)

    with pytest.raises(RouteError, match="SWIFT_ANALYZER_DEPENDENCY_REPOSITORY_UNSAFE"):
        native._ensure_swift_dependency_cache(package, root, {})


def test_swift_analyzer_missing_offline_seed_is_retryable_in_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    monkeypatch.setattr(
        native,
        "_swift_analyzer_input_manifest",
        lambda _package: {"sha256": "sha256:source"},
    )

    def fail(_toolchain: ExactToolchain, _package: Path) -> tuple[Path, dict[str, object]]:
        nonlocal calls
        calls += 1
        raise RouteError("SWIFT_ANALYZER_DEPENDENCY_OFFLINE_SEED_NOT_RUN")

    monkeypatch.setattr(native, "_build_swift_analyzer", fail)
    monkeypatch.setattr(native, "_SWIFT_ANALYZER_BINARY", None)
    monkeypatch.setattr(native, "_SWIFT_ANALYZER_RECEIPT", None)
    monkeypatch.setattr(native, "_SWIFT_ANALYZER_FAILURE", None)

    for _ in range(2):
        with pytest.raises(RouteError, match="SWIFT_ANALYZER_DEPENDENCY_OFFLINE_SEED_NOT_RUN"):
            native._swift_analyzer(_swift_toolchain())

    assert calls == 2


def test_swift_analyzer_permanent_provenance_failure_is_cached_in_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    monkeypatch.setattr(
        native,
        "_swift_analyzer_input_manifest",
        lambda _package: {"sha256": "sha256:source"},
    )

    def fail(_toolchain: ExactToolchain, _package: Path) -> tuple[Path, dict[str, object]]:
        nonlocal calls
        calls += 1
        raise RouteError("SWIFT_ANALYZER_DRIVER_PROVENANCE_REQUIRED")

    monkeypatch.setattr(native, "_build_swift_analyzer", fail)
    monkeypatch.setattr(native, "_SWIFT_ANALYZER_BINARY", None)
    monkeypatch.setattr(native, "_SWIFT_ANALYZER_RECEIPT", None)
    monkeypatch.setattr(native, "_SWIFT_ANALYZER_FAILURE", None)

    for _ in range(2):
        with pytest.raises(RouteError, match="SWIFT_ANALYZER_DRIVER_PROVENANCE_REQUIRED"):
            native._swift_analyzer(_swift_toolchain())

    assert calls == 1


def test_swift_package_inputs_reject_hardlinked_source_files(tmp_path: Path) -> None:
    package = tmp_path / "package"
    source_root = package / "Sources" / "ElmosSwiftAnalyzer"
    source_root.mkdir(parents=True)
    (package / "Package.swift").write_text("// swift-tools-version: 5.9\n", encoding="utf-8")
    (package / "Package.resolved").write_text("{}\n", encoding="utf-8")
    main = source_root / "main.swift"
    main.write_text("print(1)\n", encoding="utf-8")
    os.link(main, source_root / "alias.swift")

    with pytest.raises(RouteError, match="SWIFT_ANALYZER_INPUT_UNSAFE"):
        native._swift_analyzer_input_manifest(package)


def test_swift_network_isolation_fails_closed_when_socket_probe_is_not_denied(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_mocked_swift_network_probe_runtime(
        monkeypatch,
        tmp_path,
        probe_stdout="NETWORK_ALLOWED\n",
    )

    with pytest.raises(RouteError, match="NETWORK_ISOLATION_NOT_RUN:socket-probe-result"):
        native._verified_swift_network_isolation(tmp_path, _swift_probe_environment(tmp_path))


def test_swift_network_native_probe_positive_receipt_is_exact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands, compiler = _install_mocked_swift_network_probe_runtime(monkeypatch, tmp_path)

    receipt, identity = native._verified_swift_network_isolation(
        tmp_path,
        _swift_probe_environment(tmp_path),
    )

    assert len(commands) == 2
    assert "-std=c17" in commands[0]
    assert commands[1][-1].endswith(native._SANDBOX_NETWORK_PROBE_BINARY_NAME)
    assert set(receipt["probe"]) == {
        "result",
        "source",
        "build",
        "binary",
        "execution_seal",
        "mach_o",
    }
    assert receipt["probe"]["build"] == {
        "environment_policy": "sanitized-swift-build-deterministic-v1",
        "argv": list(native._SANDBOX_NETWORK_PROBE_BUILD_ARGV),
        "environment": dict(native._SANDBOX_NETWORK_PROBE_BUILD_ENVIRONMENT),
        "compiler": compiler,
    }
    assert identity["probe_binary"] == receipt["probe"]["binary"]


def test_swift_network_native_probe_rejects_compiler_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    drifted = {
        "role": "clang",
        "path": str(native._SWIFT_TOOLCHAIN_ROOT / "usr/bin/clang"),
        "resolved_path": str(native._SWIFT_TOOLCHAIN_ROOT / "usr/bin/clang"),
        "link_target": None,
        "sha256": "sha256:" + "b" * 64,
        "bytes": 1,
        "mode": "0755",
        "uid": 0,
        "gid": 0,
        "nlink": 1,
    }
    _install_mocked_swift_network_probe_runtime(
        monkeypatch,
        tmp_path,
        compiler_after=drifted,
    )

    with pytest.raises(RouteError, match="NETWORK_ISOLATION_NOT_RUN:probe-toolchain-changed"):
        native._verified_swift_network_isolation(tmp_path, _swift_probe_environment(tmp_path))


def test_swift_network_native_probe_rejects_sdk_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_mocked_swift_network_probe_runtime(
        monkeypatch,
        tmp_path,
        sdk_after=("sdk", "drifted"),
    )

    with pytest.raises(RouteError, match="NETWORK_ISOLATION_NOT_RUN:probe-toolchain-changed"):
        native._verified_swift_network_isolation(tmp_path, _swift_probe_environment(tmp_path))


def test_swift_execution_seal_blocks_path_swap_and_detects_identity_change(tmp_path: Path) -> None:
    source = tmp_path / "source-analyzer"
    source.write_bytes(b"sealed-analyzer")
    source.chmod(0o500)
    root = tmp_path / "execution-root"
    root.mkdir(mode=0o700)
    binary, seal = native._seal_swift_analyzer_binary(source, root)
    receipt = {"binary": seal["binary"], "execution_seal": seal}
    replacement = tmp_path / "replacement"
    replacement.write_bytes(b"replacement")
    replacement.chmod(0o500)
    try:
        assert native._verify_swift_execution_seal(binary, receipt)["binary"] == seal["binary"]
        with pytest.raises(OSError):
            replacement.replace(binary)
        tampered = copy.deepcopy(receipt)
        tampered["execution_seal"]["inode"] += 1
        with pytest.raises(RouteError, match="SWIFT_ANALYZER_EXECUTION_SEAL_CHANGED"):
            native._verify_swift_execution_seal(binary, tampered)
    finally:
        root.chmod(0o700)
