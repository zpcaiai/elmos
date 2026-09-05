from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/toolchains/diagnose_apple_route_ci.py"
PREPARE = ROOT / "scripts/toolchains/prepare_apple_route_ci_host.sh"


def _load_diagnostic():
    spec = importlib.util.spec_from_file_location("apple_route_diagnostic", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AppleRouteDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.diagnostic = _load_diagnostic()
        cls.validator, cls.validator_sha256 = cls.diagnostic._load_validator(ROOT)
        cls.script_sha256 = cls.diagnostic._script_sha256(ROOT)

    @classmethod
    def _identity(
        cls,
        lexical: str,
        *,
        resolved: str | None = None,
        kind: str = "directory",
        link_target: str | None = None,
    ) -> dict[str, object]:
        return {
            "lexical": lexical,
            "link_target": link_target,
            "resolved": resolved or lexical,
            "type": kind,
            "mode": "0755",
            "uid": 0,
            "gid": 0,
            "nlink": 1,
            "device": 1,
            "inode": 2,
            "bytes": 1,
            "mtime_ns": 3,
            "ctime_ns": 4,
        }

    @classmethod
    def _file_receipt(
        cls,
        *,
        kind: str,
        role: str,
        lexical: str,
        resolved: str,
        link_target: str | None,
    ) -> dict[str, object]:
        return {
            "kind": kind,
            "role": role,
            "lexical": lexical,
            "link_target": link_target,
            "lexical_identity": {
                "type": "symlink" if link_target is not None else "regular",
                "link_target": link_target,
                "mode": "0755",
                "uid": 0,
                "gid": 0,
                "nlink": 1,
                "device": 1,
                "inode": 2,
                "bytes": 1,
                "mtime_ns": 3,
                "ctime_ns": 4,
            },
            "resolved": resolved,
            "sha256": "sha256:" + "a" * 64,
            "bytes": 1,
            "mode": "0755",
            "uid": 0,
            "gid": 0,
            "nlink": 1,
        }

    @classmethod
    def _codesign(cls) -> dict[str, object]:
        return {
            "verify_returncode": 0,
            "verify_stdout": "",
            "verify_stderr": "",
            "display_returncode": 0,
            "display_stdout": "",
            "display_stderr": "",
            "cdhash_full": "b" * 64,
        }

    @classmethod
    def _valid_records(cls) -> list[dict[str, object]]:
        sdk_alias = str(cls.validator.SWIFT_SDK_ROOT)
        sdk_target = str(Path(sdk_alias).parent / "MacOSX.sdk")
        records: list[dict[str, object]] = [
            {
                "kind": "environment",
                "image_os": cls.diagnostic.EXPECTED_IMAGE_OS,
                "image_version": cls.diagnostic.EXPECTED_IMAGE_VERSION,
                "product_version": cls.diagnostic.EXPECTED_PRODUCT_VERSION,
                "build_version": cls.diagnostic.EXPECTED_BUILD_VERSION,
                "machine": "arm64",
                "validator_sha256": cls.validator_sha256,
                "xcode_version_stdout": cls.diagnostic.EXPECTED_XCODE_VERSION,
                "xcode_version_stderr": "",
                "sdk_version": "26.5",
            },
            {
                "kind": "xcode_source_normalization",
                "source": str(cls.diagnostic.HOSTED_SOURCE_XCODE_APP),
                "status": "ABSENT_AFTER_VERIFIED_RENAME",
            },
            {
                "kind": "xcode_physical",
                **cls._identity("/Applications/Xcode.app"),
                "selected_developer_lexical": (
                    "/Applications/Xcode.app/Contents/Developer"
                ),
                "selected_developer_physical": (
                    "/Applications/Xcode.app/Contents/Developer"
                ),
                "selected_developer_identity": cls._identity(
                    "/Applications/Xcode.app/Contents/Developer"
                ),
            },
            {
                "kind": "sdk_selected",
                **cls._identity(sdk_target),
            },
            {
                "kind": "sdk_spec_alias",
                **cls._identity(
                    sdk_alias,
                    resolved=sdk_target,
                    kind="symlink",
                    link_target="MacOSX.sdk",
                ),
                "target_identity": cls._identity(sdk_target),
            },
        ]
        for raw_spec in cls.validator.SWIFT_BUILD_CLOSURE_COMPONENT_SPECS:
            role, lexical, resolved, link_target = raw_spec[:4]
            records.append(
                cls._file_receipt(
                    kind="swift_component",
                    role=str(role),
                    lexical=str(lexical),
                    resolved=str(resolved),
                    link_target=link_target,
                )
            )
        for raw_spec in cls.validator.SWIFT_BUILD_CLOSURE_TREE_SPECS:
            role, lexical, resolved = raw_spec[:3]
            records.append(
                {
                    "kind": "swift_tree",
                    "role": str(role),
                    "lexical": str(lexical),
                    "link_target": None,
                    "resolved": str(resolved),
                    "sha256": "sha256:" + "c" * 64,
                    "file_count": 1,
                    "bytes": 1,
                }
            )
        apple_git = cls._file_receipt(
            kind="apple_git",
            role="apple-git",
            lexical=str(cls.validator.SWIFT_GIT_PATH),
            resolved=str(cls.validator.SWIFT_GIT_PATH),
            link_target=None,
        )
        apple_git.update(version_stdout="git version fixture\n", version_stderr="")
        records.append(apple_git)
        for role in ("sandbox-exec", "codesign"):
            records.append(
                {
                    "kind": "system_tool",
                    "role": role,
                    "lexical": f"/usr/bin/{role}",
                    "link_target": None,
                    "resolved": f"/usr/bin/{role}",
                    "sha256": "sha256:" + "d" * 64,
                    "bytes": 1,
                    "mode": "0755",
                    "uid": 0,
                    "gid": 0,
                    "nlink": 1,
                    "codesign": cls._codesign(),
                }
            )
        component_by_role = {
            str(spec[0]): spec for spec in cls.validator.SWIFT_BUILD_CLOSURE_COMPONENT_SPECS
        }
        for role, component_role in (
            ("xcrun-clang", "clang"),
            ("xcrun-swiftc", "swiftc-dispatcher"),
            ("xcrun-swift", "swift-dispatcher"),
        ):
            spec = component_by_role[component_role]
            compiler = cls._file_receipt(
                kind="compiler_tool",
                role=role,
                lexical=str(spec[1]),
                resolved=str(spec[2]),
                link_target=spec[3],
            )
            compiler.update(version_stdout="version fixture\n", version_stderr="")
            records.append(compiler)
        records.append(
            {
                "kind": "network_probe",
                "status": "UNAVAILABLE",
                "build_returncode": 1,
                "build_stdout": "",
                "build_stderr": "fixture unavailable",
                "argv": ["<sandbox-exec>", "<clang>"],
            }
        )
        return records

    @classmethod
    def _complete_payloads(cls) -> list[dict[str, object]]:
        complete = cls.diagnostic._complete_records(
            cls._valid_records(),
            validator=cls.validator,
            validator_sha256=cls.validator_sha256,
            script_sha256=cls.script_sha256,
            allow_network_not_run=False,
        )
        return cls.diagnostic._sequenced_records(complete)

    @classmethod
    def _write_payloads(
        cls, evidence: Path, payloads: list[dict[str, object]]
    ) -> None:
        evidence.write_text(
            "".join(
                json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
                for payload in payloads
            ),
            encoding="utf-8",
        )
        evidence.chmod(stat.S_IRUSR | stat.S_IWUSR)

    @classmethod
    def _reseal(cls, payloads: list[dict[str, object]]) -> None:
        payloads[-1]["records_sha256"] = cls.diagnostic._canonical_sha256(
            {"records": payloads[:-1]}
        )

    def test_canonical_tree_digest_matches_validator_algorithm(self) -> None:
        value = {
            "files": [
                {"path": "a", "sha256": "sha256:01", "bytes": 1},
                {"path": "b/c", "sha256": "sha256:02", "bytes": 2},
            ]
        }
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        self.assertEqual(
            self.diagnostic._canonical_sha256(value),
            "sha256:" + hashlib.sha256(encoded).hexdigest(),
        )

    def test_tree_receipt_sorts_paths_and_uses_validator_payload(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            physical = Path(raw).resolve(strict=True)
            tree = physical / "tree"
            (tree / "b").mkdir(parents=True)
            (tree / "b/item").write_bytes(b"second")
            (tree / "a").write_bytes(b"first")
            allowed = frozenset({os.getuid()})
            expected_files = [
                {
                    "path": "a",
                    "sha256": "sha256:" + hashlib.sha256(b"first").hexdigest(),
                    "bytes": 5,
                },
                {
                    "path": "b/item",
                    "sha256": "sha256:" + hashlib.sha256(b"second").hexdigest(),
                    "bytes": 6,
                },
            ]
            with mock.patch.object(
                self.diagnostic,
                "_xcode_directory_chain",
                return_value=(("stable",),),
            ):
                receipt = self.diagnostic._tree_receipt(
                    role="fixture",
                    lexical=tree,
                    physical_contents_root=physical,
                    allowed_uids=allowed,
                    allowed_gids=frozenset({os.getgid()}),
                )
            self.assertEqual(receipt["file_count"], 2)
            self.assertEqual(receipt["bytes"], 11)
            self.assertEqual(
                receipt["sha256"],
                self.diagnostic._canonical_sha256({"files": expected_files}),
            )

    def test_spec_mapping_rejects_paths_outside_declared_xcode_root(self) -> None:
        expected = Path("/Applications/Xcode.app/Contents")
        physical = Path("/Applications/Xcode_26.6.app/Contents")
        self.assertEqual(
            self.diagnostic._map_spec_path(
                "/Applications/Xcode.app/Contents/Developer/usr/bin/git",
                spec_contents_root=expected,
                physical_contents_root=physical,
            ),
            physical / "Developer/usr/bin/git",
        )
        with self.assertRaisesRegex(
            self.diagnostic.DiagnosticError, "escapes Xcode root"
        ):
            self.diagnostic._map_spec_path(
                "/usr/bin/git",
                spec_contents_root=expected,
                physical_contents_root=physical,
            )

    def test_stable_file_reader_rejects_symlink_and_enforces_byte_bound(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target = root / "target"
            target.write_bytes(b"abcd")
            link = root / "link"
            link.symlink_to("target")
            allowed = frozenset({os.getuid()})
            with self.assertRaisesRegex(
                self.diagnostic.DiagnosticError, "refusing to follow"
            ):
                self.diagnostic._stable_read_regular_file(
                    link,
                    maximum_bytes=10,
                    allowed_uids=allowed,
                    require_single_link=True,
                )
            with self.assertRaisesRegex(
                self.diagnostic.DiagnosticError, "unsafe file metadata"
            ):
                self.diagnostic._stable_read_regular_file(
                    target,
                    maximum_bytes=3,
                    allowed_uids=allowed,
                    require_single_link=True,
                )

    def test_stable_file_reader_rejects_fifo_before_open(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            fifo = Path(raw) / "fifo"
            os.mkfifo(fifo)
            with self.assertRaisesRegex(
                self.diagnostic.DiagnosticError, "unsafe file metadata"
            ):
                self.diagnostic._stable_read_regular_file(
                    fifo,
                    maximum_bytes=10,
                    allowed_uids=frozenset({os.getuid()}),
                    require_single_link=True,
                )

    def test_tree_discovery_rejects_symlinks_during_nofollow_walk(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "tree"
            root.mkdir(mode=0o700)
            (root / "target").write_bytes(b"fixture")
            (root / "alias").symlink_to("target")
            with self.assertRaisesRegex(
                self.diagnostic.DiagnosticError, "unsafe tree entry"
            ):
                self.diagnostic._discover_tree(
                    root,
                    allowed_uids=frozenset({os.getuid()}),
                    allowed_gids=frozenset({os.getgid()}),
                )

    def test_tree_receipt_rejects_same_path_content_drift_on_second_read(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            physical = Path(raw).resolve(strict=True)
            tree = physical / "tree"
            tree.mkdir()
            item = tree / "item"
            item.write_bytes(b"first")
            original = self.diagnostic._stable_read_regular_file
            reads = 0

            def drifting_read(path: Path, **kwargs):
                nonlocal reads
                if path == item:
                    reads += 1
                    if reads == 2:
                        item.write_bytes(b"other")
                return original(path, **kwargs)

            with (
                mock.patch.object(
                    self.diagnostic,
                    "_xcode_directory_chain",
                    return_value=(("stable",),),
                ),
                mock.patch.object(
                    self.diagnostic,
                    "_stable_read_regular_file",
                    side_effect=drifting_read,
                ),
                self.assertRaisesRegex(
                    self.diagnostic.DiagnosticError, "tree content changed"
                ),
            ):
                self.diagnostic._tree_receipt(
                    role="fixture",
                    lexical=tree,
                    physical_contents_root=physical,
                    allowed_uids=frozenset({os.getuid()}),
                    allowed_gids=frozenset({os.getgid()}),
                )

    def test_completion_record_proves_exact_inventory_and_jsonl_digest(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            evidence = Path(raw) / "diagnostic.jsonl"
            payloads = self._complete_payloads()
            self._write_payloads(evidence, payloads)
            self.diagnostic._verify_jsonl(evidence, ROOT)
            payloads[-1]["records_sha256"] = "sha256:" + "0" * 64
            self._write_payloads(evidence, payloads)
            with self.assertRaisesRegex(
                self.diagnostic.DiagnosticError, "completion record"
            ):
                self.diagnostic._verify_jsonl(evidence, ROOT)

    def test_verifier_rejects_resealed_authority_inventory_and_receipt_tampering(
        self,
    ) -> None:
        mutations = {
            "completion-validator": lambda payloads: payloads[-1].__setitem__(
                "validator_sha256", "sha256:" + "0" * 64
            ),
            "completion-script": lambda payloads: payloads[-1].__setitem__(
                "script_sha256", "sha256:" + "0" * 64
            ),
            "environment-validator": lambda payloads: payloads[0].__setitem__(
                "validator_sha256", "sha256:" + "0" * 64
            ),
            "component-role": lambda payloads: payloads[5].__setitem__(
                "role", "forged-component"
            ),
            "component-path": lambda payloads: payloads[5].__setitem__(
                "lexical", "/Applications/Xcode.app/Contents/forged"
            ),
            "component-resolved": lambda payloads: payloads[5].__setitem__(
                "resolved", "/Applications/Xcode.app/Contents/forged"
            ),
            "component-link": lambda payloads: payloads[5].__setitem__(
                "link_target", "forged"
            ),
            "component-sha": lambda payloads: payloads[5].__setitem__(
                "sha256", ""
            ),
            "component-bytes-bool": lambda payloads: payloads[5].__setitem__(
                "bytes", True
            ),
            "component-identity": lambda payloads: payloads[5].pop(
                "lexical_identity"
            ),
            "component-identity-link": lambda payloads: next(
                payload
                for payload in payloads
                if payload.get("kind") == "swift_component"
                and payload.get("link_target") is not None
            )["lexical_identity"].__setitem__("link_target", "forged"),
            "component-identity-type": lambda payloads: next(
                payload
                for payload in payloads
                if payload.get("kind") == "swift_component"
                and payload.get("link_target") is not None
            )["lexical_identity"].__setitem__("type", "regular"),
            "regular-identity-type": lambda payloads: payloads[-8][
                "lexical_identity"
            ].__setitem__("type", "symlink"),
            "sdk-canonical-root": lambda payloads: payloads[4].__setitem__(
                "lexical",
                "/Applications/Xcode_26.6.app/Contents/Developer/Platforms/"
                "MacOSX.platform/Developer/SDKs/MacOSX26.5.sdk",
            ),
            "sdk-alias-basename": lambda payloads: payloads[4].__setitem__(
                "lexical",
                "/Applications/Xcode.app/Contents/Developer/Platforms/"
                "MacOSX.platform/Developer/SDKs/Forged.sdk",
            ),
            "sdk-relative-target": lambda payloads: payloads[4].__setitem__(
                "link_target", "../MacOSX.sdk"
            ),
            "tree-role": lambda payloads: payloads[
                5 + self.diagnostic.EXPECTED_COMPONENT_COUNT
            ].__setitem__("role", "forged-tree"),
            "tree-root": lambda payloads: payloads[
                5 + self.diagnostic.EXPECTED_COMPONENT_COUNT
            ].__setitem__("resolved", "/Applications/Xcode.app/Contents/forged"),
            "system-path": lambda payloads: payloads[-7].__setitem__(
                "lexical", "/private/tmp/sandbox-exec"
            ),
            "system-codesign": lambda payloads: payloads[-7][
                "codesign"
            ].__setitem__("verify_returncode", 1),
            "system-cdhash": lambda payloads: payloads[-7]["codesign"].pop(
                "cdhash_full"
            ),
            "compiler-role": lambda payloads: payloads[-5].__setitem__(
                "role", "xcrun-forged"
            ),
            "compiler-path": lambda payloads: payloads[-5].__setitem__(
                "lexical", "/Applications/Xcode.app/Contents/forged"
            ),
        }
        with tempfile.TemporaryDirectory() as raw:
            evidence = Path(raw) / "diagnostic.jsonl"
            for name, mutate in mutations.items():
                with self.subTest(name=name):
                    payloads = copy.deepcopy(self._complete_payloads())
                    mutate(payloads)
                    self._reseal(payloads)
                    self._write_payloads(evidence, payloads)
                    with self.assertRaises(self.diagnostic.DiagnosticError):
                        self.diagnostic._verify_jsonl(evidence, ROOT)

    def test_verifier_rejects_duplicate_keys_and_nonfinite_values(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            evidence = Path(raw) / "diagnostic.jsonl"
            evidence.write_text(
                '{"schema":"x","schema":"y","sequence":0}\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                self.diagnostic.DiagnosticError, "JSONL is invalid"
            ):
                self.diagnostic._verify_jsonl(evidence, ROOT)
            evidence.write_text(
                '{"schema":"x","sequence":NaN}\n', encoding="utf-8"
            )
            with self.assertRaisesRegex(
                self.diagnostic.DiagnosticError, "JSONL is invalid"
            ):
                self.diagnostic._verify_jsonl(evidence, ROOT)

    def test_validator_is_loaded_from_stable_bytes_without_main_execution(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            validator = root / "scripts/batch29/validate_route.py"
            validator.parent.mkdir(parents=True)
            validator.write_text(
                "VALUE = 7\n"
                "if __name__ == '__main__':\n"
                "    raise RuntimeError('must not execute main')\n",
                encoding="utf-8",
            )
            module, digest = self.diagnostic._load_validator(root)
            self.assertEqual(module.VALUE, 7)
            self.assertEqual(
                digest,
                "sha256:" + hashlib.sha256(validator.read_bytes()).hexdigest(),
            )

    def test_source_keeps_diagnostic_and_certification_boundaries_explicit(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        prepare = PREPARE.read_text(encoding="utf-8")
        self.assertIn("not route certification evidence", source)
        self.assertIn("MAX_COMPONENT_BYTES = 400_000_000", source)
        self.assertIn("MAX_TREE_ENTRIES = 10_000", source)
        self.assertIn("MAX_TREE_BYTES = 1_000_000_000", source)
        self.assertIn("EXPECTED_COMPONENT_COUNT = 28", source)
        self.assertIn("EXPECTED_TREE_COUNT = 13", source)
        self.assertIn('frozenset({0})', source)
        self.assertIn("COMPLETE_DIAGNOSTIC_ONLY", source)
        self.assertIn("records_sha256", source)
        self.assertIn("O_NOFOLLOW is required", source)
        self.assertNotIn("SWIFT_GIT_SHA256 ==", source)
        self.assertNotIn("SWIFT_NETWORK_PROBE_BINARY_SHA256 ==", source)
        for exact_host_value in (
            "macos26",
            "20260831.0337.3",
            "26.6.2",
            "25G83",
            "20260728.0273.1",
            "26.5.2",
            "25F84",
            "Xcode 26.6",
            "17F113",
            "/Applications/Xcode_26.6.app",
            "MacOSX26.5.sdk",
            "MacOSX.sdk",
        ):
            self.assertIn(exact_host_value, prepare)
            self.assertIn(exact_host_value, source)
        self.assertIn("/usr/sbin/chown -R -P -x 0:0", prepare)
        self.assertIn("os.fchown(descriptor, 0, 0)", prepare)
        self.assertIn("os.fchmod(descriptor, 0o755)", prepare)
        self.assertIn("Xcode regular-file hard link escapes the bundle", prepare)
        self.assertIn("os.scandir(directory_descriptor)", prepare)
        self.assertIn("dir_fd=directory_descriptor", prepare)
        self.assertIn("metadata.st_dev != root_device", prepare)
        self.assertIn("XCODE_TREE_BEFORE", prepare)
        self.assertIn("XCODE_TREE_AFTER", prepare)
        self.assertIn("XCODE_TREE_NORMALIZED", prepare)
        self.assertIn("Xcode tree changed while ownership was sealed", prepare)
        self.assertIn(
            "Xcode inode/tree summary changed during physical normalization",
            prepare,
        )
        self.assertIn("Xcode pre-seal inventory is empty", prepare)
        self.assertIn("Prepared route temp root is empty", prepare)
        self.assertIn(
            'raw_target != "/Applications/Xcode_26.6.app"', prepare
        )
        self.assertIn("XCODE_ENTRY_IDENTITY_BEFORE", prepare)
        self.assertIn("XCODE_ENTRY_IDENTITY_AFTER", prepare)
        self.assertIn("observed != expected", prepare)
        self.assertIn("os.unlink(canonical.name, dir_fd=parent_descriptor)", prepare)
        self.assertIn("os.rename(", prepare)
        self.assertIn("src_dir_fd=parent_descriptor", prepare)
        self.assertIn("dst_dir_fd=parent_descriptor", prepare)
        self.assertIn("Xcode alias still exists after exact unlink", prepare)
        self.assertIn("Xcode source still exists after atomic rename", prepare)
        self.assertNotIn("os.replace", prepare)
        self.assertIn(
            '/usr/bin/sudo /usr/bin/xcode-select -s "${CANONICAL_DEVELOPER}"',
            prepare,
        )
        self.assertIn('|| -e "${SOURCE_XCODE_APP}"', prepare)
        self.assertIn('|| -L "${CANONICAL_XCODE_APP}"', prepare)
        self.assertNotIn("/bin/ln -sfn", prepare)
        self.assertIn(
            '/usr/bin/sudo /usr/sbin/chown -h 0:0 "${CANONICAL_XCODE_APP}"',
            prepare,
        )
        self.assertIn('! -user root -o ! -group wheel', prepare)
        self.assertIn('private.mkdir(mode=0o700)', prepare)
        self.assertIn('"TMPDIR=${PRIVATE_TMP}"', prepare)
        for line in prepare.splitlines():
            self.assertFalse(
                line.lstrip().startswith("readonly ") and "$(" in line,
                f"readonly masks command-substitution failure: {line}",
            )

        openssl_path = ROOT / "scripts/toolchains/verify_openssl3_ci_runtime.py"
        openssl_spec = importlib.util.spec_from_file_location(
            "apple_route_openssl_lsof_guard", openssl_path
        )
        assert openssl_spec is not None and openssl_spec.loader is not None
        openssl_verifier = importlib.util.module_from_spec(openssl_spec)
        openssl_spec.loader.exec_module(openssl_verifier)
        empty_result = subprocess.CompletedProcess(
            args=["/usr/sbin/lsof"], returncode=1, stdout="", stderr=""
        )
        with mock.patch.object(
            openssl_verifier.subprocess, "run", return_value=empty_result
        ):
            openssl_verifier._reject_inherited_writable_file_descriptors()
        for label, stdout, stderr in (
            ("stdout", "usage: lsof\n", ""),
            ("stderr", "", "permission denied\n"),
            ("whitespace", "", "\n"),
        ):
            with self.subTest(lsof_rc1_output=label):
                failed_result = subprocess.CompletedProcess(
                    args=["/usr/sbin/lsof"],
                    returncode=1,
                    stdout=stdout,
                    stderr=stderr,
                )
                with (
                    mock.patch.object(
                        openssl_verifier.subprocess,
                        "run",
                        return_value=failed_result,
                    ),
                    self.assertRaisesRegex(
                        RuntimeError, "failed closed with rc=1 output"
                    ),
                ):
                    openssl_verifier._reject_inherited_writable_file_descriptors()


if __name__ == "__main__":
    unittest.main()
