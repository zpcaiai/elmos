from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .clang_analyzer import analyze_clang, inventory_clang_module
from .emitter import _CPP_HELPERS, _OBJC_HELPERS, _SWIFT_HELPERS
from .models import ROUTED_LANGUAGES, Language, RouteError, SemanticIR
from .python_analyzer import analyze_python
from .toolchains import exact_toolchain

ENGINE_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = ENGINE_ROOT.parents[1]

# These native frontends can re-lift emitted target source even though they
# are not part of the older ROUTED_LANGUAGES evidence inventory.  Relift
# capability is deliberately named separately from route certification.
NATIVE_RELIFTABLE_LANGUAGES = frozenset({"cpp", "objc", "swift"})
MODULE_INVENTORY_KIND = "elmos.typed-pure-module-inventory"
MODULE_INVENTORY_PROFILE = "typed-pure-module-v1"


def _verify_emitted_helper_sources(source: Path, language: Language) -> None:
    registries = {"cpp": _CPP_HELPERS, "objc": _OBJC_HELPERS, "swift": _SWIFT_HELPERS}
    registry = registries.get(language)
    if registry is None:
        return
    content = source.read_text(encoding="utf-8")
    for helper_id, expected in registry.items():
        first_line = expected.splitlines()[0]
        names = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", first_line)
        if not names:
            raise RouteError(f"EMITTED_HELPER_REGISTRY_INVALID:{language}:{helper_id}")
        name = names[-1]
        if f"{name}(" not in content:
            continue
        if content.count(expected) != 1:
            raise RouteError(f"EMITTED_HELPER_SOURCE_MISMATCH:{language}:{helper_id}:{name}")


def _swift_analyzer_needs_build(package: Path, binary: Path) -> bool:
    if not binary.is_file():
        return True
    inputs = [package / "Package.swift", package / "Package.resolved", *sorted((package / "Sources").rglob("*.swift"))]
    if any(not item.is_file() for item in inputs):
        raise RouteError("SWIFT_ANALYZER_INPUT_MISSING")
    return max(item.stat().st_mtime_ns for item in inputs) > binary.stat().st_mtime_ns


def _toolchain_profile_value(profile: tuple[str, ...], key: str) -> str:
    prefix = key + "="
    matches = [item[len(prefix) :] for item in profile if item.startswith(prefix)]
    if len(matches) != 1 or not matches[0]:
        raise RouteError(f"EXACT_TOOLCHAIN_PROFILE_VALUE_REQUIRED:{key}")
    return matches[0]


def _run(command: list[str], *, cwd: Path, timeout: int = 120) -> dict[str, Any]:
    environment = os.environ.copy()
    environment["NO_COLOR"] = "1"
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=environment,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-2_000:]
        raise RouteError(f"NATIVE_ANALYZER_FAILED:{command[0]}:{detail}")
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RouteError(f"NATIVE_ANALYZER_INVALID_JSON:{command[0]}") from error
    if not isinstance(value, dict):
        raise RouteError("NATIVE_ANALYZER_OBJECT_REQUIRED")
    return value


def _validated_module_inventory(
    value: dict[str, Any],
    language: Language,
    source: Path,
) -> dict[str, Any]:
    if (
        value.get("schema_version") != "1.0.0"
        or value.get("kind") != MODULE_INVENTORY_KIND
        or value.get("profile") != MODULE_INVENTORY_PROFILE
        or value.get("source_language") != language
        or value.get("source_file") != source.name
    ):
        raise RouteError(f"MODULE_INVENTORY_IDENTITY_INVALID:{language}:{source.name}")
    status = value.get("enumeration_status")
    subjects = value.get("subjects")
    diagnostics = value.get("diagnostics")
    if status not in {"PASSED", "FAILED"} or not isinstance(subjects, list) or not isinstance(diagnostics, list):
        raise RouteError(f"MODULE_INVENTORY_CONTRACT_INVALID:{language}:{source.name}")

    normalized_subjects: list[dict[str, Any]] = []
    occurrences: dict[tuple[str, str], int] = {}
    for raw in subjects:
        if not isinstance(raw, dict):
            raise RouteError(f"MODULE_INVENTORY_SUBJECT_INVALID:{language}:{source.name}")
        name = raw.get("name")
        qualified_name = raw.get("qualified_name")
        declaration_kind = raw.get("declaration_kind")
        analyzable = raw.get("analyzable")
        source_span = raw.get("source_span")
        signature = raw.get("signature")
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(qualified_name, str)
            or not qualified_name
            or not isinstance(declaration_kind, str)
            or not declaration_kind
            or not isinstance(analyzable, bool)
            or not isinstance(signature, dict)
        ):
            raise RouteError(f"MODULE_INVENTORY_SUBJECT_INVALID:{language}:{source.name}")
        if source_span is not None:
            if not isinstance(source_span, dict):
                raise RouteError(f"MODULE_INVENTORY_SPAN_INVALID:{language}:{source.name}")
            span_file = source_span.get("file")
            start_byte = source_span.get("start_byte")
            end_byte = source_span.get("end_byte")
            if (
                span_file != source.name
                or not isinstance(start_byte, int)
                or not isinstance(end_byte, int)
                or start_byte < 0
                or end_byte <= start_byte
                or end_byte > source.stat().st_size
            ):
                raise RouteError(f"MODULE_INVENTORY_SPAN_INVALID:{language}:{source.name}")
        occurrence_key = (declaration_kind, qualified_name)
        occurrence = occurrences.get(occurrence_key, 0) + 1
        occurrences[occurrence_key] = occurrence
        normalized_subjects.append(
            {
                "name": name,
                "qualified_name": qualified_name,
                "declaration_kind": declaration_kind,
                "analyzable": analyzable,
                "source_span": source_span,
                "signature": signature,
                "occurrence": occurrence,
            }
        )
    return {
        **value,
        "subjects": normalized_subjects,
        "diagnostics": [str(item) for item in diagnostics],
    }


def inventory_module(source: Path, language: Language) -> dict[str, Any]:
    """Enumerate one file with its real parser/compiler frontend.

    This is deliberately separate from ``analyze``: enumeration establishes
    file closure, while the existing named-function mode decides whether each
    enumerated callable fits ``typed-pure-function-v1``.
    """

    source = source.resolve()
    if not source.is_file() or source.is_symlink() or source.stat().st_size > 2_000_000:
        raise RouteError("SOURCE_FILE_UNSAFE_OR_TOO_LARGE")
    if language == "python":
        raise RouteError("PYTHON_MODULE_INVENTORY_USES_CPYTHON_AST")
    toolchain = exact_toolchain(language)
    if language in ("cpp", "objc"):
        value = inventory_clang_module(
            source,
            language,
            toolchain.executable,
            toolchain.version,
            sdk_path=_toolchain_profile_value(toolchain.profile, "sdk-path"),
        )
    elif language == "java":
        helper = ENGINE_ROOT / "native" / "java" / "Analyzer.java"
        value = _run(
            [toolchain.executable, "--source", "21", str(helper), str(source), "--inventory"],
            cwd=ENGINE_ROOT,
        )
    elif language == "csharp":
        project = REPOSITORY_ROOT / "engines" / "dotnet-engine" / "src" / "Elmos.Dotnet.SemanticCli"
        value = _run(
            [toolchain.executable, "run", "--project", str(project), "--", str(source), "--inventory"],
            cwd=REPOSITORY_ROOT,
        )
    elif language == "typescript":
        frontend = REPOSITORY_ROOT / "engines" / "frontend-client-engine"
        cli = frontend / "dist" / "src" / "polyglot-cli.js"
        if not cli.is_file():
            pnpm = shutil.which("pnpm")
            if pnpm is None:
                raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:pnpm")
            completed = subprocess.run(
                [pnpm, "run", "build"],
                cwd=frontend,
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if completed.returncode != 0:
                raise RouteError("TYPESCRIPT_ANALYZER_BUILD_FAILED:" + completed.stderr[-2_000:])
        value = _run([toolchain.executable, str(cli), str(source), "--inventory"], cwd=frontend)
    elif language == "go":
        helper = ENGINE_ROOT / "native" / "go" / "analyzer.go"
        value = _run([toolchain.executable, "run", str(helper), "--", str(source), "--inventory"], cwd=ENGINE_ROOT)
    elif language == "rust":
        package = ENGINE_ROOT / "native" / "rust"
        assert toolchain.auxiliary is not None
        value = _run(
            [
                toolchain.auxiliary,
                "run",
                "--quiet",
                "--offline",
                "--locked",
                "--manifest-path",
                str(package / "Cargo.toml"),
                "--",
                str(source),
                "--inventory",
            ],
            cwd=package,
            timeout=900,
        )
    elif language == "swift":
        package = ENGINE_ROOT / "native" / "swift"
        binary = package / ".build" / "release" / "ElmosSwiftAnalyzer"
        if _swift_analyzer_needs_build(package, binary):
            built = subprocess.run(
                [toolchain.executable.replace("swiftc", "swift"), "build", "-c", "release"],
                cwd=package,
                check=False,
                capture_output=True,
                text=True,
                timeout=900,
            )
            if built.returncode != 0 or not binary.is_file():
                raise RouteError("SWIFT_ANALYZER_BUILD_FAILED:" + (built.stderr or built.stdout)[-2_000:])
        value = _run([str(binary), str(source), "--inventory"], cwd=package)
    else:
        raise RouteError(f"MODULE_INVENTORY_UNSUPPORTED:{language}")
    return _validated_module_inventory(value, language, source)


def analyze(
    source: Path,
    language: Language,
    function_name: str,
    *,
    emitted_target: bool = False,
) -> SemanticIR:
    source = source.resolve()
    if not source.is_file() or source.is_symlink() or source.stat().st_size > 2_000_000:
        raise RouteError("SOURCE_FILE_UNSAFE_OR_TOO_LARGE")
    if emitted_target and language not in ROUTED_LANGUAGES and language not in NATIVE_RELIFTABLE_LANGUAGES:
        raise RouteError(f"EMITTED_TARGET_REANALYSIS_UNSUPPORTED:{language}")
    if emitted_target:
        _verify_emitted_helper_sources(source, language)
    toolchain = exact_toolchain(language)
    if language == "python":
        return analyze_python(source, function_name, emitted_target=emitted_target)
    if language in ("cpp", "objc"):
        return analyze_clang(
            source,
            language,
            function_name,
            toolchain.executable,
            toolchain.version,
            emitted_target=emitted_target,
            sdk_path=_toolchain_profile_value(toolchain.profile, "sdk-path"),
        )
    if language == "swift":
        # The SwiftSyntax helper, built on demand exactly like the TypeScript
        # CLI: a real compiler frontend, never a text-level parse.
        package = ENGINE_ROOT / "native" / "swift"
        binary = package / ".build" / "release" / "ElmosSwiftAnalyzer"
        if _swift_analyzer_needs_build(package, binary):
            built = subprocess.run(
                [toolchain.executable.replace("swiftc", "swift"), "build", "-c", "release"],
                cwd=package,
                check=False,
                capture_output=True,
                text=True,
                timeout=900,
            )
            if built.returncode != 0 or not binary.is_file():
                raise RouteError("SWIFT_ANALYZER_BUILD_FAILED:" + (built.stderr or built.stdout)[-2_000:])
        value = _run(
            [str(binary), str(source), function_name, *(["--emitted-target"] if emitted_target else [])],
            cwd=package,
        )
        return SemanticIR.from_mapping(value)
    if language == "java":
        helper = ENGINE_ROOT / "native" / "java" / "Analyzer.java"
        arguments = [str(source), function_name]
        if emitted_target:
            arguments.append("--emitted-target")
        value = _run(
            [toolchain.executable, "--source", "21", str(helper), *arguments],
            cwd=ENGINE_ROOT,
        )
    elif language == "csharp":
        project = (
            ENGINE_ROOT / "native" / "csharp"
            if emitted_target
            else REPOSITORY_ROOT / "engines" / "dotnet-engine" / "src" / "Elmos.Dotnet.SemanticCli"
        )
        arguments = [str(source), function_name]
        if emitted_target:
            arguments.append("--emitted-target")
        value = _run(
            [toolchain.executable, "run", "--project", str(project), "--", *arguments],
            cwd=REPOSITORY_ROOT,
        )
    elif language == "go":
        helper = ENGINE_ROOT / "native" / "go" / "analyzer.go"
        arguments = [str(source), function_name]
        if emitted_target:
            arguments.append("--emitted-target")
        value = _run([toolchain.executable, "run", str(helper), "--", *arguments], cwd=ENGINE_ROOT)
    elif language == "rust":
        package = ENGINE_ROOT / "native" / "rust"
        assert toolchain.auxiliary is not None
        value = _run(
            [
                toolchain.auxiliary,
                "run",
                "--quiet",
                "--offline",
                "--locked",
                "--manifest-path",
                str(package / "Cargo.toml"),
                "--",
                str(source),
                function_name,
                *(["--emitted-target"] if emitted_target else []),
            ],
            cwd=package,
            timeout=900,
        )
    elif emitted_target:
        helper = ENGINE_ROOT / "native" / "typescript" / "analyzer.mjs"
        typescript_module = (
            REPOSITORY_ROOT
            / "engines"
            / "frontend-client-engine"
            / "node_modules"
            / "typescript"
            / "lib"
            / "typescript.js"
        )
        value = _run(
            [
                toolchain.executable,
                str(helper),
                str(typescript_module),
                str(source),
                function_name,
                "--emitted-target",
            ],
            cwd=ENGINE_ROOT,
        )
    else:
        frontend = REPOSITORY_ROOT / "engines" / "frontend-client-engine"
        cli = frontend / "dist" / "src" / "polyglot-cli.js"
        if not cli.is_file():
            pnpm = shutil.which("pnpm")
            if pnpm is None:
                raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:pnpm")
            completed = subprocess.run(
                [pnpm, "run", "build"],
                cwd=frontend,
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if completed.returncode != 0:
                raise RouteError("TYPESCRIPT_ANALYZER_BUILD_FAILED:" + completed.stderr[-2_000:])
        value = _run([toolchain.executable, str(cli), str(source), function_name], cwd=frontend)
    return SemanticIR.from_mapping(value)
