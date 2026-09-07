#!/usr/bin/env python3.12
"""Emit the exact bundled-Dart repository-build pins for toolchains.py.

This is a read-only qualification helper. It never runs Flutter/Dart, downloads
an artifact or changes the SDK. Two full scans must be byte-identical before a
maintainer can review and copy the emitted constants.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT / "src"))

PACKAGE = "elmos_polyglot_route"
if PACKAGE not in sys.modules:
    stub = types.ModuleType(PACKAGE)
    stub.__path__ = [str(ENGINE_ROOT / "src" / PACKAGE)]
    sys.modules[PACKAGE] = stub

from elmos_polyglot_route.toolchains import (  # noqa: E402
    _EXPECTED_FLUTTER_DART_SDK_ROOT,
    _EXPECTED_FLUTTER_ROOT,
    _qualified_tree_manifest,
)


def scalar(prefix: str, identity: dict[str, object]) -> None:
    for field in (
        "sha256",
        "record_count",
        "file_count",
        "directory_count",
        "bytes",
    ):
        value = identity[field]
        rendered = repr(value) if isinstance(value, str) else str(value)
        print(f"{prefix}_{field.upper()} = {rendered}")


def main() -> int:
    first = _qualified_tree_manifest(
        _EXPECTED_FLUTTER_DART_SDK_ROOT,
        _EXPECTED_FLUTTER_ROOT,
        "PIN_FLUTTER_DART_SDK_TREE_UNSAFE",
    )
    second = _qualified_tree_manifest(
        _EXPECTED_FLUTTER_DART_SDK_ROOT,
        _EXPECTED_FLUTTER_ROOT,
        "PIN_FLUTTER_DART_SDK_TREE_UNSAFE",
    )
    if first != second:
        raise RuntimeError("PIN_FLUTTER_DART_SDK_TREE_CHANGED_DURING_SCAN")
    scalar("_EXPECTED_FLUTTER_DART_SDK_TREE", first)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
