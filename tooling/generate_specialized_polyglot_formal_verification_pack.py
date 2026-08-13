#!/usr/bin/env python3
"""Build the exact eight-route C++/Objective-C/Swift/Java formal pack.

This generator deliberately consumes only already executed, byte-bound Batch 29
route evidence.  It does not infer a four-language complete matrix, does not
touch the legacy exact-30 pack, and cannot promote local assumption-bound proof
to certification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib
import urllib.parse
import urllib.request
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

import generate_polyglot_formal_verification_pack as base


ROOT = Path(__file__).resolve().parents[1]
PACK_KEY = "polyglot-specialized-8-route-formal-equivalence-v1"
SEMANTIC_PROFILE = "typed-pure-function-v1"
MODULE_PROFILE = "typed-pure-module-v1"
INPUT_DOMAIN = "canonical-finite-no-error-input-domain"
LANGUAGES = ("cpp", "objc", "swift", "java")
EXACT_ROUTE_KEYS = (
    "cpp-to-objc",
    "objc-to-cpp",
    "cpp-to-swift",
    "swift-to-cpp",
    "objc-to-swift",
    "swift-to-objc",
    "cpp-to-java",
    "java-to-cpp",
)
SWIFT_DEPENDENCY_TREE = {
    "identity": "swift-syntax",
    "version": "600.0.1",
    "revision": "0687f71944021d616d34d922343dcef086855920",
    "sha256": "sha256:b78ec1b227a6cbe43ca239585f66907e50485b9119f96b5461bfc888f0e5f45d",
    "file_count": 753,
    "bytes": 8_866_479,
}
SWIFT_DEPENDENCY_SEED = "verified-content-addressed-cache"
SWIFT_DEPENDENCY_CACHE_KEY = (
    "swift-syntax-600.0.1-0687f71944021d616d34d922343dcef086855920-"
    "b78ec1b227a6cbe43ca239585f66907e50485b9119f96b5461bfc888f0e5f45d"
)
SWIFT_CACHE_KEYS = {
    "cache_key",
    "cache_schema",
    "identity",
    "version",
    "revision",
    "seed",
    "sha256",
    "file_count",
    "bytes",
}
SWIFT_MIRROR_KEYS = {
    "seed",
    "cache",
    "git",
    "identity",
    "version",
    "revision",
    "sha256",
    "file_count",
    "bytes",
}
SWIFT_GIT_IDENTITY = {
    "path": "/Applications/Xcode.app/Contents/Developer/usr/bin/git",
    "sha256": "sha256:10f9c1df894525ae4c7454258febab6d3d25071062b42cb48dbb1842cdffd2a9",
    "version": "git version 2.50.1 (Apple Git-155)",
}
BLOCKS = (
    "signature-types-and-names",
    "typed-literals",
    "integer-arithmetic-safe-domain",
    "finite-number-transport-and-comparison",
    "boolean-short-circuit-and-branch",
    "if-else-path-conditions",
    "return-and-totality",
    "concrete-source-spans",
    "module-composition",
    "string-semantics",
    "finite-number-arithmetic",
    "out-of-domain-arithmetic-errors",
)
LOCALLY_EXERCISED_BLOCKS = frozenset(BLOCKS[:9])
ARITHMETIC_EVIDENCE_ID = "arithmetic-campaign"
ARITHMETIC_EVIDENCE_BLOCKS = frozenset(
    {
        "integer-arithmetic-safe-domain",
        "out-of-domain-arithmetic-errors",
    }
)
PACKED_REPLAY_COMMAND = [
    "python",
    "-I",
    "-B",
    "certification/replay/validate_packed_route.py",
    "--route",
    ".",
]
PACKED_REPLAY_FILES = {
    "certification/replay/validate_packed_route.py": (
        "scripts/batch35/validate_packed_route.py",
        "replay-tool",
        "launcher",
    ),
    "certification/replay/scripts/batch29/validate_route.py": (
        "scripts/batch29/validate_route.py",
        "replay-tool",
        "validator",
    ),
    "certification/replay/schemas/batch29/formal-equivalence-evidence.schema.json": (
        "schemas/batch29/formal-equivalence-evidence.schema.json",
        "replay-schema",
        "schema",
    ),
    "certification/replay/schemas/batch29/formal-input.schema.json": (
        "schemas/batch29/formal-input.schema.json",
        "replay-schema",
        "formal_input_schema",
    ),
    "certification/replay/schemas/batch29/identifier-plan.schema.json": (
        "schemas/batch29/identifier-plan.schema.json",
        "replay-schema",
        "identifier_plan_schema",
    ),
    "certification/replay/schemas/batch29/module-equivalence-evidence.schema.json": (
        "schemas/batch29/module-equivalence-evidence.schema.json",
        "replay-schema",
        "module_schema",
    ),
    "certification/replay/schemas/batch29/module-case-manifest.schema.json": (
        "schemas/batch29/module-case-manifest.schema.json",
        "replay-schema",
        "module_case_schema",
    ),
    "certification/replay/schemas/batch29/formal-input-module-function.schema.json": (
        "schemas/batch29/formal-input-module-function.schema.json",
        "replay-schema",
        "module_formal_input_schema",
    ),
}

PACKED_RUNTIME_EVIDENCE_ID = "packed-replay-runtime"
PACKED_RUNTIME_MANIFEST = "runtime/packed-replay-runtime.json"
PACKED_RUNTIME_LOCK = "runtime/uv.lock"
PRODUCTION_LOCK_SHA256 = (
    "sha256:59b8aa440f92f865671ddcdd0badc75ac55c9e86c6ef1ac92449f99cfbd87497"
)
PRODUCTION_LOCK_BYTES = 26_669
PYTHON_ARCHIVE_NAME = (
    "cpython-3.12.12+20260211-aarch64-apple-darwin-install_only_stripped.tar.gz"
)
PYTHON_ARCHIVE_PATH = f"runtime/{PYTHON_ARCHIVE_NAME}"
PYTHON_ARCHIVE_URL = (
    "https://releases.astral.sh/github/python-build-standalone/releases/download/"
    "20260211/cpython-3.12.12%2B20260211-aarch64-apple-darwin-"
    "install_only_stripped.tar.gz"
)
PYTHON_ARCHIVE_SHA256 = (
    "sha256:22625deaf5757e7c266cf1a096c9151a06b598b1e14632a2ec9993d58ec5fe84"
)
PYTHON_ARCHIVE_BYTES = 17_667_661
PYTHON_TREE_SHA256 = (
    "sha256:1400403c757cb4da3ce2df42d17d02e1368c54afd46bbed71ae84e25d081a154"
)
PYTHON_TREE_FILE_COUNT = 1_890
PYTHON_TREE_SYMLINKS = {
    "bin/2to3": "2to3-3.12",
    "bin/idle3": "idle3.12",
    "bin/pydoc3": "pydoc3.12",
    "bin/python": "python3.12",
    "bin/python3": "python3.12",
    "bin/python3-config": "python3.12-config",
    "lib/pkgconfig/python3-embed.pc": "python-3.12-embed.pc",
    "lib/pkgconfig/python3.pc": "python-3.12.pc",
    "share/man/man1/python3.1": "python3.12.1",
}
PYTHON_TREE_BYTES = 47_880_708
PRODUCTION_PACKAGE_NAMES = frozenset(
    {
        "attrs",
        "jsonschema",
        "jsonschema-specifications",
        "referencing",
        "rpds-py",
        "typing-extensions",
        "z3-solver",
    }
)
PRODUCTION_WHEEL_FILENAMES = {
    "attrs": "attrs-26.1.0-py3-none-any.whl",
    "jsonschema": "jsonschema-4.25.1-py3-none-any.whl",
    "jsonschema-specifications": (
        "jsonschema_specifications-2025.9.1-py3-none-any.whl"
    ),
    "referencing": "referencing-0.37.0-py3-none-any.whl",
    "rpds-py": "rpds_py-2026.6.3-cp312-cp312-macosx_11_0_arm64.whl",
    "typing-extensions": "typing_extensions-4.16.0-py3-none-any.whl",
    "z3-solver": "z3_solver-4.16.0.0-py3-none-macosx_15_0_arm64.whl",
}


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _safe_archive_member(name: str) -> str:
    if not name or "\\" in name or name.startswith("/"):
        raise RuntimeError("PACKED_RUNTIME_PYTHON_ARCHIVE_PATH_INVALID")
    normalized = name.rstrip("/")
    parts = PurePosixPath(normalized).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise RuntimeError("PACKED_RUNTIME_PYTHON_ARCHIVE_PATH_INVALID")
    if len(parts) < 2 or parts[0] != "python":
        raise RuntimeError("PACKED_RUNTIME_PYTHON_ARCHIVE_ROOT_INVALID")
    return PurePosixPath(*parts[1:]).as_posix()


def python_archive_inventory(archive: Path) -> dict[str, Any]:
    """Derive the exact stripped CPython tree without trusting extracted paths."""

    records: list[dict[str, Any]] = []
    names: set[str] = set()
    with tarfile.open(archive, mode="r:gz") as bundle:
        for member in bundle.getmembers():
            relative = _safe_archive_member(member.name)
            if relative in names:
                raise RuntimeError("PACKED_RUNTIME_PYTHON_ARCHIVE_DUPLICATE")
            names.add(relative)
            if member.isfile():
                stream = bundle.extractfile(member)
                if stream is None:
                    raise RuntimeError("PACKED_RUNTIME_PYTHON_ARCHIVE_FILE_INVALID")
                content = stream.read()
                records.append(
                    {
                        "bytes": len(content),
                        "kind": "file",
                        "mode": f"{member.mode:04o}",
                        "path": relative,
                        "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
                    }
                )
            elif member.issym():
                target = member.linkname
                if not target or "\\" in target or target.startswith("/"):
                    raise RuntimeError("PACKED_RUNTIME_PYTHON_SYMLINK_INVALID")
                resolved_target = posixpath.normpath(
                    posixpath.join(posixpath.dirname(relative), target)
                )
                if resolved_target == ".." or resolved_target.startswith("../"):
                    raise RuntimeError("PACKED_RUNTIME_PYTHON_SYMLINK_ESCAPE")
                records.append(
                    {
                        "kind": "symlink",
                        "mode": f"{member.mode:04o}",
                        "path": relative,
                        "target": target,
                    }
                )
            elif member.isdir():
                records.append(
                    {
                        "kind": "directory",
                        "mode": f"{member.mode:04o}",
                        "path": relative,
                    }
                )
            else:
                raise RuntimeError("PACKED_RUNTIME_PYTHON_ARCHIVE_SPECIAL_FILE")
    records.sort(key=lambda item: item["path"])
    return {
        "inventory_sha256": _canonical_digest(records),
        "record_count": len(records),
        "regular_file_count": sum(item["kind"] == "file" for item in records),
        "regular_file_bytes": sum(
            int(item.get("bytes", 0)) for item in records if item["kind"] == "file"
        ),
        "symlinks": {
            item["path"]: item["target"]
            for item in records
            if item["kind"] == "symlink"
        },
    }


def _normalized_package_name(value: str) -> str:
    return value.lower().replace("_", "-")


def production_wheels_from_lock(lock_path: Path) -> list[dict[str, Any]]:
    """Independently close production dependencies and select exact arm64 wheels."""

    lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    packages = lock.get("package")
    if not isinstance(packages, list):
        raise RuntimeError("PACKED_RUNTIME_LOCK_PACKAGES_INVALID")
    by_name: dict[str, dict[str, Any]] = {}
    project: dict[str, Any] | None = None
    for item in packages:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise RuntimeError("PACKED_RUNTIME_LOCK_PACKAGE_INVALID")
        name = _normalized_package_name(item["name"])
        if name in by_name:
            raise RuntimeError("PACKED_RUNTIME_LOCK_PACKAGE_DUPLICATE")
        by_name[name] = item
        source = item.get("source")
        if isinstance(source, dict) and source.get("editable") == ".":
            if project is not None:
                raise RuntimeError("PACKED_RUNTIME_LOCK_PROJECT_DUPLICATE")
            project = item
    if project is None:
        raise RuntimeError("PACKED_RUNTIME_LOCK_PROJECT_MISSING")
    pending = [
        _normalized_package_name(item["name"])
        for item in project.get("dependencies", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    ]
    closure: set[str] = set()
    while pending:
        name = pending.pop()
        if name in closure:
            continue
        package = by_name.get(name)
        if package is None:
            raise RuntimeError("PACKED_RUNTIME_LOCK_DEPENDENCY_MISSING")
        closure.add(name)
        pending.extend(
            _normalized_package_name(item["name"])
            for item in package.get("dependencies", [])
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        )
    if closure != PRODUCTION_PACKAGE_NAMES:
        raise RuntimeError("PACKED_RUNTIME_LOCK_PRODUCTION_CLOSURE_INVALID")

    selected: list[dict[str, Any]] = []
    for name in sorted(closure):
        package = by_name[name]
        expected_filename = PRODUCTION_WHEEL_FILENAMES[name]
        candidates = []
        for wheel in package.get("wheels", []):
            if not isinstance(wheel, dict) or not isinstance(wheel.get("url"), str):
                continue
            filename = urllib.parse.unquote(
                PurePosixPath(urllib.parse.urlparse(wheel["url"]).path).name
            )
            if filename == expected_filename:
                candidates.append(wheel)
        if len(candidates) != 1:
            raise RuntimeError("PACKED_RUNTIME_LOCK_WHEEL_SELECTION_INVALID")
        wheel = candidates[0]
        digest = wheel.get("hash")
        size = wheel.get("size")
        version = package.get("version")
        if (
            not isinstance(digest, str)
            or not digest.startswith("sha256:")
            or not isinstance(size, int)
            or size <= 0
            or not isinstance(version, str)
        ):
            raise RuntimeError("PACKED_RUNTIME_LOCK_WHEEL_METADATA_INVALID")
        selected.append(
            {
                "name": name,
                "version": version,
                "dependencies": sorted(
                    _normalized_package_name(item["name"])
                    for item in package.get("dependencies", [])
                    if isinstance(item, dict) and isinstance(item.get("name"), str)
                ),
                "filename": expected_filename,
                "path": f"runtime/wheelhouse/{expected_filename}",
                "url": wheel["url"],
                "sha256": digest,
                "bytes": size,
            }
        )
    return selected


def _copy_or_fetch_runtime_file(
    *,
    source: Path | None,
    url: str,
    target: Path,
    expected_sha256: str,
    expected_bytes: int,
) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if source is not None:
        base.copy_file(source, target)
    else:
        last_error: Exception | None = None
        for attempt in range(3):
            temporary = target.with_name(f".{target.name}.download-{attempt}")
            try:
                request = urllib.request.Request(
                    url,
                    headers={"User-Agent": "ELMOS-packed-runtime/1"},
                )
                with urllib.request.urlopen(request, timeout=60) as response:
                    with temporary.open("wb") as output:
                        shutil.copyfileobj(response, output, length=1024 * 1024)
                os.replace(temporary, target)
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                temporary.unlink(missing_ok=True)
                if attempt < 2:
                    time.sleep(2**attempt)
        if last_error is not None:
            raise RuntimeError("PACKED_RUNTIME_DOWNLOAD_FAILED") from last_error
    if (
        base.digest_file(target) != expected_sha256
        or target.stat().st_size != expected_bytes
    ):
        raise RuntimeError("PACKED_RUNTIME_DOWNLOAD_IDENTITY_MISMATCH")


def prepare_packed_runtime(
    pack: Path,
    repo_root: Path,
    runtime_cache: Path | None,
) -> Path:
    """Create one pack-level offline runtime closure before route validation."""

    lock_source = repo_root / "engines" / "polyglot-route-engine" / "uv.lock"
    lock_target = pack / PACKED_RUNTIME_LOCK
    base.copy_file(lock_source, lock_target)
    if (
        base.digest_file(lock_target) != PRODUCTION_LOCK_SHA256
        or lock_target.stat().st_size != PRODUCTION_LOCK_BYTES
    ):
        raise RuntimeError("PACKED_RUNTIME_LOCK_IDENTITY_MISMATCH")
    wheels = production_wheels_from_lock(lock_target)
    cache_root = runtime_cache.resolve(strict=True) if runtime_cache else None
    archive_source = cache_root / PYTHON_ARCHIVE_NAME if cache_root else None
    if archive_source is not None and not archive_source.is_file():
        raise RuntimeError("PACKED_RUNTIME_CACHE_ARCHIVE_MISSING")
    archive_target = pack / PYTHON_ARCHIVE_PATH
    _copy_or_fetch_runtime_file(
        source=archive_source,
        url=PYTHON_ARCHIVE_URL,
        target=archive_target,
        expected_sha256=PYTHON_ARCHIVE_SHA256,
        expected_bytes=PYTHON_ARCHIVE_BYTES,
    )
    inventory = python_archive_inventory(archive_target)
    if inventory != {
        "inventory_sha256": PYTHON_TREE_SHA256,
        "record_count": PYTHON_TREE_FILE_COUNT + len(PYTHON_TREE_SYMLINKS),
        "regular_file_count": PYTHON_TREE_FILE_COUNT,
        "regular_file_bytes": PYTHON_TREE_BYTES,
        "symlinks": PYTHON_TREE_SYMLINKS,
    }:
        raise RuntimeError("PACKED_RUNTIME_PYTHON_TREE_IDENTITY_MISMATCH")

    for wheel in wheels:
        cached_wheel = None
        if cache_root is not None:
            candidates = (
                cache_root / "wheelhouse" / wheel["filename"],
                cache_root / wheel["filename"],
            )
            cached_wheel = next((item for item in candidates if item.is_file()), None)
            if cached_wheel is None:
                raise RuntimeError("PACKED_RUNTIME_CACHE_WHEEL_MISSING")
        _copy_or_fetch_runtime_file(
            source=cached_wheel,
            url=wheel["url"],
            target=pack / wheel["path"],
            expected_sha256=wheel["sha256"],
            expected_bytes=wheel["bytes"],
        )

    runtime = {
        "schema_version": 1,
        "runtime_key": "macos-aarch64-cpython-3.12.12-z3-4.16.0",
        "scope": "offline-evidence-integrity-and-semantic-closure-only",
        "replay_command": list(PACKED_REPLAY_COMMAND),
        "python_archive": {
            "path": PYTHON_ARCHIVE_PATH,
            "url": PYTHON_ARCHIVE_URL,
            "sha256": PYTHON_ARCHIVE_SHA256,
            "bytes": PYTHON_ARCHIVE_BYTES,
            "implementation": "cpython",
            "version": "3.12.12",
            "build": "20260211",
            "platform": "macos-aarch64-none",
            "tree": inventory,
        },
        "production_lock": {
            "path": PACKED_RUNTIME_LOCK,
            "sha256": PRODUCTION_LOCK_SHA256,
            "bytes": PRODUCTION_LOCK_BYTES,
            "resolution": "independent-transitive-production-closure",
        },
        "wheelhouse": {
            "package_count": len(wheels),
            "install_policy": {
                "offline": True,
                "no_index": True,
                "require_hashes": True,
                "no_dependencies": True,
                "link_mode": "copy",
            },
            "packages": wheels,
        },
        "uv": {
            "path": "/opt/homebrew/Cellar/uv/0.11.16/bin/uv",
            "sha256": "sha256:d4182a7bba32f331b2c5a74568cf1c88aa50f31fe643a2c56118c6610db0aff0",
            "bytes": 46_541_136,
            "version": "uv 0.11.16 (Homebrew 2026-05-21 aarch64-apple-darwin)",
        },
        "sandbox": {
            "path": "/usr/bin/sandbox-exec",
            "sha256": "sha256:e3d7a792c58a5d3783d2f7274c82d70062393830d8cb1ded713ca554a470bd2f",
            "bytes": 102_368,
            "mode": "100755",
            "uid": 0,
            "gid": 0,
            "profile": "(version 1)\n(allow default)\n(deny network*)\n",
            "profile_sha256": "sha256:5c358b8d847211333e7ba22df82d84f796b5f30a41a2682209a949d783adbd08",
            "socket_denial_probe": "SOCKET_DENIED:1",
        },
        "environment": {
            "policy": "explicit-private-allowlist",
            "private_home": True,
            "private_tmp": True,
            "private_cache": True,
            "proxy_variables": [],
        },
        "native_route_reexecution": "NOT_RUN",
        "independent_verification": "NOT_RUN",
        "external_certification": "NOT_CERTIFIED",
    }
    manifest = pack / PACKED_RUNTIME_MANIFEST
    base.write_json(manifest, runtime)
    return manifest


def configure_base(repo_root: Path) -> None:
    """Configure the shared immutable-pack helpers for this explicit route set."""

    global ROOT
    ROOT = repo_root.resolve()
    base.ROOT = ROOT
    base.PACK_KEY = PACK_KEY
    base.LANGUAGES = LANGUAGES
    base.BLOCKS = BLOCKS
    base.LOCALLY_EXERCISED_BLOCKS = LOCALLY_EXERCISED_BLOCKS
    base.PACKED_REPLAY_COMMAND = PACKED_REPLAY_COMMAND
    base.PACKED_REPLAY_FILES = PACKED_REPLAY_FILES


def exact_routes() -> list[tuple[str, str, str]]:
    routes: list[tuple[str, str, str]] = []
    for route_key in EXACT_ROUTE_KEYS:
        source, target = route_key.split("-to-", 1)
        routes.append((route_key, source, target))
    return routes


def validate_portable_swift_receipt(route: Path, reference: dict[str, Any]) -> None:
    """Recheck the complete receipt boundary before packaging it."""

    relative = reference.get("path")
    if relative != "certification/formal-artifacts/swift-analyzer-build-receipt.json":
        raise RuntimeError(f"SWIFT_ANALYZER_RECEIPT_PATH_INVALID:{route.name}")
    receipt_path = route / relative
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    validator_directory = ROOT / "scripts" / "batch29"
    validator_directory_value = str(validator_directory)
    if validator_directory_value not in sys.path:
        sys.path.insert(0, validator_directory_value)
    from validate_route import _validate_swift_analyzer_receipt_document

    failures: list[str] = []
    validated = _validate_swift_analyzer_receipt_document(
        receipt,
        label=f"{route.name} Swift analyzer build receipt",
        failures=failures,
    )
    if validated is None or failures:
        detail = " | ".join(failures) if failures else "unknown receipt failure"
        raise RuntimeError(f"SWIFT_ANALYZER_RECEIPT_INVALID:{route.name}:{detail}")


def validate_source_routes(repo_root: Path) -> None:
    validator = repo_root / "scripts" / "batch29" / "validate_route.py"
    if not validator.is_file():
        raise RuntimeError(f"BATCH29_VALIDATOR_MISSING:{validator}")
    for route_key, _, _ in exact_routes():
        completed = subprocess.run(
            [sys.executable, str(validator), str(repo_root / "routes" / route_key)],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(f"BATCH29_ROUTE_INVALID:{route_key}:{detail}")


def copy_module_closure(
    route: Path,
    target_root: Path,
    certification: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    module_ref = certification.get("module_equivalence")
    if not isinstance(module_ref, dict):
        raise RuntimeError(f"MODULE_EQUIVALENCE_REQUIRED:{route.name}")
    module_relative = module_ref.get("path")
    if module_relative != "certification/module-equivalence.json":
        raise RuntimeError(f"MODULE_REFERENCE_INVALID:{route.name}")
    module_path = base.route_relative_file(
        route, module_relative, label=f"{route.name}_MODULE_WRAPPER"
    )
    if base.digest_file(module_path) != module_ref.get(
        "sha256"
    ) or module_path.stat().st_size != module_ref.get("bytes"):
        raise RuntimeError(f"MODULE_REFERENCE_TAMPERED:{route.name}")
    module = base.load_json(module_path)
    if (
        module.get("profile") != MODULE_PROFILE
        or module.get("local_verification_status") != "PASSED"
        or module.get("status") != "PASSED"
        or module.get("certification_status") != "NOT_CERTIFIED"
        or module.get("external_verification_status") != "NOT_RUN"
    ):
        raise RuntimeError(f"MODULE_STATUS_BOUNDARY_INVALID:{route.name}")
    contract = module.get("module_contract")
    independence = contract.get("independence") if isinstance(contract, dict) else None
    composition = module.get("composition")
    module_input = module.get("module_input")
    whole_file_closure = module.get("whole_file_closure")
    if (
        not isinstance(contract, dict)
        or contract.get("exact_profile_symbol_set") is not True
        or contract.get("exact_generated_helper_symbol_set") is not True
        or contract.get("exact_profile_signature_set") is not True
        or not isinstance(contract.get("whole_file_closure_sha256"), str)
        or not isinstance(independence, dict)
        or not isinstance(whole_file_closure, dict)
        or contract.get("verified_language_prelude")
        != whole_file_closure.get("verified_language_prelude")
        or contract.get("verified_language_wrapper")
        != whole_file_closure.get("verified_language_wrapper")
        or independence.get("source_user_call_graph_closure") != "EMPTY_AND_CLOSED"
        or independence.get("source_user_call_graph_edges") != []
        or independence.get("target_call_graph_policy")
        != "UNSUPPORTED_EXCEPT_EXACT_EMITTER_HELPERS"
        or independence.get("target_call_graph")
        != whole_file_closure.get("target_call_graph")
        or independence.get("shared_state") != "ABSENT_BY_IR_CONSTRUCTION"
        or not isinstance(composition, dict)
        or composition.get("input_domain") != INPUT_DOMAIN
        or composition.get("target_profile_to_emitted_call_graph_status")
        != "EXACT_EMITTER_HELPERS_AND_PINNED_BUILTINS"
        or composition.get("target_profile_to_emitted_call_graph_scope")
        != "profile-functions-to-emitted-callees"
        or not isinstance(module_input, dict)
        or module_input.get("input_domain") != INPUT_DOMAIN
        or whole_file_closure.get("status") != "PASSED"
        or whole_file_closure.get("blocked_declarations")
        != {"source": [], "target": []}
        or whole_file_closure.get("source_user_call_graph")
        != {"edges": [], "status": "EMPTY_AND_CLOSED"}
        or whole_file_closure.get("target_call_graph", {}).get("status")
        != "EXACT_EMITTER_HELPERS_AND_PINNED_BUILTINS"
    ):
        raise RuntimeError(f"MODULE_CONTRACT_INVALID:{route.name}")
    functions = module.get("functions")
    if not isinstance(functions, list) or len(functions) < 5:
        raise RuntimeError(f"MODULE_FUNCTION_COVERAGE_INVALID:{route.name}")
    covered_types: set[str] = set()
    for function in functions:
        if not isinstance(function, dict):
            raise RuntimeError(f"MODULE_FUNCTION_INVALID:{route.name}")
        signature = function.get("signature")
        if not isinstance(signature, dict):
            raise RuntimeError(f"MODULE_SIGNATURE_INVALID:{route.name}")
        for parameter in signature.get("parameters", []):
            if isinstance(parameter, dict) and isinstance(parameter.get("type"), str):
                covered_types.add(parameter["type"])
        if isinstance(signature.get("return_type"), str):
            covered_types.add(signature["return_type"])
    if not {"integer", "number", "boolean"}.issubset(covered_types):
        raise RuntimeError(f"MODULE_TYPE_COVERAGE_INVALID:{route.name}")

    relative_paths = {module_relative}
    artifact_refs = module.get("artifact_refs")
    if not isinstance(artifact_refs, list) or not artifact_refs:
        raise RuntimeError(f"MODULE_ARTIFACT_REFS_REQUIRED:{route.name}")
    for index, artifact_ref in enumerate(artifact_refs):
        if not isinstance(artifact_ref, dict):
            raise RuntimeError(f"MODULE_ARTIFACT_REF_INVALID:{route.name}:{index}")
        source = base.route_relative_file(
            route,
            artifact_ref.get("path"),
            label=f"{route.name}_MODULE_ARTIFACT_{index}",
        )
        if base.digest_file(source) != artifact_ref.get(
            "sha256"
        ) or source.stat().st_size != artifact_ref.get("bytes"):
            raise RuntimeError(
                f"MODULE_ARTIFACT_REF_TAMPERED:{route.name}:{artifact_ref.get('path')}"
            )
        relative_paths.add(artifact_ref["path"])
    for relative in sorted(relative_paths):
        source = base.route_relative_file(
            route, relative, label=f"{route.name}_MODULE_BUNDLE_MEMBER"
        )
        base.copy_file(source, target_root / relative)
    return module, module_relative


def collect_route_evidence(
    pack: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    routes: list[dict[str, Any]] = []
    copies: list[dict[str, Any]] = []
    for route_key, source, target in exact_routes():
        route = ROOT / "routes" / route_key
        manifest = base.load_json(route / "route.json")
        certification = base.load_json(route / "certification" / "certification.json")
        if (
            manifest.get("route_key") != route_key
            or manifest.get("source", {}).get("language") != source
            or manifest.get("target", {}).get("language") != target
        ):
            raise RuntimeError(f"ROUTE_IDENTITY_MISMATCH:{route_key}")
        if manifest.get("profiles", {}).get("semantic_profile") != SEMANTIC_PROFILE:
            raise RuntimeError(f"SEMANTIC_PROFILE_MISMATCH:{route_key}")
        if (
            manifest.get("gates", {}).get(
                "canonical_finite_no_error_input_domain_required"
            )
            is not True
        ):
            raise RuntimeError(f"SPECIALIZED_DOMAIN_GATE_MISSING:{route_key}")
        if (
            certification.get("status") != "limited"
            or certification.get("certification_decision") != "NOT_CERTIFIED"
            or certification.get("declared_scope")
            != f"{SEMANTIC_PROFILE}+{MODULE_PROFILE}"
        ):
            raise RuntimeError(f"ROUTE_STATUS_BOUNDARY_INVALID:{route_key}")
        target_root = pack / "evidence" / "routes" / route_key
        formal, formal_relative, replay_members = base.copy_route_formal_bundle(
            route, target_root, certification
        )
        module, module_relative = copy_module_closure(route, target_root, certification)
        formal_receipts = [
            item
            for item in formal.get("artifact_refs", [])
            if isinstance(item, dict)
            and item.get("role") == "swift-analyzer-build-receipt"
        ]
        module_receipts = [
            item
            for item in module.get("artifact_refs", [])
            if isinstance(item, dict)
            and item.get("role") == "swift-analyzer-build-receipt"
        ]
        if "swift" in {source, target}:
            if len(formal_receipts) != 1 or len(module_receipts) != 1:
                raise RuntimeError(
                    f"SWIFT_ANALYZER_BUILD_RECEIPT_COUNT_INVALID:{route_key}"
                )
            if formal_receipts[0].get(
                "path"
            ) != "certification/formal-artifacts/swift-analyzer-build-receipt.json" or {
                key: formal_receipts[0].get(key) for key in ("path", "sha256", "bytes")
            } != {
                key: module_receipts[0].get(key) for key in ("path", "sha256", "bytes")
            }:
                raise RuntimeError(
                    f"SWIFT_ANALYZER_BUILD_RECEIPT_BINDING_INVALID:{route_key}"
                )
            validate_portable_swift_receipt(route, formal_receipts[0])
        elif formal_receipts or module_receipts:
            raise RuntimeError(f"SWIFT_ANALYZER_BUILD_RECEIPT_UNEXPECTED:{route_key}")
        proof_status = formal.get("formal_proof", {}).get("status")
        if proof_status != "PROVED_UNDER_ASSUMPTIONS":
            raise RuntimeError(
                f"ROUTE_FORMAL_PROOF_NONPASSING:{route_key}:{proof_status}"
            )
        evidence_id = f"route-evidence-{route_key}"
        module_evidence_id = f"route-module-evidence-{route_key}"
        copies.append(
            {
                "evidence_id": evidence_id,
                "relative": (target_root / formal_relative)
                .relative_to(pack)
                .as_posix(),
                "module_evidence_id": module_evidence_id,
                "module_relative": (target_root / module_relative)
                .relative_to(pack)
                .as_posix(),
                "source_ir_sha256": formal["semantic_ir"]["source_ir_sha256"],
                "target_ir_sha256": formal["semantic_ir"]["target_relift_ir_sha256"],
                "environment_sha256": formal["environment_sha256"],
                "artifact_sha256": formal["artifact_sha256"],
                "behavior_cases": formal["behavior_equivalence"]["total_cases"],
                "module_function_count": len(module["functions"]),
                "proof_status": proof_status,
                "replay_members": replay_members,
            }
        )
        routes.append(
            {
                "route_key": route_key,
                "source_language": source,
                "target_language": target,
                "route_version": str(manifest.get("version")),
                "semantic_profile": SEMANTIC_PROFILE,
                "composition_id": f"composition-{route_key}",
                "artifact_evidence_ids": [evidence_id],
                "module_evidence_id": module_evidence_id,
                "packed_replay_evidence_ids": [
                    base.packed_replay_evidence_id(route_key, member["member"])
                    for member in replay_members
                ],
            }
        )
    if tuple(route["route_key"] for route in routes) != EXACT_ROUTE_KEYS:
        raise RuntimeError("SPECIALIZED_ROUTE_SET_IS_NOT_EXACT")
    return routes, copies


def _bind_specialized_arithmetic_evidence(campaign: dict[str, Any]) -> None:
    """Bind residual int64 evidence to the exact specialized target obligations."""

    evidence = campaign.get("evidence")
    obligations = campaign.get("obligations")
    if not isinstance(evidence, list) or not isinstance(obligations, list):
        raise RuntimeError("ARITHMETIC_EVIDENCE_BINDING_INVALID")
    evidence_entries = [
        item
        for item in evidence
        if isinstance(item, dict) and item.get("evidence_id") == ARITHMETIC_EVIDENCE_ID
    ]
    if len(evidence_entries) != 1:
        raise RuntimeError("ARITHMETIC_EVIDENCE_BINDING_INVALID")

    expected_obligation_ids = {
        f"lowering-{language}-{block}"
        for language in LANGUAGES
        for block in ARITHMETIC_EVIDENCE_BLOCKS
    }
    matching_obligations: dict[str, dict[str, Any]] = {}
    for obligation in obligations:
        if not isinstance(obligation, dict):
            raise RuntimeError("ARITHMETIC_EVIDENCE_BINDING_INVALID")
        obligation_id = obligation.get("obligation_id")
        evidence_ids = obligation.get("evidence_ids")
        if not isinstance(obligation_id, str) or not isinstance(evidence_ids, list):
            raise RuntimeError("ARITHMETIC_EVIDENCE_BINDING_INVALID")
        if any(not isinstance(item, str) for item in evidence_ids):
            raise RuntimeError("ARITHMETIC_EVIDENCE_BINDING_INVALID")
        if (
            obligation.get("kind") == "target-lowering"
            and obligation.get("semantic_block") in ARITHMETIC_EVIDENCE_BLOCKS
        ):
            if obligation_id in matching_obligations:
                raise RuntimeError("ARITHMETIC_EVIDENCE_BINDING_INVALID")
            matching_obligations[obligation_id] = obligation

    if set(matching_obligations) != expected_obligation_ids:
        raise RuntimeError("ARITHMETIC_EVIDENCE_BINDING_INVALID")
    for obligation in matching_obligations.values():
        evidence_ids = obligation["evidence_ids"]
        if ARITHMETIC_EVIDENCE_ID not in evidence_ids:
            evidence_ids.append(ARITHMETIC_EVIDENCE_ID)

    bound_obligation_ids: set[str] = set()
    for obligation in obligations:
        evidence_ids = obligation["evidence_ids"]
        binding_count = evidence_ids.count(ARITHMETIC_EVIDENCE_ID)
        if binding_count == 0:
            continue
        obligation_id = obligation["obligation_id"]
        if binding_count != 1 or obligation_id not in expected_obligation_ids:
            raise RuntimeError("ARITHMETIC_EVIDENCE_BINDING_INVALID")
        bound_obligation_ids.add(obligation_id)
    if bound_obligation_ids != expected_obligation_ids:
        raise RuntimeError("ARITHMETIC_EVIDENCE_BINDING_INVALID")


def build_campaign(
    pack: Path,
    routes: list[dict[str, Any]],
    route_copies: list[dict[str, Any]],
    bundle_paths: dict[str, str],
) -> dict[str, Any]:
    campaign = base.build_campaign(pack, routes, route_copies, bundle_paths)
    _bind_specialized_arithmetic_evidence(campaign)
    campaign["schema_version"] = 2
    campaign["route_policy"] = "exact-explicit-set"
    campaign["required_route_keys"] = list(EXACT_ROUTE_KEYS)
    campaign["input_domain"] = INPUT_DOMAIN
    base.add_evidence(
        pack,
        campaign,
        PACKED_RUNTIME_EVIDENCE_ID,
        PACKED_RUNTIME_MANIFEST,
        role="packed-replay-runtime",
    )
    campaign["packed_replay_runtime_evidence_id"] = PACKED_RUNTIME_EVIDENCE_ID
    campaign["limitations"] = [
        "The route inventory is the explicit specialized eight; it is not a four-language complete matrix and does not imply 12 or 72 directions.",
        "Packed replay independently revalidates the byte-bound function and five-function module closure but does not regenerate native evidence.",
        "Integer arithmetic is limited to the canonical finite no-error domain; arithmetic-error behavior outside that domain is blocked.",
        "Finite number support is transport/comparison only; number arithmetic, non-finite values, and string semantics are unsupported.",
        "All local formal results are PROVED_UNDER_ASSUMPTIONS; analyzer, compiler, runtime, and external soundness remain NOT_RUN.",
        "Independent verification, customer workloads, production execution, and external certification remain NOT_RUN.",
    ]

    copy_by_route = {
        item["evidence_id"].removeprefix("route-evidence-"): item
        for item in route_copies
    }
    for route_key in EXACT_ROUTE_KEYS:
        item = copy_by_route[route_key]
        base.add_evidence(
            pack,
            campaign,
            item["module_evidence_id"],
            item["module_relative"],
            role="route-module-evidence",
        )

    routes_by_key = {route["route_key"]: route for route in routes}
    for obligation in campaign["obligations"]:
        block = obligation.get("semantic_block")
        if block != "module-composition":
            continue
        evidence_ids = obligation["evidence_ids"]
        if obligation.get("kind") == "route-behavior":
            evidence_ids.append(
                copy_by_route[obligation["route_key"]]["module_evidence_id"]
            )
        elif obligation.get("kind") == "source-lifting":
            language = obligation["source_language"]
            evidence_ids.extend(
                copy_by_route[route_key]["module_evidence_id"]
                for route_key, route in routes_by_key.items()
                if route["source_language"] == language
            )
        elif obligation.get("kind") == "target-lowering":
            language = obligation["target_language"]
            evidence_ids.extend(
                copy_by_route[route_key]["module_evidence_id"]
                for route_key, route in routes_by_key.items()
                if route["target_language"] == language
            )
        obligation["evidence_ids"] = list(dict.fromkeys(evidence_ids))
    base.write_json(pack / "formal-route-campaign.json", campaign)
    return campaign


def specialize_base_files(pack: Path) -> None:
    manifest = base.load_json(pack / "pack.json")
    manifest["status"] = "limited"
    manifest["scope"].update(
        {
            "migration_route": "cpp-objc-swift-java-exact-explicit-8-routes",
            "route_count": 8,
            "route_policy": "exact-explicit-set",
            "input_domain": INPUT_DOMAIN,
            "supported_types": ["integer", "finite-number", "boolean"],
            "blocked_semantics": [
                "string",
                "number-arithmetic",
                "non-finite-number",
                "arithmetic-error-domain",
            ],
        }
    )
    manifest["tags"] = [
        "formal-equivalence",
        "polyglot",
        "specialized-exact-8-directed-routes",
        "typed-pure-module",
        "not-certified",
    ]
    base.write_json(pack / "pack.json", manifest)

    support = base.load_json(pack / "support-matrix.json")
    support["capabilities"][0].update(
        {
            "status": "conditional",
            "limitations": [
                "Exact explicit eight directions only; unsupported pairs fail closed.",
                "Integer behavior is conditional on the canonical finite no-error input domain.",
                "Finite numbers are transport/comparison only; boolean logic and branches are covered.",
                "String and finite-number arithmetic semantics are blocked.",
                "Local theorem-under-assumptions evidence is not certification.",
            ],
        }
    )
    support["capabilities"][1].update(
        {
            "key": "specialized-integer-safe-domain-and-finite-number-transport",
            "status": "conditional",
            "limitations": [
                "The copied aggregate arithmetic campaign is residual background evidence, not a proof of out-of-domain runtime behavior.",
                "Overflow, division by zero, non-finite values, and number arithmetic remain blocked.",
            ],
        }
    )
    support["capabilities"][2]["limitations"] = [
        "Strings, number arithmetic, out-of-domain arithmetic errors, mutable state, calls, exceptions, I/O, concurrency, frameworks, and databases are outside scope."
    ]
    base.write_json(pack / "support-matrix.json", support)

    property_spec = base.load_json(pack / "properties" / "sample.json")
    property_spec["generator"]["constraints"] = [
        f"profile={SEMANTIC_PROFILE}",
        "route-set=exact-specialized-8",
        f"input-domain={INPUT_DOMAIN}",
    ]
    base.write_json(pack / "properties" / "sample.json", property_spec)

    model = base.load_json(pack / "models" / "model.json")
    model["invariants"] = [
        item.replace(
            "route-set-is-exactly-thirty", "route-set-is-exact-specialized-eight"
        )
        for item in model["invariants"]
    ]
    base.write_json(pack / "models" / "model.json", model)

    assurance = base.load_json(pack / "assurance" / "assurance-case.json")
    assurance["top_claim"] = (
        "The explicit specialized eight-route typed function and module campaign "
        "has replayable local evidence and fails closed on every unresolved boundary."
    )
    base.write_json(pack / "assurance" / "assurance-case.json", assurance)

    for relative in (
        "certification/evidence.json",
        "certification/certification.json",
    ):
        document = base.load_json(pack / relative)
        document["metrics"]["directed_route_count"] = 8
        if relative.endswith("certification.json"):
            document["status"] = "limited"
            document["exact_scope"] = manifest["scope"]
            document["limitations"] = [
                "NOT_CERTIFIED",
                "Exact explicit specialized eight routes only.",
                "Formal route compositions contain required NOT_RUN source/target soundness obligations.",
                "String, number arithmetic, non-finite number, and arithmetic-error domains are blocked.",
                "Independent verification and external/customer/production validation are NOT_RUN.",
            ]
        base.write_json(pack / relative, document)


def write_corpus_manifests(pack: Path, *, route_set_digest: str) -> None:
    values = {
        "development": (
            "local-development-integer",
            "Each exact route executes an independent integer function corpus within the safe domain.",
        ),
        "negative": (
            "local-specialized-negative",
            "Each applicable analyzer rejection, string/number-domain control, overflow preflight, helper tamper, undeclared pair, and missing symbol is recorded with a stable reason code.",
        ),
        "holdout": (
            "local-separated-finite-number-holdout",
            "Each exact route transports finite numbers including signed zero and finite boundaries; external independence remains NOT_RUN.",
        ),
        "representative-workloads": (
            "bounded-boolean-branch-workload",
            "Each exact route executes nested short-circuit boolean logic with true/false literals and a branch; customer representativeness remains NOT_RUN.",
        ),
    }
    for key, (dataset_class, note) in values.items():
        base.write_json(
            pack / "corpus" / key / "manifest.json",
            {
                "schema_version": 1,
                "corpus": key,
                "status": "passed",
                "source_digest": route_set_digest,
                "dataset_digest": base.aggregate_digest(
                    {
                        "corpus": key,
                        "route_set": route_set_digest,
                        "input_domain": INPUT_DOMAIN,
                    }
                ),
                "evidence_refs": ["evidence/route-set.json"],
                "dataset_class": dataset_class,
                "notes": [note],
            },
        )


def write_readme(pack: Path) -> None:
    (pack / "README.md").write_text(
        "# Specialized polyglot exact-8 formal equivalence v1\n\n"
        "Batch 35 aggregate for exactly eight directed routes: C++↔Objective-C, "
        "C++↔Swift, Objective-C↔Swift, and C++↔Java. This is an explicit set, not "
        "a four-language 12-route matrix and not a nine-language 72-route matrix.\n\n"
        f"The local profile is `{SEMANTIC_PROFILE}+{MODULE_PROFILE}` over "
        f"`{INPUT_DOMAIN}`. Integer behavior is safe-domain conditional; finite "
        "numbers are transport/comparison only; boolean logic and branching are "
        "covered. Strings, number arithmetic, non-finite values, and arithmetic "
        "error behavior are blocked.\n\n"
        "Every packed route includes the three independent function corpora, "
        "five-function module composition, function/module formal input-SMT-result "
        "closures, frozen validator/schema sources, and content-addressed replay. "
        "Schema-v2 replay uses one content-bound CPython 3.12.12 private runtime, "
        "the exact seven-package production wheel closure derived from uv.lock, "
        "copy-only offline installation, isolated Python, and a pinned macOS "
        "default-deny-network sandbox with an actual socket-denial probe. "
        "Native regeneration, compiler/runtime soundness, independent review, "
        "customer evidence, production execution, and external certification remain "
        "`NOT_RUN`; the pack remains `limited / NOT_CERTIFIED`.\n",
        encoding="utf-8",
    )
    (pack / "certification" / "gap-inventory.md").write_text(
        "# Remaining formal and certification gaps\n\n"
        "- Independently prove or validate source and target analyzer/emitter soundness.\n"
        "- Add an external verifier and independently controlled route regeneration.\n"
        "- Define and evidence Unicode/string semantics before enabling strings.\n"
        "- Define finite-number arithmetic rounding, payload, and exceptional-result semantics before enabling number arithmetic.\n"
        "- Model language-specific overflow, undefined behavior, traps, and division errors outside the canonical finite no-error domain.\n"
        "- Execute representative customer repositories and production-equivalent security/performance campaigns.\n"
        "- Obtain external certification; current certification state is NOT_CERTIFIED.\n",
        encoding="utf-8",
    )


def build_staged_pack(pack: Path, arithmetic_campaign: Path) -> tuple[int, int]:
    base.prepare_directories(pack)
    if not (pack / PACKED_RUNTIME_MANIFEST).is_file():
        raise RuntimeError("PACKED_RUNTIME_MUST_BE_PREPARED_BEFORE_ROUTE_COLLECTION")
    routes, route_copies = collect_route_evidence(pack)
    base.copy_file(arithmetic_campaign, pack / "solver" / "arithmetic-campaign.json")
    arithmetic = base.load_json(pack / "solver" / "arithmetic-campaign.json")
    if arithmetic.get("solver", {}).get("version") != "4.16.0":
        raise RuntimeError("ARITHMETIC_SOLVER_VERSION_NOT_LOCKED")
    if arithmetic.get("all_required_proved") is not False:
        raise RuntimeError("ARITHMETIC_CAMPAIGN_MUST_PRESERVE_RESIDUAL_STATUS")
    bundle_paths = base.write_bundle_evidence(pack, route_copies)
    campaign = build_campaign(pack, routes, route_copies, bundle_paths)
    base.base_pack_files(
        pack,
        source_digest=base.digest_file(pack / bundle_paths["source"]),
        target_digest=base.digest_file(pack / bundle_paths["target"]),
        environment_digest=base.digest_file(pack / bundle_paths["environment"]),
        arithmetic_digest=base.digest_file(
            pack / "solver" / "arithmetic-campaign.json"
        ),
        total_behavior_cases=sum(int(item["behavior_cases"]) for item in route_copies),
        arithmetic_counts=arithmetic.get("counts", {}),
    )
    specialize_base_files(pack)
    route_set_digest = base.digest_file(pack / "evidence" / "route-set.json")
    write_corpus_manifests(pack, route_set_digest=route_set_digest)
    write_readme(pack)
    return len(routes), len(campaign["obligation_matrix"])


def publish_staged_pack(staging: Path, destination: Path) -> None:
    if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
        raise RuntimeError(f"PACK_DESTINATION_INVALID:{destination}")
    backup: Path | None = None
    if destination.exists():
        backup = Path(
            tempfile.mkdtemp(prefix=f".{PACK_KEY}-backup-", dir=destination.parent)
        )
        backup.rmdir()
        os.replace(destination, backup)
    try:
        os.replace(staging, destination)
    except Exception:
        if backup is not None and backup.exists() and not destination.exists():
            os.replace(backup, destination)
        raise
    if backup is not None:
        shutil.rmtree(backup)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--arithmetic-campaign",
        type=Path,
        required=True,
        help="machine-readable residual campaign from prove_arithmetic_compensation.py",
    )
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument(
        "--runtime-cache",
        type=Path,
        help=(
            "optional directory containing the pinned CPython archive and "
            "wheelhouse; when omitted exact artifacts are downloaded"
        ),
    )
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    arithmetic_campaign = args.arithmetic_campaign.resolve(strict=True)
    runtime_cache = (
        args.runtime_cache.resolve(strict=True)
        if args.runtime_cache is not None
        else None
    )
    configure_base(repo_root)
    pack_parent = repo_root / "verification-packs"
    pack_parent.mkdir(parents=True, exist_ok=True)
    destination = pack_parent / PACK_KEY
    staging = Path(tempfile.mkdtemp(prefix=f".{PACK_KEY}-staging-", dir=pack_parent))
    try:
        base.prepare_directories(staging)
        prepare_packed_runtime(staging, repo_root, runtime_cache)
        runtime_preflight = subprocess.run(
            [
                sys.executable,
                str(
                    repo_root
                    / "scripts"
                    / "batch35"
                    / "validate_formal_route_campaign.py"
                ),
                str(staging),
                "--runtime-preflight",
                "--json",
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
        if runtime_preflight.returncode != 0:
            diagnostic = (
                runtime_preflight.stderr.strip()
                or runtime_preflight.stdout.strip()
                or "unknown packed runtime preflight failure"
            )
            raise RuntimeError(
                "PACKED_RUNTIME_PRIVATE_PREFLIGHT_FAILED:" + diagnostic[-2048:]
            )
        validate_source_routes(repo_root)
        route_count, matrix_count = build_staged_pack(staging, arithmetic_campaign)
        base.validate_staged_pack(repo_root, staging)
        publish_staged_pack(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    print(
        f"PASS: built {destination} with {route_count} exact routes, "
        f"{matrix_count} route/block rows, decision NOT_CERTIFIED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
