"""Exact Kotlin module inventory for repository orchestration.

The named-function Kotlin frontend lives in :mod:`elmos_polyglot_route.native`,
whose public repository inventory dispatcher predates Kotlin.  Keep that
historical boundary frozen: this module reuses the same content-addressed
analyzer classes, pinned compiler jars and pinned JDK, but exposes only the
``--inventory`` mode needed by whole-repository discovery.

Kotlin scripts are deliberately not accepted here.  A ``.kts`` file is
executable build/script input, not an ordinary Kotlin compilation unit; project
discovery retains it as a build-descriptor or UNKNOWN obligation instead of
silently translating it as ``typed-pure-module-v1`` source.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from . import native
from .models import RouteError
from .toolchains import ExactToolchain, exact_toolchain

_MAX_SOURCE_BYTES = 2_000_000


def _stable_source_bytes(source: Path) -> bytes:
    return native._stable_read_regular_file(
        source,
        failure="KOTLIN_REPOSITORY_SOURCE_UNSAFE",
        maximum_bytes=_MAX_SOURCE_BYTES,
        allowed_uids=frozenset({os.getuid()}),
    )


def _verify_execution_inputs(
    *,
    helper: Path,
    expected_helper: dict[str, object],
    snapshot: Path,
    expected_snapshot: dict[str, object],
    root: Path,
    toolchain: ExactToolchain,
    classes: Path,
    class_receipt: dict[str, Any] | None,
) -> None:
    """Recheck every executable input around the inventory JVM process."""

    try:
        if native._kotlin_analyzer_source_binding(helper) != expected_helper:
            raise RouteError("KOTLIN_REPOSITORY_ANALYZER_SOURCE_CHANGED")
        if native._kotlin_analyzer_snapshot_binding(snapshot, root) != expected_snapshot:
            raise RouteError("KOTLIN_REPOSITORY_ANALYZER_SNAPSHOT_CHANGED")
        native._verify_trusted_kotlin_toolchain(toolchain)
        if class_receipt is not None:
            native._verify_kotlin_analyzer_classes(classes, class_receipt)
    except (OSError, RouteError, ValueError) as error:
        if isinstance(error, RouteError) and str(error).startswith("KOTLIN_REPOSITORY_"):
            raise
        raise RouteError("KOTLIN_REPOSITORY_ANALYZER_INPUT_CHANGED") from error


def inventory_kotlin_module(source: Path) -> dict[str, Any]:
    """Enumerate one ordinary ``.kt`` file with the pinned Kotlin PSI parser."""

    raw_source = source.expanduser()
    if raw_source.suffix.lower() != ".kt":
        raise RouteError("KOTLIN_REPOSITORY_SOURCE_EXTENSION_UNSUPPORTED")
    if raw_source.is_symlink():
        raise RouteError("KOTLIN_REPOSITORY_SOURCE_UNSAFE")
    try:
        resolved = raw_source.resolve(strict=True)
    except OSError as error:
        raise RouteError("KOTLIN_REPOSITORY_SOURCE_UNSAFE") from error
    if not resolved.is_file():
        raise RouteError("KOTLIN_REPOSITORY_SOURCE_UNSAFE")
    source_bytes = _stable_source_bytes(resolved)

    toolchain = exact_toolchain("kotlin")
    helper = native.ENGINE_ROOT / "native" / "kotlin" / "analyzer.kt"
    expected_helper, helper_content = native._kotlin_analyzer_source_snapshot(helper)
    java, compiler_jar, stdlib_jar = native._kotlin_runtime_paths(toolchain)

    with tempfile.TemporaryDirectory(prefix="elmos-kotlin-repository-inventory-") as temporary:
        root = Path(temporary).resolve(strict=True)
        root.chmod(0o700)
        snapshot, expected_snapshot = native._write_kotlin_analyzer_snapshot(root, helper_content)
        cached = native._kotlin_analyzer_classes(helper, toolchain, compiler_jar, root)
        if cached is None:
            classes = root / "classes"
            classes.mkdir(mode=0o700)
            if not native._compile_kotlin_analyzer(
                toolchain,
                compiler_jar,
                snapshot,
                classes,
                root,
            ):
                raise RouteError("KOTLIN_REPOSITORY_ANALYZER_COMPILE_FAILED")
            class_receipt = None
        else:
            classes, class_receipt = cached

        _verify_execution_inputs(
            helper=helper,
            expected_helper=expected_helper,
            snapshot=snapshot,
            expected_snapshot=expected_snapshot,
            root=root,
            toolchain=toolchain,
            classes=classes,
            class_receipt=class_receipt,
        )
        command = [
            str(java),
            "-cp",
            os.pathsep.join([str(classes), str(compiler_jar), str(stdlib_jar)]),
            "AnalyzerKt",
            str(resolved),
            "--inventory",
        ]
        try:
            value = native._run(command, cwd=root, timeout=900)
        except (OSError, RouteError, ValueError) as error:
            try:
                _verify_execution_inputs(
                    helper=helper,
                    expected_helper=expected_helper,
                    snapshot=snapshot,
                    expected_snapshot=expected_snapshot,
                    root=root,
                    toolchain=toolchain,
                    classes=classes,
                    class_receipt=class_receipt,
                )
            except RouteError as changed:
                raise changed from error
            raise
        _verify_execution_inputs(
            helper=helper,
            expected_helper=expected_helper,
            snapshot=snapshot,
            expected_snapshot=expected_snapshot,
            root=root,
            toolchain=toolchain,
            classes=classes,
            class_receipt=class_receipt,
        )

    if _stable_source_bytes(resolved) != source_bytes:
        raise RouteError("MODULE_INVENTORY_SOURCE_CHANGED:kotlin")
    return native._validated_module_inventory(value, "kotlin", resolved, source_bytes)


__all__ = ["inventory_kotlin_module"]
