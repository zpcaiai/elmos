from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
import struct
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .emitter import EmittedFile
from .models import Function, Language, RouteError
from .react_analyzer import verify_react_runtime_import
from .repository import javascript_esm_descriptor
from .toolchains import ExactToolchain, exact_toolchain, sanitized_subprocess_env

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]

# A compiler killed by the host (rather than by its own diagnostic path) can
# transiently return SIGTERM/SIGKILL with no output when several independent
# local qualification jobs share a workstation.  Retry exactly once only for
# that empty-diagnostic shape.  A real compiler diagnostic, a timeout, or a
# repeated signal remains a normal failed obligation and is never promoted.
_TRANSIENT_EMPTY_SIGNAL_RETURN_CODES = frozenset({-9, -15, 137, 143})
_TRANSIENT_EMPTY_SIGNAL_RETRIES = 1


def _run(
    command: list[str],
    cwd: Path,
    *,
    timeout: int = 180,
    executable_dirs: tuple[Path, ...] = (),
) -> subprocess.CompletedProcess[str]:
    executable = Path(command[0])
    executable = executable if executable.is_absolute() else (cwd / executable)
    for attempt in range(_TRANSIENT_EMPTY_SIGNAL_RETRIES + 1):
        try:
            with tempfile.TemporaryDirectory(prefix="elmos-validation-process-") as temporary:
                root = Path(temporary)
                home = root / "home"
                scratch = root / "tmp"
                home.mkdir(mode=0o700)
                scratch.mkdir(mode=0o700)
                completed = subprocess.run(
                    command,
                    cwd=cwd,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=sanitized_subprocess_env(
                        home=home,
                        temp_dir=scratch,
                        executable_dirs=(executable.resolve().parent, *executable_dirs),
                    ),
                )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise RouteError(f"TARGET_VALIDATION_FAILED:{Path(command[0]).name}:process") from error
        if completed.returncode == 0:
            return completed
        if (
            attempt < _TRANSIENT_EMPTY_SIGNAL_RETRIES
            and completed.returncode in _TRANSIENT_EMPTY_SIGNAL_RETURN_CODES
            and not (completed.stdout or "").strip()
            and not (completed.stderr or "").strip()
        ):
            continue
        stdout = _bounded_process_diagnostic(completed.stdout, cwd=cwd)
        stderr = _bounded_process_diagnostic(completed.stderr, cwd=cwd)
        raise RouteError(
            "TARGET_VALIDATION_FAILED:"
            f"{Path(command[0]).name}:returncode={completed.returncode}:"
            f"stdout={json.dumps(stdout, ensure_ascii=True)}:"
            f"stderr={json.dumps(stderr, ensure_ascii=True)}"
        )
    raise RouteError(f"TARGET_VALIDATION_FAILED:{Path(command[0]).name}:process")


#: Disclosure policy for external-toolchain failure diagnostics.
#:
#: Reporting only one stream is not safe: a toolchain that writes a banner,
#: telemetry notice or first-run message to ``stderr`` while writing its real
#: diagnostics to ``stdout`` -- ``dotnet build`` on first invocation is the case
#: that motivated this -- gets reported by the banner alone, hiding the reason
#: the build failed behind text that says nothing.  Reporting *both* streams
#: raw is not safe either, because a build log carries host paths and can carry
#: credentials, and these messages are persisted into evidence.  So both streams
#: are kept, and both are sanitised and bounded.
#:
#: These definitions deliberately mirror ``assembly._bounded_process_diagnostic``
#: verb for verb: the two modules run third-party build tools for the same
#: campaign and their failures must obey one disclosure rule, not two.  The copy
#: lives here because ``assembly`` already imports from ``validation`` (see
#: ``safe_output``), so ``validation`` is the lower module and is where the
#: shared version belongs.  ``assembly`` imports this one and no longer keeps a
#: byte-identical copy (K12), so the engine has exactly one sanitiser.
_PROCESS_DIAGNOSTIC_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_PROCESS_DIAGNOSTIC_SECRET_RE = re.compile(
    r"(?im)\b(token|secret|password|passwd|api[_-]?key|cookie|credential)\b"
    r"(\s*[:=]\s*)([^\s,;]+)"
)
_PROCESS_DIAGNOSTIC_AUTHORIZATION_RE = re.compile(
    r"(?im)\b(authorization)\b(\s*:\s*)[^\r\n]*"
)
_PROCESS_DIAGNOSTIC_PRIVATE_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9._-])/(?:private|tmp|var/folders)/[^\s\"'<>]+"
)
_PROCESS_DIAGNOSTIC_LIMIT = 2_000


def _bounded_process_diagnostic(value: str, *, cwd: Path) -> str:
    """Return a bounded diagnostic with host paths and common secrets removed."""

    cleaned = _PROCESS_DIAGNOSTIC_CONTROL_RE.sub("?", value)
    for path, replacement in (
        (str(cwd.resolve()), "<cwd>"),
        (str(Path.home().resolve()), "<home>"),
    ):
        if path:
            cleaned = cleaned.replace(path, replacement)
    cleaned = _PROCESS_DIAGNOSTIC_AUTHORIZATION_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}<redacted>",
        cleaned,
    )
    cleaned = _PROCESS_DIAGNOSTIC_SECRET_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}<redacted>",
        cleaned,
    )
    cleaned = _PROCESS_DIAGNOSTIC_PRIVATE_PATH_RE.sub("<path>", cleaned)
    bounded = cleaned.strip()[-_PROCESS_DIAGNOSTIC_LIMIT:]
    return bounded or "<empty>"


def _apple_sdk(toolchain_profile: tuple[str, ...]) -> str:
    prefix = "sdk-path="
    matches = [item[len(prefix) :] for item in toolchain_profile if item.startswith(prefix)]
    if len(matches) != 1:
        raise RouteError("EXACT_TOOLCHAIN_PROFILE_VALUE_REQUIRED:sdk-path")
    path = Path(matches[0])
    if not path.is_dir():
        raise RouteError(f"EXACT_TOOLCHAIN_APPLE_SDK_INVALID:{path}")
    return str(path)


def _toolchain_evidence(toolchain: ExactToolchain) -> dict[str, Any]:
    return {
        "language": toolchain.language,
        "version": toolchain.version,
        "executable": toolchain.executable,
        "executable_sha256": toolchain.executable_sha256,
        "auxiliary": toolchain.auxiliary,
        "auxiliary_sha256": toolchain.auxiliary_sha256,
        "profile": list(toolchain.profile),
    }


def _toolchain_executable_dirs(toolchain: ExactToolchain) -> tuple[Path, ...]:
    """Return only directories belonging to the exact selected toolchain.

    Some pinned compiler launchers (notably pnpm's ``tsc`` wrapper) dispatch
    to another pinned executable.  Validation still uses a minimal subprocess
    environment, but both exact launchers must be reachable there.

    Kotlin needs a third entry.  ``kotlinc`` and ``kotlin`` are shell scripts
    that exec a JVM: with only their own ``bin`` on PATH they would resolve a
    bare ``java`` from ``/usr/bin``, i.e. an *unpinned* interpreter running
    inside a run this module reports as exactly-toolchained.  ``_kotlin``
    records the JVM it verified as ``kotlin-jvm-home=`` precisely so it can be
    put in front here; ``sanitized_subprocess_env`` places these directories
    ahead of the system ones, so the pinned ``java`` wins.
    """

    paths = (toolchain.executable, toolchain.auxiliary)
    directories = [Path(path).resolve().parent for path in paths if path is not None]
    if toolchain.language == "kotlin":
        directories.insert(0, _kotlin_jvm_bin(toolchain.profile))
    return tuple(directories)


def _kotlin_jvm_bin(toolchain_profile: tuple[str, ...]) -> Path:
    prefix = "kotlin-jvm-home="
    matches = [item[len(prefix) :] for item in toolchain_profile if item.startswith(prefix)]
    if len(matches) != 1:
        raise RouteError("EXACT_TOOLCHAIN_PROFILE_VALUE_REQUIRED:kotlin-jvm-home")
    java_bin = Path(matches[0]) / "bin"
    if not java_bin.is_dir() or not (java_bin / "java").is_file():
        raise RouteError(f"EXACT_TOOLCHAIN_KOTLIN_JVM_INVALID:{java_bin}")
    return java_bin


def _argument(value: object, language: Language) -> str:
    if isinstance(value, bool):
        if language == "python":
            return "True" if value else "False"
        if language == "objc":
            return "YES" if value else "NO"
        return "true" if value else "false"
    if isinstance(value, str):
        encoded = json.dumps(value, ensure_ascii=False)
        if language == "objc":
            return f"@{encoded}"
        if language == "rust":
            return f"{encoded}.to_string()"
        return encoded
    if isinstance(value, int):
        if language in {"java", "csharp"} and not -(2**31) <= value <= 2**31 - 1:
            return f"{value}L"
        if language in {"cpp", "objc"}:
            if value == -(2**63):
                return "INT64_MIN" if language == "cpp" else "LLONG_MIN"
            if not -(2**31) <= value <= 2**31 - 1:
                return f"{value}LL"
    return str(value)


def _java_literal(value: object, value_type: str) -> str:
    if value_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool) or not -(2**63) <= value <= 2**63 - 1:
            raise RouteError("JAVA_CASE_INTEGER_OUTSIDE_INT64")
        if value == -(2**63):
            return "Long.MIN_VALUE"
        return f"{value}L" if not -(2**31) <= value <= 2**31 - 1 else str(value)
    if value_type == "number":
        if not isinstance(value, int | float) or isinstance(value, bool):
            raise RouteError("JAVA_CASE_NUMBER_REQUIRED")
        number = float(value)
        if math.isnan(number):
            return "Double.NaN"
        if math.isinf(number):
            return "Double.NEGATIVE_INFINITY" if number < 0 else "Double.POSITIVE_INFINITY"
        if number == 0.0 and math.copysign(1.0, number) < 0:
            return "-0.0d"
        return repr(number) + ("d" if "." in repr(number) or "e" in repr(number).lower() else ".0d")
    if value_type == "boolean":
        if not isinstance(value, bool):
            raise RouteError("JAVA_CASE_BOOLEAN_REQUIRED")
        return "true" if value else "false"
    if value_type == "string":
        if not isinstance(value, str):
            raise RouteError("JAVA_CASE_STRING_REQUIRED")
        data = value.encode("utf-8")
        if not data:
            return '""'
        items = ", ".join(f"(byte)0x{byte:02x}" for byte in data)
        return "new String(new byte[]{" + items + "}, java.nio.charset.StandardCharsets.UTF_8)"
    raise RouteError(f"JAVA_CASE_TYPE_UNSUPPORTED:{value_type}")


def _expected(value: object, language: Language) -> str:
    return _argument(value, language)


def _returned_case_value(case: dict[str, Any]) -> object:
    if "expected_error" in case:
        # Error/trap equivalence requires one isolated process per case so a
        # signal or fatal trap cannot swallow subsequent observations.  Until
        # that executor exists, preserve the evidence boundary explicitly.
        raise RouteError("EXPECTED_ERROR_BEHAVIOR_NOT_RUN:isolated-case-executor-required")
    if "expected" not in case:
        raise RouteError("BEHAVIOR_CASE_EXPECTED_VALUE_REQUIRED")
    return case["expected"]


def _java_harness(
    function: Function,
    cases: list[dict[str, Any]],
    *,
    owner: str = "Migrated",
) -> str:
    checks = []
    for index, case in enumerate(cases):
        values = case.get("args")
        if not isinstance(values, list) or len(values) != len(function.parameters):
            raise RouteError("JAVA_CASE_ARGUMENT_COUNT_INVALID")
        args = ", ".join(
            _java_literal(value, parameter.type) for value, parameter in zip(values, function.parameters, strict=True)
        )
        expected = _java_literal(_returned_case_value(case), function.return_type)
        call = f"{owner}.{function.name}({args})"
        actual = f"actual{index}"
        expected_name = f"expected{index}"
        # `!=` on String is a reference comparison in Java, so a correct
        # string-returning route could still be reported as a behaviour
        # failure (or, with interned literals, a wrong one reported as a
        # pass). Objects.equals is the value comparison the other three
        # harnesses already perform.
        condition = (
            f"!java.util.Objects.equals({actual}, {expected_name})"
            if function.return_type == "string"
            else (
                f"!((Double.isNaN({actual}) && Double.isNaN({expected_name})) || "
                f"Double.doubleToRawLongBits({actual}) == "
                f"Double.doubleToRawLongBits({expected_name}))"
                if function.return_type == "number"
                else f"{actual} != {expected_name}"
            )
        )
        encoding, rendered = {
            "integer": ("i64-dec", f"Long.toString({actual})"),
            "number": (
                "fp64-hex",
                f'String.format(java.util.Locale.ROOT, "%016x", Double.doubleToRawLongBits({actual}))',
            ),
            "boolean": ("bool", f"Boolean.toString({actual})"),
            "string": (
                "hex-utf8",
                f"java.util.HexFormat.of().formatHex({actual}.getBytes(java.nio.charset.StandardCharsets.UTF_8))",
            ),
        }[function.return_type]
        checks.extend(
            [
                f"        var {actual} = {call};",
                f"        var {expected_name} = {expected};",
                f'        if ({condition}) throw new AssertionError("case {index}");',
                f'        System.out.println("ELMOS_OBSERVATION\\t{index}\\t{encoding}\\t" + {rendered});',
            ]
        )
    return (
        "public final class RouteHarness {\n"
        "    public static void main(String[] args) {\n" + "\n".join(checks) + "\n    }\n}\n"
    )


def _csharp_harness(
    function: Function,
    cases: list[dict[str, Any]],
    *,
    owner: str = "Migrated",
) -> str:
    checks = []
    for index, case in enumerate(cases):
        args = ", ".join(_argument(value, "csharp") for value in case["args"])
        expected = _expected(case["expected"], "csharp")
        actual = f"actual{index}"
        checks.extend(
            [
                f"var {actual} = {owner}.{function.name}({args});",
                f'if ({actual} != {expected}) throw new Exception("case {index}");',
                'Console.WriteLine("ELMOS_OBSERVATION\\t'
                f'{index}\\tb64\\t" + Convert.ToBase64String('
                f"System.Text.Encoding.UTF8.GetBytes(Convert.ToString({actual}, "
                "System.Globalization.CultureInfo.InvariantCulture) ?? string.Empty)));",
            ]
        )
    return "\n".join(checks) + "\n"


def _python_literal(value: object, value_type: str) -> str:
    """Render a behaviour-case value as a Python literal of the canonical type.

    Python is the one target in this matrix whose annotations do not coerce
    anything.  ``def add(left: float, right: float) -> float`` called as
    ``add(2, 3)`` returns the **integer** ``5``, not ``5.0``; the observation is
    then recorded as an int while the canonical value -- and every statically
    typed target -- carries a float64 ``5.0``.  Byte-exact evidence comparison
    correctly rejects that, so a perfectly good route is reported as a
    behaviour failure.

    Argument rendering therefore has to be driven by the canonical parameter
    type, exactly as ``_java_literal`` and the TypeScript harness already do.
    """

    if value_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool) or not -(2**63) <= value <= 2**63 - 1:
            raise RouteError("PYTHON_CASE_INTEGER_OUTSIDE_INT64")
        return repr(value)
    if value_type == "number":
        if not isinstance(value, int | float) or isinstance(value, bool):
            raise RouteError("PYTHON_CASE_NUMBER_REQUIRED")
        number = float(value)
        if math.isnan(number):
            return 'float("nan")'
        if math.isinf(number):
            return 'float("-inf")' if number < 0 else 'float("inf")'
        if number == 0.0 and math.copysign(1.0, number) < 0:
            return "-0.0"
        return repr(number)
    if value_type == "boolean":
        if not isinstance(value, bool):
            raise RouteError("PYTHON_CASE_BOOLEAN_REQUIRED")
        return "True" if value else "False"
    if value_type == "string":
        if not isinstance(value, str):
            raise RouteError("PYTHON_CASE_STRING_REQUIRED")
        return json.dumps(value, ensure_ascii=False)
    raise RouteError(f"PYTHON_CASE_TYPE_UNSUPPORTED:{value_type}")


def _python_harness(
    function: Function,
    cases: list[dict[str, Any]],
    *,
    module: str = "migrated",
) -> str:
    checks = []
    for index, case in enumerate(cases):
        values = case.get("args")
        if not isinstance(values, list) or len(values) != len(function.parameters):
            raise RouteError("PYTHON_CASE_ARGUMENT_COUNT_INVALID")
        args = ", ".join(
            _python_literal(value, parameter.type)
            for value, parameter in zip(values, function.parameters, strict=True)
        )
        expected = _python_literal(_returned_case_value(case), function.return_type)
        actual = f"actual_{index}"
        expected_name = f"expected_{index}"
        if function.return_type == "number":
            # float64 identity, not `==`.  `0.0 == -0.0` is True and
            # `nan == nan` is False, so `==` both accepts and rejects the wrong
            # observations.  This is the same bit-exact rule `_java_harness`
            # applies via `Double.doubleToRawLongBits`.
            guard = f"assert type({actual}) is float"
            comparison = (
                f"assert (math.isnan({actual}) and math.isnan({expected_name})) or "
                f"struct.pack('>d', {actual}) == struct.pack('>d', {expected_name})"
            )
        elif function.return_type == "integer":
            # `type(...) is int` rather than isinstance: bool is a subclass of
            # int, and True must not be accepted as the integer 1.
            guard = f"assert type({actual}) is int"
            comparison = f"assert {actual} == {expected_name}"
        elif function.return_type == "boolean":
            guard = f"assert type({actual}) is bool"
            comparison = f"assert {actual} is {expected_name}"
        else:
            guard = f"assert type({actual}) is str"
            comparison = f"assert {actual} == {expected_name}"
        checks.extend(
            [
                f"{expected_name} = {expected}",
                f"{actual} = {module}.{function.name}({args})",
                guard,
                comparison,
                f'print("ELMOS_OBSERVATION\\tjson\\t" + json.dumps('
                f'{{"case_id": {index}, "value": {actual}}}, sort_keys=True, separators=(",", ":")))',
            ]
        )
    return f"import json\nimport math\nimport struct\nimport {module}\n" + "\n".join(checks) + "\n"


def _typescript_harness(
    function: Function,
    cases: list[dict[str, Any]],
    *,
    module_path: str = "./migrated.js",
) -> str:
    subject = "_elmosHarnessSubject"
    checks: list[str] = []
    for index, case in enumerate(cases):
        values = case.get("args")
        if not isinstance(values, list) or len(values) != len(function.parameters):
            raise RouteError("TYPESCRIPT_CASE_ARGUMENT_COUNT_INVALID")
        args = ", ".join(_argument(value, "typescript") for value in values)
        expected = _expected(_returned_case_value(case), "typescript")
        actual = f"actual{index}"
        expected_name = f"expected{index}"
        if function.return_type == "integer":
            condition = f"!Number.isSafeInteger({actual}) || Object.is({actual}, -0) || {actual} !== {expected_name}"
            encoding = "i64-dec"
            rendered = f"String({actual})"
        elif function.return_type == "number":
            condition = f"!Number.isFinite({actual}) || !Object.is({actual}, {expected_name})"
            encoding = "fp64-hex"
            rendered = f"_elmosHarnessFP64({actual})"
        elif function.return_type == "boolean":
            condition = f'typeof {actual} !== "boolean" || {actual} !== {expected_name}'
            encoding = "bool"
            rendered = f"String({actual})"
        elif function.return_type == "string":
            condition = f'typeof {actual} !== "string" || {actual} !== {expected_name}'
            encoding = "hex-utf8"
            rendered = f"_elmosHarnessHexUTF8({actual})"
        else:
            raise RouteError(f"TYPESCRIPT_CASE_TYPE_UNSUPPORTED:{function.return_type}")
        checks.extend(
            [
                f"const {actual} = {subject}({args});",
                f"const {expected_name} = {expected};",
                f'if ({condition}) throw new Error("case {index}");',
                f'console.log("ELMOS_OBSERVATION\\t{index}\\t{encoding}\\t" + {rendered});',
            ]
        )
    return (
        f'import {{ {function.name} as {subject} }} from "{module_path}";\n'
        + "function _elmosHarnessFP64(value: number): string {\n"
        + "  const bytes = new ArrayBuffer(8);\n"
        + "  const view = new DataView(bytes);\n"
        + "  view.setFloat64(0, value, false);\n"
        + '  return view.getBigUint64(0, false).toString(16).padStart(16, "0");\n'
        + "}\n"
        + "function _elmosHarnessHexUTF8(value: string): string {\n"
        + "  return Array.from(new TextEncoder().encode(value), "
        + 'byte => byte.toString(16).padStart(2, "0")).join("");\n'
        + "}\n"
        + "\n".join(checks)
        + "\n"
    )


def _write_typescript_validation_project(
    output: Path,
    *,
    include: list[str],
    react: bool = False,
) -> None:
    compiler_options: dict[str, object] = {
        "target": "ES2022",
        "module": "NodeNext",
        "moduleResolution": "NodeNext",
        "strict": True,
        "outDir": "dist",
    }
    if react:
        compiler_options.update({"jsx": "react-jsx", "types": []})
        (output / "package.json").write_text(
            json.dumps(
                {
                    "private": True,
                    "type": "module",
                    "dependencies": {
                        "react": "19.2.7",
                        "react-dom": "19.2.7",
                    },
                    "devDependencies": {
                        "@types/react": "19.1.10",
                        "@types/react-dom": "19.1.7",
                        "typescript": "5.9.2",
                    },
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    (output / "tsconfig.json").write_text(
        json.dumps(
            {
                "compilerOptions": compiler_options,
                "include": include,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _javascript_literal(value: object, value_type: str) -> str:
    if value_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool) or not -(2**53 - 1) <= value <= 2**53 - 1:
            raise RouteError("JAVASCRIPT_CASE_INTEGER_OUTSIDE_SAFE_SUBSET")
    elif value_type == "number":
        if not isinstance(value, int | float) or isinstance(value, bool) or not math.isfinite(float(value)):
            raise RouteError("JAVASCRIPT_CASE_NUMBER_OUTSIDE_FINITE_SUBSET")
    elif value_type == "boolean":
        if not isinstance(value, bool):
            raise RouteError("JAVASCRIPT_CASE_BOOLEAN_REQUIRED")
    elif value_type == "string":
        if not isinstance(value, str):
            raise RouteError("JAVASCRIPT_CASE_STRING_REQUIRED")
    else:
        raise RouteError(f"JAVASCRIPT_CASE_TYPE_UNSUPPORTED:{value_type}")
    return _argument(value, "javascript")


def _javascript_harness(
    function: Function,
    cases: list[dict[str, Any]],
    *,
    module_path: str = "./migrated.mjs",
) -> str:
    subject = "_elmosHarnessSubject"
    checks: list[str] = []
    for index, case in enumerate(cases):
        values = case.get("args")
        if not isinstance(values, list) or len(values) != len(function.parameters):
            raise RouteError("JAVASCRIPT_CASE_ARGUMENT_COUNT_INVALID")
        args = ", ".join(
            _javascript_literal(value, parameter.type)
            for value, parameter in zip(values, function.parameters, strict=True)
        )
        expected = _javascript_literal(_returned_case_value(case), function.return_type)
        actual = f"actual{index}"
        expected_name = f"expected{index}"
        if function.return_type == "integer":
            condition = f"!Number.isSafeInteger({actual}) || Object.is({actual}, -0) || {actual} !== {expected_name}"
            encoding = "i64-dec"
            rendered = f"String({actual})"
        elif function.return_type == "number":
            condition = f"!Number.isFinite({actual}) || !Object.is({actual}, {expected_name})"
            encoding = "fp64-hex"
            rendered = f"elmosHarnessFP64({actual})"
        elif function.return_type == "boolean":
            condition = f'typeof {actual} !== "boolean" || {actual} !== {expected_name}'
            encoding = "bool"
            rendered = f"String({actual})"
        elif function.return_type == "string":
            condition = f'typeof {actual} !== "string" || {actual} !== {expected_name}'
            encoding = "hex-utf8"
            rendered = f"elmosHarnessHexUTF8({actual})"
        else:
            raise RouteError(f"JAVASCRIPT_CASE_TYPE_UNSUPPORTED:{function.return_type}")
        checks.extend(
            [
                f"const {actual} = {subject}({args});",
                f"const {expected_name} = {expected};",
                f'if ({condition}) throw new Error("case {index}");',
                f'console.log("ELMOS_OBSERVATION\\t{index}\\t{encoding}\\t" + {rendered});',
            ]
        )
    return (
        f'import {{ {function.name} as {subject} }} from "{module_path}";\n'
        + "function elmosHarnessFP64(value) {\n"
        + "  const bytes = new ArrayBuffer(8);\n"
        + "  const view = new DataView(bytes);\n"
        + "  view.setFloat64(0, value, false);\n"
        + '  return view.getBigUint64(0, false).toString(16).padStart(16, "0");\n'
        + "}\n"
        + "function elmosHarnessHexUTF8(value) {\n"
        + '  return Buffer.from(value, "utf8").toString("hex");\n'
        + "}\n"
        + "\n".join(checks)
        + "\n"
    )


def _native_literal(value: object, language: Language, value_type: str) -> str:
    if value_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool) or not -(2**63) <= value <= 2**63 - 1:
            raise RouteError("NATIVE_CASE_INTEGER_OUTSIDE_INT64")
        if language == "swift":
            if value == -(2**63):
                return "Int64.min"
            if value == 2**63 - 1:
                return "Int64.max"
            return f"Int64({value})"
        if value == -(2**63):
            return "INT64_MIN" if language == "cpp" else "LLONG_MIN"
        return f"{value}LL" if not -(2**31) <= value <= 2**31 - 1 else str(value)
    if value_type == "number":
        if not isinstance(value, int | float) or isinstance(value, bool):
            raise RouteError("NATIVE_CASE_NUMBER_REQUIRED")
        number = float(value)
        if math.isnan(number):
            return {
                "cpp": "std::numeric_limits<double>::quiet_NaN()",
                "objc": "NAN",
                "swift": "Double.nan",
            }[language]
        if math.isinf(number):
            sign = "-" if number < 0 else ""
            return {
                "cpp": f"{sign}std::numeric_limits<double>::infinity()",
                "objc": f"{sign}INFINITY",
                "swift": f"{sign}Double.infinity",
            }[language]
        if number == 0.0 and math.copysign(1.0, number) < 0:
            return "-0.0"
        rendered = repr(number)
        return rendered if "." in rendered or "e" in rendered.lower() else rendered + ".0"
    if value_type == "boolean":
        if not isinstance(value, bool):
            raise RouteError("NATIVE_CASE_BOOLEAN_REQUIRED")
        if language == "objc":
            return "YES" if value else "NO"
        return "true" if value else "false"
    if value_type == "string":
        if not isinstance(value, str):
            raise RouteError("NATIVE_CASE_STRING_REQUIRED")
        return _native_string_literal(value, language)
    raise RouteError(f"NATIVE_CASE_TYPE_UNSUPPORTED:{value_type}")


def _native_string_literal(value: str, language: Language) -> str:
    data = value.encode("utf-8")
    if language == "cpp":
        if not data:
            return "std::string()"
        items = ", ".join(f"static_cast<char>(0x{byte:02x})" for byte in data)
        return f"std::string({{{items}}})"
    if language == "objc":
        if not data:
            return '@""'
        items = ", ".join(f"0x{byte:02x}" for byte in data)
        return (
            "[[NSString alloc] initWithBytes:(const unsigned char[]){"
            + items
            + f"}} length:{len(data)} encoding:NSUTF8StringEncoding]"
        )
    if language == "swift":
        if not data:
            return "String()"
        items = ", ".join(f"0x{byte:02x}" for byte in data)
        return f"String(decoding: [UInt8]([{items}]), as: UTF8.self)"
    raise RouteError(f"NATIVE_STRING_LITERAL_UNSUPPORTED:{language}")


def _native_arguments(function: Function, case: dict[str, Any], language: Language) -> str:
    values = case.get("args")
    if not isinstance(values, list) or len(values) != len(function.parameters):
        raise RouteError("NATIVE_CASE_ARGUMENT_COUNT_INVALID")
    return ", ".join(
        _native_literal(value, language, parameter.type)
        for value, parameter in zip(values, function.parameters, strict=True)
    )


def _cpp_harness(
    function: Function,
    cases: list[dict[str, Any]],
    *,
    include_file: str = "migrated.cpp",
) -> str:
    checks: list[str] = []
    for index, case in enumerate(cases):
        args = _native_arguments(function, case, "cpp")
        expected = _native_literal(_returned_case_value(case), "cpp", function.return_type)
        actual = f"actual_{index}"
        expected_name = f"expected_{index}"
        condition = (
            f"!elmos_harness_same_fp64({actual}, {expected_name})"
            if function.return_type == "number"
            else f"{actual} != {expected_name}"
        )
        encoding, rendered = {
            "integer": ("i64-dec", f"std::to_string({actual})"),
            "number": ("fp64-hex", f"elmos_harness_fp64({actual})"),
            "boolean": ("bool", f'({actual} ? std::string("true") : std::string("false"))'),
            "string": ("hex-utf8", f"elmos_harness_hex_utf8({actual})"),
        }[function.return_type]
        checks.extend(
            [
                f"    const auto {actual} = {function.name}({args});",
                f"    const auto {expected_name} = {expected};",
                f"    if ({condition}) return {index + 1};",
                f'    std::cout << "ELMOS_OBSERVATION\\t{index}\\t{encoding}\\t" << {rendered} << "\\n";',
            ]
        )
    return (
        "#include <cmath>\n#include <cstdint>\n#include <cstring>\n#include <iomanip>\n"
        "#include <iostream>\n#include <limits>\n#include <sstream>\n#include <string>\n"
        f'#include "{include_file}"\n\n'
        "[[maybe_unused]] static std::uint64_t elmos_harness_fp64_bits(double value) {\n"
        "    std::uint64_t bits = 0;\n"
        "    static_assert(sizeof(bits) == sizeof(value));\n"
        "    std::memcpy(&bits, &value, sizeof(bits));\n"
        "    return bits;\n"
        "}\n\n"
        "[[maybe_unused]] static bool elmos_harness_same_fp64(double left, double right) {\n"
        "    return (std::isnan(left) && std::isnan(right)) ||\n"
        "           elmos_harness_fp64_bits(left) == elmos_harness_fp64_bits(right);\n"
        "}\n\n"
        "[[maybe_unused]] static std::string elmos_harness_fp64(double value) {\n"
        "    std::ostringstream stream;\n"
        "    stream << std::hex << std::setfill('0') << std::setw(16)\n"
        "           << elmos_harness_fp64_bits(value);\n"
        "    return stream.str();\n"
        "}\n\n"
        "[[maybe_unused]] static std::string elmos_harness_hex_utf8(const std::string &value) {\n"
        '    static constexpr char digits[] = "0123456789abcdef";\n'
        "    std::string encoded;\n"
        "    encoded.reserve(value.size() * 2);\n"
        "    for (const unsigned char byte : value) {\n"
        "        encoded.push_back(digits[byte >> 4]);\n"
        "        encoded.push_back(digits[byte & 0x0f]);\n"
        "    }\n"
        "    return encoded;\n"
        "}\n\n"
        "int main() {\n" + "\n".join(checks) + "\n    return 0;\n}\n"
    )


def _objc_harness(
    function: Function,
    cases: list[dict[str, Any]],
    *,
    include_file: str = "migrated.m",
) -> str:
    checks: list[str] = []
    native_type = {
        "integer": "long long",
        "number": "double",
        "boolean": "BOOL",
        "string": "NSString *",
    }[function.return_type]
    for index, case in enumerate(cases):
        args = _native_arguments(function, case, "objc")
        expected = _native_literal(_returned_case_value(case), "objc", function.return_type)
        actual = f"actual_{index}"
        expected_name = f"expected_{index}"
        condition = (
            f"![{actual} isEqualToString:{expected_name}]"
            if function.return_type == "string"
            else (
                f"!ElmosHarnessSameFP64({actual}, {expected_name})"
                if function.return_type == "number"
                else f"{actual} != {expected_name}"
            )
        )
        observation = {
            "integer": f'printf("ELMOS_OBSERVATION\\t{index}\\ti64-dec\\t%lld\\n", {actual});',
            "number": (
                f'printf("ELMOS_OBSERVATION\\t{index}\\tfp64-hex\\t%s\\n", [ElmosHarnessFP64({actual}) UTF8String]);'
            ),
            "boolean": (f'printf("ELMOS_OBSERVATION\\t{index}\\tbool\\t%s\\n", {actual} ? "true" : "false");'),
            "string": (
                f'printf("ELMOS_OBSERVATION\\t{index}\\thex-utf8\\t%s\\n", [ElmosHarnessHexUTF8({actual}) UTF8String]);'
            ),
        }[function.return_type]
        checks.extend(
            [
                f"        {native_type} {actual} = {function.name}({args});",
                f"        {native_type} {expected_name} = {expected};",
                f"        if ({condition}) return {index + 1};",
                f"        {observation}",
            ]
        )
    return (
        "#import <Foundation/Foundation.h>\n#include <math.h>\n#include <stdint.h>\n#include <string.h>\n"
        f'#import "{include_file}"\n\n'
        "static __attribute__((unused)) uint64_t ElmosHarnessFP64Bits(double value) {\n"
        "    uint64_t bits = 0;\n"
        "    memcpy(&bits, &value, sizeof(bits));\n"
        "    return bits;\n"
        "}\n\n"
        "static __attribute__((unused)) BOOL ElmosHarnessSameFP64(double left, double right) {\n"
        "    return (isnan(left) && isnan(right)) ||\n"
        "           ElmosHarnessFP64Bits(left) == ElmosHarnessFP64Bits(right);\n"
        "}\n\n"
        "static __attribute__((unused)) NSString *ElmosHarnessFP64(double value) {\n"
        '    return [NSString stringWithFormat:@"%016llx", '
        "(unsigned long long)ElmosHarnessFP64Bits(value)];\n"
        "}\n\n"
        "static __attribute__((unused)) NSString *ElmosHarnessHexUTF8(NSString *value) {\n"
        "    NSData *data = [value dataUsingEncoding:NSUTF8StringEncoding];\n"
        "    const unsigned char *bytes = data.bytes;\n"
        "    NSMutableString *result = [NSMutableString stringWithCapacity:data.length * 2];\n"
        "    for (NSUInteger index = 0; index < data.length; index++) {\n"
        '        [result appendFormat:@"%02x", (unsigned int)bytes[index]];\n'
        "    }\n"
        "    return result;\n"
        "}\n\n"
        "int main() {\n    @autoreleasepool {\n" + "\n".join(checks) + "\n    }\n    return 0;\n}\n"
    )


def _swift_harness(function: Function, cases: list[dict[str, Any]]) -> str:
    checks: list[str] = []
    for index, case in enumerate(cases):
        args = _native_arguments(function, case, "swift")
        expected = _native_literal(_returned_case_value(case), "swift", function.return_type)
        actual = f"actual{index}"
        expected_name = f"expected{index}"
        condition = (
            f"!elmosHarnessSameFP64({actual}, {expected_name})"
            if function.return_type == "number"
            else f"{actual} != {expected_name}"
        )
        encoding, rendered = {
            "integer": ("i64-dec", f"String({actual})"),
            "number": ("fp64-hex", f"elmosHarnessFP64({actual})"),
            "boolean": ("bool", f'({actual} ? "true" : "false")'),
            "string": ("hex-utf8", f"elmosHarnessHexUTF8({actual})"),
        }[function.return_type]
        checks.extend(
            [
                f"let {actual} = {function.name}({args})",
                f"let {expected_name} = {expected}",
                f'if {condition} {{ fatalError("case {index}") }}',
                f'print("ELMOS_OBSERVATION\\t{index}\\t{encoding}\\t\\({rendered})")',
            ]
        )
    return (
        "import Foundation\n\n"
        "func elmosHarnessSameFP64(_ left: Double, _ right: Double) -> Bool {\n"
        "    return (left.isNaN && right.isNaN) || left.bitPattern == right.bitPattern\n"
        "}\n\n"
        "func elmosHarnessFP64(_ value: Double) -> String {\n"
        '    return String(format: "%016llx", value.bitPattern)\n'
        "}\n\n"
        "func elmosHarnessHexUTF8(_ value: String) -> String {\n"
        '    return value.utf8.map { String(format: "%02x", $0) }.joined()\n'
        "}\n\n" + "\n".join(checks) + "\n"
    )


def _php_command(toolchain: ExactToolchain, *arguments: str) -> list[str]:
    """One PHP invocation with the interpreter's ambient configuration removed.

    `-n` drops every php.ini, and the three `-d` overrides pin the settings that
    can change an *observed value* rather than just a diagnostic: `precision`
    and `serialize_precision` govern float-to-string, and OPcache is disabled so
    a stale cached compilation of a previous route's file can never be executed
    in place of the file this harness just wrote. `sanitized_subprocess_env`
    already drops PHPRC and PHP_INI_SCAN_DIR, so this closes the remaining path.
    """
    return [
        toolchain.executable,
        "-n",
        "-d",
        "error_reporting=E_ALL",
        "-d",
        "precision=17",
        "-d",
        "serialize_precision=-1",
        "-d",
        "opcache.enable_cli=0",
        *arguments,
    ]


def _php_literal(value: object, value_type: str) -> str:
    """Render one behaviour-case value as a PHP literal of the canonical type.

    Kept separate from `_native_literal` for the same reason `_python_literal`
    is: PHP's spellings for the non-finite doubles and for `PHP_INT_MIN` have no
    overlap with the clang/Swift family, and folding them into that function
    would make its language dispatch a three-way switch on every arm.

    Strings are built from their UTF-8 bytes rather than quoted, so the case
    value cannot depend on how this file's own encoding survived transport, and
    so a byte sequence that is not valid UTF-8 source can still be expressed.
    """
    if value_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool) or not -(2**63) <= value <= 2**63 - 1:
            raise RouteError("PHP_CASE_INTEGER_OUTSIDE_INT64")
        # A bare -9223372036854775808 is a float in PHP; see emitter._integer_literal.
        return "PHP_INT_MIN" if value == -(2**63) else str(value)
    if value_type == "number":
        if not isinstance(value, int | float) or isinstance(value, bool):
            raise RouteError("PHP_CASE_NUMBER_REQUIRED")
        number = float(value)
        if math.isnan(number):
            return "NAN"
        if math.isinf(number):
            return "-INF" if number < 0 else "INF"
        if number == 0.0 and math.copysign(1.0, number) < 0:
            return "-0.0"
        rendered = repr(number)
        return rendered if "." in rendered or "e" in rendered.lower() else rendered + ".0"
    if value_type == "boolean":
        if not isinstance(value, bool):
            raise RouteError("PHP_CASE_BOOLEAN_REQUIRED")
        return "true" if value else "false"
    if value_type == "string":
        if not isinstance(value, str):
            raise RouteError("PHP_CASE_STRING_REQUIRED")
        data = value.encode("utf-8")
        return "''" if not data else f"hex2bin('{data.hex()}')"
    raise RouteError(f"PHP_CASE_TYPE_UNSUPPORTED:{value_type}")


def _php_arguments(function: Function, case: dict[str, Any]) -> str:
    values = case.get("args")
    if not isinstance(values, list) or len(values) != len(function.parameters):
        raise RouteError("PHP_CASE_ARGUMENT_COUNT_INVALID")
    return ", ".join(
        _php_literal(value, parameter.type)
        for value, parameter in zip(values, function.parameters, strict=True)
    )


def _php_harness(function: Function, cases: list[dict[str, Any]], subject_relative_path: str) -> str:
    """A standalone PHP harness that `require`s the subject and replays cases.

    The comparison is bit-exact for `number`: `pack('E', ...)` is the big-endian
    binary64 image, so -0.0 and 0.0 differ and every NaN payload is visible,
    which `==` in PHP would hide. NaN is compared as a pair of `is_nan` calls
    for the same reason the Java and Swift harnesses do: no NaN equals itself.
    """
    checks: list[str] = []
    for index, case in enumerate(cases):
        args = _php_arguments(function, case)
        expected = _php_literal(_returned_case_value(case), function.return_type)
        actual = f"$actual_{index}"
        expected_name = f"$expected_{index}"
        condition = (
            f"!elmos_harness_same_fp64({actual}, {expected_name})"
            if function.return_type == "number"
            else f"{actual} !== {expected_name}"
        )
        encoding, rendered = {
            "integer": ("i64-dec", f"(string){actual}"),
            "number": ("fp64-hex", f"elmos_harness_fp64({actual})"),
            "boolean": ("bool", f"({actual} ? 'true' : 'false')"),
            "string": ("hex-utf8", f"bin2hex({actual})"),
        }[function.return_type]
        checks.extend(
            [
                f"{actual} = {function.name}({args});",
                f"{expected_name} = {expected};",
                f"if ({condition}) {{ fwrite(STDERR, 'case {index}' . PHP_EOL); exit(1); }}",
                f"echo \"ELMOS_OBSERVATION\\t{index}\\t{encoding}\\t\", {rendered}, PHP_EOL;",
            ]
        )
    return (
        "<?php\n\n"
        "declare(strict_types=1);\n\n"
        f"require __DIR__ . '/{subject_relative_path}';\n\n"
        "function elmos_harness_same_fp64(float $left, float $right): bool {\n"
        "    if (is_nan($left) && is_nan($right)) {\n"
        "        return true;\n"
        "    }\n"
        "    return pack('E', $left) === pack('E', $right);\n"
        "}\n\n"
        "function elmos_harness_fp64(float $value): string {\n"
        "    return bin2hex(pack('E', $value));\n"
        "}\n\n" + "\n".join(checks) + "\n"
    )


#: The declared JVM class name of every generated Kotlin harness, source side
#: and target side alike.  One name and one rule beats two file-derived names.
_KOTLIN_HARNESS_JVM_NAME = "ElmosHarness"

_KOTLIN_PACKAGE_RE = re.compile(
    r"(?m)^package\s+([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\s*;?\s*$"
)


#: Bit-exact float64 helpers, emitted only for a `number` return.  `toRawBits`
#: and not `toBits`: the latter collapses every NaN payload onto the canonical
#: quiet NaN, which is exactly the difference the evidence has to preserve.
#: The hex digits are assembled by hand because `Long.toHexString` drops
#: leading zeros -- `_native_typed_observation` requires `[0-9a-f]{16}` -- and
#: `String.format("%016x", ...)` would make the observation depend on a locale.
_KOTLIN_HARNESS_FP64 = (
    "private fun elmosHarnessSameFP64(left: Double, right: Double): Boolean {\n"
    "    return (left.isNaN() && right.isNaN()) || left.toRawBits() == right.toRawBits()\n"
    "}\n"
    "\n"
    "private fun elmosHarnessFP64(value: Double): String {\n"
    "    val bits = value.toRawBits()\n"
    '    val digits = "0123456789abcdef"\n'
    "    val encoded = StringBuilder(16)\n"
    "    for (shift in 60 downTo 0 step 4) {\n"
    "        encoded.append(digits[((bits ushr shift) and 0xfL).toInt()])\n"
    "    }\n"
    "    return encoded.toString()\n"
    "}"
)


#: Emitted only for a `string` return.  `Byte` is signed in Kotlin, so the
#: value has to be widened through `and 0xff` before it can index the table.
_KOTLIN_HARNESS_HEX_UTF8 = (
    "private fun elmosHarnessHexUTF8(value: String): String {\n"
    '    val digits = "0123456789abcdef"\n'
    "    val encoded = StringBuilder(value.length * 2)\n"
    "    for (byte in value.toByteArray(Charsets.UTF_8)) {\n"
    "        val unsigned = byte.toInt() and 0xff\n"
    "        encoded.append(digits[unsigned ushr 4])\n"
    "        encoded.append(digits[unsigned and 0x0f])\n"
    "    }\n"
    "    return encoded.toString()\n"
    "}"
)


def _kotlin_literal(value: object, value_type: str) -> str:
    """Render one behaviour-case value as a Kotlin literal of the canonical type.

    Driven by the canonical type and never by the Python value's own type,
    because Kotlin has no implicit `Long` -> `Double` widening: passing `1L`
    where the subject declares `Double` is a compile error, not the silent
    coercion Java and C# apply.  A `number` case whose JSON carried the integer
    `1` therefore has to come out as `1.0`, exactly as `_python_literal` and
    `_java_literal` already do for their own reasons.

    Strings are built from their UTF-8 bytes rather than quoted, for one reason
    beyond the transport-encoding argument `_php_literal` makes: a Kotlin
    double-quoted string interpolates `$name` and `${expr}` (see
    `emitter._string_literal`), so a quoted case value containing `$` would
    compile into a different string or into a reference to a name that does not
    exist.
    """
    if value_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool) or not -(2**63) <= value <= 2**63 - 1:
            raise RouteError("KOTLIN_CASE_INTEGER_OUTSIDE_INT64")
        # Unsuffixed literals are `Int`, and Kotlin has no negative literal, so
        # -2^63 has no spelling at all; see emitter._integer_literal.
        if value == -(2**63):
            return "Long.MIN_VALUE"
        if value == 2**63 - 1:
            return "Long.MAX_VALUE"
        return f"{value}L"
    if value_type == "number":
        if not isinstance(value, int | float) or isinstance(value, bool):
            raise RouteError("KOTLIN_CASE_NUMBER_REQUIRED")
        number = float(value)
        if math.isnan(number):
            return "Double.NaN"
        if math.isinf(number):
            return "Double.NEGATIVE_INFINITY" if number < 0 else "Double.POSITIVE_INFINITY"
        if number == 0.0 and math.copysign(1.0, number) < 0:
            return "-0.0"
        rendered = repr(number)
        # A Kotlin floating literal is a `Double` only when it carries a point
        # or an exponent; a bare `5` would be an `Int`.
        return rendered if "." in rendered or "e" in rendered.lower() else rendered + ".0"
    if value_type == "boolean":
        if not isinstance(value, bool):
            raise RouteError("KOTLIN_CASE_BOOLEAN_REQUIRED")
        return "true" if value else "false"
    if value_type == "string":
        if not isinstance(value, str):
            raise RouteError("KOTLIN_CASE_STRING_REQUIRED")
        data = value.encode("utf-8")
        if not data:
            return '""'
        # `.toByte()` on each element because `byteArrayOf` takes `Byte` and an
        # integer literal above 0x7f does not fit one.
        items = ", ".join(f"0x{byte:02x}.toByte()" for byte in data)
        return f"String(byteArrayOf({items}), Charsets.UTF_8)"
    raise RouteError(f"KOTLIN_CASE_TYPE_UNSUPPORTED:{value_type}")


def _kotlin_arguments(function: Function, case: dict[str, Any]) -> str:
    values = case.get("args")
    if not isinstance(values, list) or len(values) != len(function.parameters):
        raise RouteError("KOTLIN_CASE_ARGUMENT_COUNT_INVALID")
    return ", ".join(
        _kotlin_literal(value, parameter.type)
        for value, parameter in zip(values, function.parameters, strict=True)
    )


def _kotlin_package(text: str) -> str:
    """The subject file's package directive, or the empty default package.

    A top-level Kotlin function is visible unqualified only from inside its own
    package, so the source-side harness has to be declared in the subject's
    package -- the same thing `_go_source_harness` does with the Go package it
    reads out of the source.  A miss here cannot produce a wrong answer: the
    harness lands in the default package, the call does not resolve, and
    kotlinc rejects the compilation.
    """
    match = _KOTLIN_PACKAGE_RE.search(text)
    return "" if match is None else match.group(1)


def _kotlin_harness(
    function: Function,
    cases: list[dict[str, Any]],
    source_relative_path: str,
    *,
    package_name: str = "",
) -> str:
    """A standalone `main()` that calls the subject once per behaviour case.

    Kotlin binds the subject by *co-compilation*, not by an import the way
    Python and the ECMAScript targets do, so `source_relative_path` is not a
    `require`: it names the file the dispatch site hands to the same `kotlinc`
    invocation, and is recorded in the header so the generated artifact states
    which subject it was compiled against.  `package_name` must be that file's
    package directive; the emitted `migrated.kt` declares none (see
    `emitter._emit`), so the target side leaves it empty.

    The `number` comparison is bit-exact: `Double.toRawBits` keeps the NaN
    payload and separates -0.0 from 0.0, both of which `==` erases.  That is the
    same rule `_swift_harness` applies through `bitPattern` and `_php_harness`
    through `pack('E', ...)`.
    """
    if "\n" in source_relative_path or "\r" in source_relative_path:
        # The path is interpolated into a `//` comment, where a newline would
        # end the comment and turn the remainder into Kotlin source.
        raise RouteError("KOTLIN_HARNESS_SUBJECT_PATH_INVALID")
    checks: list[str] = []
    for index, case in enumerate(cases):
        args = _kotlin_arguments(function, case)
        expected = _kotlin_literal(_returned_case_value(case), function.return_type)
        actual = f"actual{index}"
        expected_name = f"expected{index}"
        # `!=` on String is the structural comparison in Kotlin -- it compiles
        # to `!equals` -- so unlike `_java_harness` the string arm needs no
        # Objects.equals; `number` is the only arm `!=` cannot serve.
        condition = (
            f"!elmosHarnessSameFP64({actual}, {expected_name})"
            if function.return_type == "number"
            else f"{actual} != {expected_name}"
        )
        encoding, rendered = {
            "integer": ("i64-dec", f"{actual}.toString()"),
            "number": ("fp64-hex", f"elmosHarnessFP64({actual})"),
            "boolean": ("bool", f'(if ({actual}) "true" else "false")'),
            "string": ("hex-utf8", f"elmosHarnessHexUTF8({actual})"),
        }[function.return_type]
        checks.extend(
            [
                f"    val {actual} = {function.name}({args})",
                f"    val {expected_name} = {expected}",
                f'    if ({condition}) throw AssertionError("case {index}")',
                # Concatenated, never a string template: `$` opens an
                # interpolation in Kotlin and the observation line is parsed
                # byte for byte by `_observations`.
                f'    println("ELMOS_OBSERVATION\\t{index}\\t{encoding}\\t" + {rendered})',
            ]
        )
    # Only the helpers this return type reaches are emitted.  An unused private
    # top-level function is a Kotlin warning, and the dispatch sites compile
    # with `-Werror`, so emitting the whole set unconditionally -- the C++
    # harness's `[[maybe_unused]]` approach -- would fail the build instead.
    helpers: tuple[str, ...]
    if function.return_type == "number":
        helpers = (_KOTLIN_HARNESS_FP64,)
    elif function.return_type == "string":
        helpers = (_KOTLIN_HARNESS_HEX_UTF8,)
    else:
        helpers = ()
    return (
        f"// Behaviour harness for `{function.name}`, compiled together with {source_relative_path}.\n"
        # The JVM class name is DECLARED, not derived.  Kotlin names a file
        # class after the file with only the first letter capitalised, so
        # `route_harness.kt` becomes `Route_harnessKt` -- not the
        # `RouteHarnessKt` that reading the rule as snake-to-Pascal suggests,
        # which fails at run time with "could not find or load main class".
        # Pinning it here means neither dispatch site depends on that rule.
        + f'@file:JvmName("{_KOTLIN_HARNESS_JVM_NAME}")\n'
        + (f"\npackage {package_name}\n" if package_name else "")
        + "\n"
        + "".join(f"{helper}\n\n" for helper in helpers)
        + "fun main() {\n"
        + "\n".join(checks)
        + "\n}\n"
    )


def _dart_literal(value: object, value_type: str) -> str:
    """Render one exact behavior value for bundled Dart 3.12.1."""

    if value_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool) or not -(2**63) <= value <= 2**63 - 1:
            raise RouteError("DART_CASE_INTEGER_OUTSIDE_INT64")
        return str(value)
    if value_type == "number":
        if not isinstance(value, int | float) or isinstance(value, bool):
            raise RouteError("DART_CASE_NUMBER_REQUIRED")
        number = float(value)
        if math.isnan(number):
            return "double.nan"
        if math.isinf(number):
            return "double.negativeInfinity" if number < 0 else "double.infinity"
        if number == 0.0 and math.copysign(1.0, number) < 0:
            return "-0.0"
        rendered = repr(number)
        return rendered if "." in rendered or "e" in rendered.lower() else rendered + ".0"
    if value_type == "boolean":
        if not isinstance(value, bool):
            raise RouteError("DART_CASE_BOOLEAN_REQUIRED")
        return "true" if value else "false"
    if value_type == "string":
        if not isinstance(value, str):
            raise RouteError("DART_CASE_STRING_REQUIRED")
        return json.dumps(value, ensure_ascii=False).replace("$", "\\$")
    raise RouteError(f"DART_CASE_TYPE_UNSUPPORTED:{value_type}")


def _dart_harness(function: Function, cases: list[dict[str, Any]], subject: str) -> str:
    """Compile the exact pure-Dart subject in one runtime harness library."""

    checks: list[str] = []
    for index, case in enumerate(cases):
        arguments = case.get("args")
        if not isinstance(arguments, list) or len(arguments) != len(function.parameters):
            raise RouteError("DART_CASE_ARGUMENT_COUNT_INVALID")
        args = ", ".join(
            _dart_literal(value, parameter.type)
            for value, parameter in zip(arguments, function.parameters, strict=True)
        )
        expected = _dart_literal(_returned_case_value(case), function.return_type)
        actual = f"actual{index}"
        checks.append(f"  final {actual} = {function.name}({args});")
        if function.return_type == "number":
            checks.append(
                f"  if (!_elmosHarnessSameFp64({actual}, {expected})) "
                f"throw StateError('case {index}');"
            )
            observation = f"_elmosHarnessFp64({actual})"
            encoding = "fp64-hex"
        elif function.return_type == "string":
            checks.append(f"  if ({actual} != {expected}) throw StateError('case {index}');")
            observation = f"_elmosHarnessHexUtf8({actual})"
            encoding = "hex-utf8"
        else:
            checks.append(f"  if ({actual} != {expected}) throw StateError('case {index}');")
            observation = actual
            encoding = "i64-dec" if function.return_type == "integer" else "bool"
        checks.append(
            f"  print('ELMOS_OBSERVATION\\t{index}\\t{encoding}\\t${{{observation}}}');"
        )

    imports = ""
    helpers = ""
    if function.return_type == "number":
        imports = "import 'dart:typed_data';\n\n"
        helpers = (
            "String _elmosHarnessFp64(double value) {\n"
            "  final data = ByteData(8)..setFloat64(0, value, Endian.big);\n"
            "  return List<int>.generate(8, data.getUint8)\n"
            "      .map((byte) => byte.toRadixString(16).padLeft(2, '0'))\n"
            "      .join();\n"
            "}\n\n"
            "bool _elmosHarnessSameFp64(double left, double right) {\n"
            "  return _elmosHarnessFp64(left) == _elmosHarnessFp64(right);\n"
            "}\n\n"
        )
    elif function.return_type == "string":
        imports = "import 'dart:convert';\n\n"
        helpers = (
            "String _elmosHarnessHexUtf8(String value) {\n"
            "  return utf8.encode(value)\n"
            "      .map((byte) => byte.toRadixString(16).padLeft(2, '0'))\n"
            "      .join();\n"
            "}\n\n"
        )
    return (
        imports
        + subject.rstrip()
        + "\n\n"
        + helpers
        + "void main() {\n"
        + "\n".join(checks)
        + "\n}\n"
    )


def _go_case_literal(value: object, value_type: str, *, math_alias: str = "math") -> str:
    if value_type == "number":
        if not isinstance(value, int | float) or isinstance(value, bool) or not math.isfinite(float(value)):
            raise RouteError("GO_CASE_NUMBER_OUTSIDE_FINITE_SUBSET")
        bits = struct.unpack(">Q", struct.pack(">d", float(value)))[0]
        return f"{math_alias}.Float64frombits(0x{bits:016x})"
    return _argument(value, "go")


def _go_private_identifiers(function: Function, bases: tuple[str, ...]) -> tuple[str, ...]:
    """Allocate bounded harness-only names around the certified subject.

    A repository work unit currently carries exactly one compiler-inventoried
    function.  That subject is therefore the complete user-declared name set
    visible to these generated harness declarations.  Import aliases and the
    source test entry point must not collide with it (for example a function
    named ``fmt`` or ``TestElmosSourceBehavior``).
    """

    occupied = {function.name}
    allocated: list[str] = []
    for base in bases:
        for suffix in range(17):
            candidate = base if suffix == 0 else f"{base}{suffix}"
            if candidate not in occupied:
                occupied.add(candidate)
                allocated.append(candidate)
                break
        else:
            raise RouteError(f"GO_HARNESS_IDENTIFIER_EXHAUSTED:{base}")
    return tuple(allocated)


def _go_harness(function: Function, cases: list[dict[str, Any]]) -> str:
    if function.name == "main":
        raise RouteError("GO_HARNESS_SUBJECT_NAME_CONFLICT:main")
    fmt_alias, base64_alias, math_alias = _go_private_identifiers(
        function,
        ("_elmosFmt", "_elmosBase64", "_elmosMath"),
    )
    checks: list[str] = []
    uses_number = function.return_type == "number" or any(
        parameter.type == "number" for parameter in function.parameters
    )
    for index, case in enumerate(cases):
        args = ", ".join(
            _go_case_literal(value, parameter.type, math_alias=math_alias)
            for value, parameter in zip(case["args"], function.parameters, strict=True)
        )
        expected = _go_case_literal(
            _returned_case_value(case),
            function.return_type,
            math_alias=math_alias,
        )
        actual = f"actual{index}"
        if function.return_type == "number":
            checks.extend(
                [
                    f"    {actual} := {function.name}({args})",
                    f"    if {math_alias}.Float64bits({actual}) != "
                    f'{math_alias}.Float64bits({expected}) {{ panic("case {index}") }}',
                    f'    {fmt_alias}.Printf("ELMOS_OBSERVATION\\t{index}\\tfp64-hex\\t%016x\\n", '
                    f"{math_alias}.Float64bits({actual}))",
                ]
            )
        else:
            checks.extend(
                [
                    f"    {actual} := {function.name}({args})",
                    f'    if {actual} != {expected} {{ panic("case {index}") }}',
                    f'    {fmt_alias}.Printf("ELMOS_OBSERVATION\\t{index}\\tb64\\t%s\\n", '
                    f"{base64_alias}.StdEncoding.EncodeToString([]byte({fmt_alias}.Sprint({actual}))))",
                ]
            )
    imports = [f'{fmt_alias} "fmt"']
    if function.return_type != "number":
        imports.insert(0, f'{base64_alias} "encoding/base64"')
    if uses_number:
        imports.append(f'{math_alias} "math"')
    return (
        "package main\n\nimport (\n    "
        + "\n    ".join(imports)
        + "\n)\n\nfunc main() {\n"
        + "\n".join(checks)
        + "\n}\n"
    )


def _rust_harness(
    function: Function,
    cases: list[dict[str, Any]],
    *,
    include_file: str = "migrated.rs",
) -> str:
    checks = []
    for index, case in enumerate(cases):
        rendered_args = []
        for value, parameter in zip(case["args"], function.parameters, strict=True):
            if parameter.type == "number" and isinstance(value, int) and not isinstance(value, bool):
                rendered_args.append(f"{value}.0")
            else:
                rendered_args.append(_argument(value, "rust"))
        args = ", ".join(rendered_args)
        expected_value = case["expected"]
        expected = (
            f"{expected_value}.0"
            if (
                function.return_type == "number"
                and isinstance(expected_value, int)
                and not isinstance(expected_value, bool)
            )
            else _expected(expected_value, "rust")
        )
        actual = f"actual_{index}"
        checks.extend(
            [
                f"    let {actual} = {function.name}({args});",
                f'    assert!({actual} == {expected}, "case {index}");',
                f'    println!("ELMOS_OBSERVATION\\t{index}\\trust-debug\\t{{:?}}", {actual});',
            ]
        )
    return f'include!("{include_file}");\n\nfn main() {{\n' + "\n".join(checks) + "\n}\n"


def _typed_observation(text: str, return_type: str) -> object:
    if return_type == "integer":
        return int(text)
    if return_type == "number":
        return float(text)
    if return_type == "boolean":
        if text.lower() not in {"true", "false"}:
            raise RouteError("TARGET_OBSERVATION_BOOLEAN_INVALID")
        return text.lower() == "true"
    if return_type == "string":
        return text
    raise RouteError(f"TARGET_OBSERVATION_TYPE_UNSUPPORTED:{return_type}")


def _native_typed_observation(raw: str, encoding: str, return_type: str) -> object:
    expected_encoding = {
        "integer": "i64-dec",
        "number": "fp64-hex",
        "boolean": "bool",
        "string": "hex-utf8",
    }[return_type]
    if encoding != expected_encoding:
        raise RouteError(f"TARGET_OBSERVATION_ENCODING_TYPE_MISMATCH:{encoding}:{return_type}")
    if encoding == "i64-dec":
        if not re.fullmatch(r"-?(?:0|[1-9][0-9]*)", raw):
            raise RouteError("TARGET_OBSERVATION_INTEGER_INVALID")
        value = int(raw)
        if not -(2**63) <= value <= 2**63 - 1:
            raise RouteError("TARGET_OBSERVATION_INTEGER_OUTSIDE_INT64")
        return value
    if encoding == "fp64-hex":
        if not re.fullmatch(r"[0-9a-f]{16}", raw):
            raise RouteError("TARGET_OBSERVATION_FP64_INVALID")
        return struct.unpack(">d", bytes.fromhex(raw))[0]
    if encoding == "bool":
        if raw not in {"true", "false"}:
            raise RouteError("TARGET_OBSERVATION_BOOLEAN_INVALID")
        return raw == "true"
    if not re.fullmatch(r"(?:[0-9a-f]{2})*", raw):
        raise RouteError("TARGET_OBSERVATION_UTF8_HEX_INVALID")
    try:
        return bytes.fromhex(raw).decode("utf-8")
    except UnicodeDecodeError as error:
        raise RouteError("TARGET_OBSERVATION_UTF8_HEX_INVALID") from error


def _observations(
    stdout: str,
    function: Function,
    case_count: int,
) -> list[dict[str, Any]]:
    values: dict[int, dict[str, Any]] = {}
    for line in stdout.splitlines():
        if not line.startswith("ELMOS_OBSERVATION\t"):
            continue
        parts = line.split("\t", 3)
        if len(parts) < 3:
            raise RouteError("TARGET_OBSERVATION_MALFORMED")
        if parts[1] == "json":
            if len(parts) != 3:
                raise RouteError("TARGET_OBSERVATION_MALFORMED")
            try:
                payload = json.loads(parts[2])
            except json.JSONDecodeError as error:
                raise RouteError("TARGET_OBSERVATION_JSON_INVALID") from error
            if not isinstance(payload, dict) or not isinstance(payload.get("case_id"), int):
                raise RouteError("TARGET_OBSERVATION_JSON_INVALID")
            case_id = payload["case_id"]
            value = payload.get("value")
            encoding = "json"
            raw = parts[2]
        else:
            if len(parts) != 4:
                raise RouteError("TARGET_OBSERVATION_MALFORMED")
            try:
                case_id = int(parts[1])
            except ValueError as error:
                raise RouteError("TARGET_OBSERVATION_CASE_ID_INVALID") from error
            encoding = parts[2]
            raw = parts[3]
            if encoding == "b64":
                try:
                    decoded = base64.b64decode(raw, validate=True).decode("utf-8")
                except (ValueError, UnicodeDecodeError) as error:
                    raise RouteError("TARGET_OBSERVATION_BASE64_INVALID") from error
                value = _typed_observation(decoded, function.return_type)
            elif encoding == "rust-debug":
                if function.return_type == "string":
                    try:
                        value = json.loads(raw)
                    except json.JSONDecodeError as error:
                        raise RouteError("TARGET_OBSERVATION_RUST_STRING_INVALID") from error
                else:
                    value = _typed_observation(raw, function.return_type)
            elif encoding in {"i64-dec", "fp64-hex", "bool", "hex-utf8"}:
                value = _native_typed_observation(raw, encoding, function.return_type)
            else:
                raise RouteError(f"TARGET_OBSERVATION_ENCODING_UNSUPPORTED:{encoding}")
        if not 0 <= case_id < case_count or case_id in values:
            raise RouteError("TARGET_OBSERVATION_CASE_SET_INVALID")
        values[case_id] = {
            "case_id": case_id,
            "status": "RETURNED",
            "value": value,
            "encoding": encoding,
            "raw": raw,
        }
    if set(values) != set(range(case_count)):
        raise RouteError("TARGET_OBSERVATION_CASE_SET_INCOMPLETE")
    return [values[index] for index in range(case_count)]


def _go_source_harness(
    package_name: str,
    function: Function,
    cases: list[dict[str, Any]],
) -> tuple[str, str]:
    fmt_alias, base64_alias, math_alias, testing_alias, test_parameter, test_name = _go_private_identifiers(
        function,
        (
            "_elmosFmt",
            "_elmosBase64",
            "_elmosMath",
            "_elmosTesting",
            "_elmosT",
            "TestElmosSourceBehavior",
        ),
    )
    checks: list[str] = []
    uses_number = function.return_type == "number" or any(
        parameter.type == "number" for parameter in function.parameters
    )
    for index, case in enumerate(cases):
        args = ", ".join(
            _go_case_literal(value, parameter.type, math_alias=math_alias)
            for value, parameter in zip(case["args"], function.parameters, strict=True)
        )
        expected = _go_case_literal(
            _returned_case_value(case),
            function.return_type,
            math_alias=math_alias,
        )
        actual = f"actual{index}"
        if function.return_type == "number":
            checks.extend(
                [
                    f"    {actual} := {function.name}({args})",
                    f"    if {math_alias}.Float64bits({actual}) != "
                    f'{math_alias}.Float64bits({expected}) {{ {test_parameter}.Fatalf("case {index}") }}',
                    f'    {fmt_alias}.Printf("ELMOS_OBSERVATION\\t{index}\\tfp64-hex\\t%016x\\n", '
                    f"{math_alias}.Float64bits({actual}))",
                ]
            )
        else:
            checks.extend(
                [
                    f"    {actual} := {function.name}({args})",
                    f'    if {actual} != {expected} {{ {test_parameter}.Fatalf("case {index}") }}',
                    f'    {fmt_alias}.Printf("ELMOS_OBSERVATION\\t{index}\\tb64\\t%s\\n", '
                    f"{base64_alias}.StdEncoding.EncodeToString([]byte({fmt_alias}.Sprint({actual}))))",
                ]
            )
    imports = [f'{fmt_alias} "fmt"', f'{testing_alias} "testing"']
    if function.return_type != "number":
        imports.insert(0, f'{base64_alias} "encoding/base64"')
    if uses_number:
        imports.append(f'{math_alias} "math"')
    harness = (
        f"package {package_name}\n\nimport (\n    "
        + "\n    ".join(imports)
        + f"\n)\n\nfunc {test_name}({test_parameter} *{testing_alias}.T) {{\n"
        + "\n".join(checks)
        + "\n}\n"
    )
    return harness, test_name


def _safe_source_name(source: Path) -> str:
    stem = source.stem
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", stem):
        raise RouteError("SOURCE_MODULE_NAME_UNSAFE")
    return stem


def _javascript_descriptor_stable_projection(
    source: Path,
    descriptor: dict[str, object],
) -> dict[str, object]:
    descriptor_path = Path(str(descriptor.get("path", "")))
    digest = descriptor.get("sha256")
    byte_count = descriptor.get("bytes")
    descriptor_type = descriptor.get("type")
    if (
        not descriptor_path.is_absolute()
        or not isinstance(digest, str)
        or not isinstance(byte_count, int)
        or byte_count < 0
        or descriptor_type != "module"
    ):
        raise RouteError("JAVASCRIPT_ESM_DESCRIPTOR_INVALID_DURING_VALIDATION")
    normalized_digest = digest if digest.startswith("sha256:") else f"sha256:{digest}"
    return {
        "logical_path": Path(os.path.relpath(descriptor_path, source.parent)).as_posix(),
        "sha256": normalized_digest,
        "bytes": byte_count,
        "type": descriptor_type,
    }




def _extract_python_function(source: str, function_name: str) -> str:
    import ast

    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        raise RouteError("SOURCE_VALIDATION_EXTRACTION_FAILED") from error
    lines = source.splitlines(keepends=True)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == function_name:
            start = min([node.lineno, *(item.lineno for item in node.decorator_list)]) - 1
            end = node.end_lineno or node.lineno
            return "".join(lines[start:end])
    raise RouteError("SOURCE_VALIDATION_EXTRACTION_FAILED")


def _extract_braced_function(source: str, function_name: str) -> str:
    matches = list(re.finditer(rf"(?<![A-Za-z0-9_$]){re.escape(function_name)}\s*\(", source))
    if not matches:
        raise RouteError("SOURCE_VALIDATION_EXTRACTION_FAILED")
    match = matches[0]
    start = source.rfind("\n", 0, match.start()) + 1
    opening = source.find("{", match.end())
    if opening < 0:
        raise RouteError("SOURCE_VALIDATION_EXTRACTION_FAILED")
    depth = 0
    quote: str | None = None
    escaped = False
    line_comment = False
    block_comment = False
    index = opening
    while index < len(source):
        character = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if line_comment:
            if character == "\n":
                line_comment = False
        elif block_comment:
            if character == "*" and following == "/":
                block_comment = False
                index += 1
        elif quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
        elif character == "/" and following == "/":
            line_comment = True
            index += 1
        elif character == "/" and following == "*":
            block_comment = True
            index += 1
        elif character in {'"', "'"}:
            quote = character
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
        index += 1
    raise RouteError("SOURCE_VALIDATION_EXTRACTION_FAILED")


def _source_subject(source: Path, language: Language, function: Function) -> EmittedFile:
    content = source.read_text(encoding="utf-8")
    extracted = (
        _extract_python_function(content, function.name)
        if language == "python"
        else _extract_braced_function(content, function.name)
    )
    if language == "python":
        return EmittedFile("migrated.py", extracted.rstrip() + "\n")
    if language == "java":
        return EmittedFile("Migrated.java", f"public final class Migrated {{\n{extracted}\n}}\n")
    if language == "csharp":
        return EmittedFile("Migrated.cs", f"public static class Migrated\n{{\n{extracted}\n}}\n")
    if language == "typescript":
        return EmittedFile("migrated.ts", extracted.rstrip() + "\n")
    if language == "go":
        return EmittedFile("migrated.go", "package main\n\n" + extracted.rstrip() + "\n")
    if language == "rust":
        return EmittedFile("migrated.rs", extracted.rstrip() + "\n")
    if language == "cpp":
        return EmittedFile("migrated.cpp", "#include <cstdint>\n#include <string>\n\n" + extracted.rstrip() + "\n")
    if language == "objc":
        return EmittedFile("migrated.m", "#import <Foundation/Foundation.h>\n\n" + extracted.rstrip() + "\n")
    return EmittedFile("migrated.swift", extracted.rstrip() + "\n")


def validate_source(
    source: Path,
    language: Language,
    function: Function,
    cases: list[dict[str, Any]],
    output: Path,
) -> dict[str, Any]:
    """Compile and execute the original source artifact in an isolated folder.

    This is intentionally separate from target validation: re-emitting the
    source IR back into its own language would only test the emitter twice and
    would not be evidence about the original source bytes.
    """

    toolchain = exact_toolchain(language)
    output.mkdir(parents=True, exist_ok=True)
    source_name = _safe_source_name(source)
    copied_source = output / source.name
    copied_source.write_bytes(source.read_bytes())
    javascript_descriptor: dict[str, object] | None = None
    javascript_descriptor_report: dict[str, object] | None = None
    javascript_descriptor_observation: dict[str, object] | None = None
    if language == "javascript":
        javascript_descriptor = javascript_esm_descriptor(source)
        if javascript_descriptor is not None:
            descriptor_path = Path(str(javascript_descriptor["path"]))
            descriptor_content = descriptor_path.read_bytes()
            if (
                len(descriptor_content) != javascript_descriptor["bytes"]
                or hashlib.sha256(descriptor_content).hexdigest() != javascript_descriptor["sha256"]
            ):
                raise RouteError("JAVASCRIPT_ESM_DESCRIPTOR_CHANGED_DURING_VALIDATION")
            (output / "package.json").write_bytes(descriptor_content)
            javascript_descriptor_report = _javascript_descriptor_stable_projection(
                source,
                javascript_descriptor,
            )
            javascript_descriptor_observation = {
                "observed_origin_path": str(descriptor_path),
            }
    commands: list[list[str]]
    if language == "java":
        (output / "RouteHarness.java").write_text(_java_harness(function, cases, owner=source_name), encoding="utf-8")
        assert toolchain.auxiliary is not None
        commands = [
            [toolchain.auxiliary, source.name, "RouteHarness.java"],
            [toolchain.executable, "-cp", ".", "RouteHarness"],
        ]
    elif language == "python":
        (output / "source_harness.py").write_text(
            _python_harness(function, cases, module=source_name), encoding="utf-8"
        )
        commands = [
            [toolchain.executable, "-m", "py_compile", source.name, "source_harness.py"],
            [toolchain.executable, "source_harness.py"],
        ]
    elif language == "csharp":
        (output / "Program.cs").write_text(_csharp_harness(function, cases, owner=source_name), encoding="utf-8")
        (output / "SourceHarness.csproj").write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>'
            "<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>"
            "<ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable>"
            "<TreatWarningsAsErrors>true</TreatWarningsAsErrors>"
            "</PropertyGroup></Project>\n",
            encoding="utf-8",
        )
        commands = [
            [toolchain.executable, "build", "SourceHarness.csproj", "-c", "Release"],
            [
                toolchain.executable,
                "run",
                "--project",
                "SourceHarness.csproj",
                "-c",
                "Release",
                "--no-build",
            ],
        ]
    elif language in {"typescript", "react"}:
        (output / "source_harness.ts").write_text(
            _typescript_harness(function, cases, module_path=f"./{source_name}.js"),
            encoding="utf-8",
        )
        _write_typescript_validation_project(
            output,
            include=["*.ts", "*.tsx"] if language == "react" else ["*.ts"],
            react=language == "react",
        )
        assert toolchain.auxiliary is not None
        commands = [
            [toolchain.auxiliary, "-p", "tsconfig.json"],
            [toolchain.executable, "dist/source_harness.js"],
        ]
    elif language == "javascript":
        (output / "source_harness.mjs").write_text(
            _javascript_harness(function, cases, module_path=f"./{source.name}"),
            encoding="utf-8",
        )
        commands = [
            [toolchain.executable, "--check", source.name],
            [toolchain.executable, "--check", "source_harness.mjs"],
            [toolchain.executable, "source_harness.mjs"],
        ]
    elif language == "go":
        match = re.search(r"(?m)^package\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", source.read_text(encoding="utf-8"))
        if match is None:
            raise RouteError("GO_SOURCE_PACKAGE_REQUIRED")
        source_harness, source_test_name = _go_source_harness(match.group(1), function, cases)
        (output / "source_behavior_test.go").write_text(
            source_harness,
            encoding="utf-8",
        )
        commands = [
            [
                toolchain.executable,
                "test",
                "-v",
                "-count=1",
                "-run",
                f"^{source_test_name}$",
                source.name,
                "source_behavior_test.go",
            ]
        ]
    elif language == "rust":
        (output / "source_harness.rs").write_text(
            _rust_harness(function, cases, include_file=source.name), encoding="utf-8"
        )
        commands = [
            [
                toolchain.executable,
                "--edition=2021",
                "-D",
                "warnings",
                "-o",
                "source_harness",
                "source_harness.rs",
            ],
            ["./source_harness"],
        ]
    elif language == "cpp":
        (output / "source_harness.cpp").write_text(
            _cpp_harness(function, cases, include_file=source.name), encoding="utf-8"
        )
        commands = [
            [
                toolchain.executable,
                "-std=c++20",
                "-isysroot",
                _apple_sdk(toolchain.profile),
                "-Wall",
                "-Wextra",
                "-Werror",
                "-o",
                "source_harness",
                "source_harness.cpp",
            ],
            ["./source_harness"],
        ]
    elif language == "objc":
        (output / "source_harness.m").write_text(
            _objc_harness(function, cases, include_file=source.name), encoding="utf-8"
        )
        commands = [
            [
                toolchain.executable,
                "-x",
                "objective-c",
                "-std=c17",
                "-isysroot",
                _apple_sdk(toolchain.profile),
                "-fobjc-arc",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-framework",
                "Foundation",
                "-o",
                "source_harness",
                "source_harness.m",
            ],
            ["./source_harness"],
        ]
    elif language == "swift":
        (output / "main.swift").write_text(_swift_harness(function, cases), encoding="utf-8")
        commands = [
            [
                toolchain.executable,
                "-swift-version",
                "6",
                "-sdk",
                _apple_sdk(toolchain.profile),
                "-warnings-as-errors",
                "-o",
                "source_harness",
                source.name,
                "main.swift",
            ],
            ["./source_harness"],
        ]
    elif language == "php":
        (output / "source_harness.php").write_text(
            _php_harness(function, cases, source.name),
            encoding="utf-8",
        )
        commands = [
            _php_command(toolchain, "-l", source.name),
            _php_command(toolchain, "-l", "source_harness.php"),
            _php_command(toolchain, "source_harness.php"),
        ]
    elif language == "kotlin":
        package_name = _kotlin_package(source.read_text(encoding="utf-8"))
        (output / "source_harness.kt").write_text(
            _kotlin_harness(function, cases, source.name, package_name=package_name),
            encoding="utf-8",
        )
        assert toolchain.auxiliary is not None
        # `kotlinc` is the compiler and `kotlin` the launcher -- the reverse of
        # the java/javac pairing above, where `executable` is the runtime.
        # Classes go to a directory, not a jar, so `-include-runtime` does not
        # apply (it is only legal with `-d <jar>`): the pinned `kotlin`
        # launcher puts kotlin-stdlib on the run classpath itself.  A top-level
        # `main` in `source_harness.kt` compiles to the class `SourceHarnessKt`,
        # qualified by whatever package the subject declares.
        entry_point = (
            f"{package_name}.{_KOTLIN_HARNESS_JVM_NAME}" if package_name else _KOTLIN_HARNESS_JVM_NAME
        )
        commands = [
            [toolchain.executable, "-Werror", "-d", "classes", source.name, "source_harness.kt"],
            [toolchain.auxiliary, "-classpath", "classes", entry_point],
        ]
    elif language == "flutter":
        if toolchain.auxiliary is None:
            raise RouteError("EXACT_TOOLCHAIN_FLUTTER_DART_REQUIRED")
        (output / "source_harness.dart").write_text(
            _dart_harness(function, cases, copied_source.read_text(encoding="utf-8")),
            encoding="utf-8",
        )
        commands = [
            [
                toolchain.auxiliary,
                "analyze",
                "--fatal-infos",
                "--fatal-warnings",
                source.name,
                "source_harness.dart",
            ],
            [
                toolchain.auxiliary,
                "compile",
                "kernel",
                "source_harness.dart",
                "-o",
                "source_harness.dill",
            ],
            [toolchain.auxiliary, "source_harness.dill"],
        ]
    else:
        raise RouteError(f"SOURCE_RUNTIME_UNSUPPORTED:{language}")
    logs: list[dict[str, Any]] = []
    react_runtime_receipt: dict[str, Any] | None = None
    if language == "react":
        react_runtime_receipt = verify_react_runtime_import(toolchain)
        logs.append(
            {
                "command": react_runtime_receipt["command"],
                "stdout": react_runtime_receipt["stdout"],
                "stderr": react_runtime_receipt["stderr"],
            }
        )
    runtime_stdout = ""
    executable_dirs = _toolchain_executable_dirs(toolchain)
    for index, command in enumerate(commands):
        completed = _run(command, output, executable_dirs=executable_dirs)
        logs.append(
            {
                "command": command,
                "stdout": completed.stdout[-2_000:],
                "stderr": completed.stderr[-2_000:],
            }
        )
        if index == len(commands) - 1:
            runtime_stdout = completed.stdout
    if javascript_descriptor is not None:
        current_descriptor = javascript_esm_descriptor(source)
        if (
            current_descriptor is None
            or _javascript_descriptor_stable_projection(source, current_descriptor) != javascript_descriptor_report
        ):
            raise RouteError("JAVASCRIPT_ESM_DESCRIPTOR_CHANGED_DURING_VALIDATION")
        copied_descriptor = output / "package.json"
        if (
            not copied_descriptor.is_file()
            or hashlib.sha256(copied_descriptor.read_bytes()).hexdigest() != javascript_descriptor["sha256"]
            or copied_descriptor.stat().st_size != javascript_descriptor["bytes"]
        ):
            raise RouteError("JAVASCRIPT_ESM_DESCRIPTOR_SNAPSHOT_CHANGED_DURING_VALIDATION")
    observations = _observations(runtime_stdout, function, len(cases))
    report = {
        "status": "PASSED",
        "role": "source",
        "language": language,
        "artifact_path": source.name,
        "artifact_sha256": "sha256:" + hashlib.sha256(copied_source.read_bytes()).hexdigest(),
        "toolchain": _toolchain_evidence(toolchain),
        "commands": logs,
        "case_count": len(cases),
        "observations": observations,
    }
    if javascript_descriptor_report is not None:
        report["javascript_esm_descriptor"] = javascript_descriptor_report
        report["javascript_esm_descriptor_observation"] = javascript_descriptor_observation
    if react_runtime_receipt is not None:
        report["react_runtime_receipt"] = react_runtime_receipt
    return report


def validate(
    emitted: EmittedFile,
    language: Language,
    function: Function,
    cases: list[dict[str, Any]],
    output: Path,
) -> dict[str, Any]:
    toolchain = exact_toolchain(language)
    output.mkdir(parents=True, exist_ok=True)
    target = output / emitted.relative_path
    target.write_text(emitted.content, encoding="utf-8")
    commands: list[list[str]] = []
    if language == "java":
        (output / "RouteHarness.java").write_text(_java_harness(function, cases), encoding="utf-8")
        assert toolchain.auxiliary is not None
        commands = [
            [toolchain.auxiliary, "Migrated.java", "RouteHarness.java"],
            [toolchain.executable, "-cp", ".", "RouteHarness"],
        ]
    elif language == "python":
        (output / "route_harness.py").write_text(_python_harness(function, cases), encoding="utf-8")
        commands = [
            [toolchain.executable, "-m", "py_compile", "migrated.py", "route_harness.py"],
            [toolchain.executable, "route_harness.py"],
        ]
    elif language == "csharp":
        (output / "Program.cs").write_text(_csharp_harness(function, cases), encoding="utf-8")
        (output / "RouteHarness.csproj").write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>'
            "<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>"
            "<ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable>"
            "<TreatWarningsAsErrors>true</TreatWarningsAsErrors>"
            "</PropertyGroup></Project>\n",
            encoding="utf-8",
        )
        commands = [
            [toolchain.executable, "build", "RouteHarness.csproj", "-c", "Release"],
            [
                toolchain.executable,
                "run",
                "--project",
                "RouteHarness.csproj",
                "-c",
                "Release",
                "--no-build",
            ],
        ]
    elif language == "cpp":
        (output / "route_harness.cpp").write_text(_cpp_harness(function, cases), encoding="utf-8")
        commands = [
            [
                toolchain.executable,
                "-std=c++20",
                "-isysroot",
                _apple_sdk(toolchain.profile),
                "-Wall",
                "-Wextra",
                "-Werror",
                "-o",
                "route_harness",
                "route_harness.cpp",
            ],
            ["./route_harness"],
        ]
    elif language == "objc":
        (output / "route_harness.m").write_text(_objc_harness(function, cases), encoding="utf-8")
        commands = [
            [
                toolchain.executable,
                "-x",
                "objective-c",
                "-std=c17",
                "-isysroot",
                _apple_sdk(toolchain.profile),
                "-fobjc-arc",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-framework",
                "Foundation",
                "-o",
                "route_harness",
                "route_harness.m",
            ],
            ["./route_harness"],
        ]
    elif language == "swift":
        # The file *must* be called main.swift: Swift only allows top-level
        # statements there, and rejects them ("statements are not allowed at
        # the top level") in any other file name.
        (output / "main.swift").write_text(_swift_harness(function, cases), encoding="utf-8")
        commands = [
            [
                toolchain.executable,
                "-swift-version",
                "6",
                "-sdk",
                _apple_sdk(toolchain.profile),
                "-warnings-as-errors",
                "-o",
                "route_harness",
                "migrated.swift",
                "main.swift",
            ],
            ["./route_harness"],
        ]
    elif language == "go":
        (output / "route_harness.go").write_text(_go_harness(function, cases), encoding="utf-8")
        commands = [
            [toolchain.executable, "build", "-o", "route_harness", "migrated.go", "route_harness.go"],
            ["./route_harness"],
        ]
    elif language == "rust":
        (output / "route_harness.rs").write_text(_rust_harness(function, cases), encoding="utf-8")
        commands = [
            [toolchain.executable, "--edition=2021", "-D", "warnings", "-o", "route_harness", "route_harness.rs"],
            ["./route_harness"],
        ]
    elif language == "javascript":
        (output / "route_harness.mjs").write_text(_javascript_harness(function, cases), encoding="utf-8")
        commands = [
            [toolchain.executable, "--check", emitted.relative_path],
            [toolchain.executable, "--check", "route_harness.mjs"],
            [toolchain.executable, "route_harness.mjs"],
        ]
    elif language == "php":
        (output / "route_harness.php").write_text(
            _php_harness(function, cases, emitted.relative_path),
            encoding="utf-8",
        )
        commands = [
            _php_command(toolchain, "-l", emitted.relative_path),
            _php_command(toolchain, "-l", "route_harness.php"),
            _php_command(toolchain, "route_harness.php"),
        ]
    elif language == "kotlin":
        (output / "route_harness.kt").write_text(
            _kotlin_harness(function, cases, emitted.relative_path),
            encoding="utf-8",
        )
        assert toolchain.auxiliary is not None
        # `migrated.kt` carries no package declaration -- the placer adds one
        # only when the file lands in a repository tree -- so the harness stays
        # in the default package and its entry class is the bare declared name.
        commands = [
            [toolchain.executable, "-Werror", "-d", "classes", emitted.relative_path, "route_harness.kt"],
            [toolchain.auxiliary, "-classpath", "classes", _KOTLIN_HARNESS_JVM_NAME],
        ]
    elif language == "flutter":
        if toolchain.auxiliary is None:
            raise RouteError("EXACT_TOOLCHAIN_FLUTTER_DART_REQUIRED")
        (output / "route_harness.dart").write_text(
            _dart_harness(function, cases, emitted.content),
            encoding="utf-8",
        )
        commands = [
            [
                toolchain.auxiliary,
                "analyze",
                "--fatal-infos",
                "--fatal-warnings",
                emitted.relative_path,
                "route_harness.dart",
            ],
            [
                toolchain.auxiliary,
                "compile",
                "kernel",
                "route_harness.dart",
                "-o",
                "route_harness.dill",
            ],
            [toolchain.auxiliary, "route_harness.dill"],
        ]
    elif language in {"typescript", "react"}:
        (output / "route_harness.ts").write_text(_typescript_harness(function, cases), encoding="utf-8")
        _write_typescript_validation_project(
            output,
            include=["*.ts", "*.tsx"] if language == "react" else ["*.ts"],
            react=language == "react",
        )
        assert toolchain.auxiliary is not None
        commands = [
            [toolchain.auxiliary, "-p", "tsconfig.json"],
            [toolchain.executable, "dist/route_harness.js"],
        ]
    else:
        raise RouteError(f"TARGET_RUNTIME_UNSUPPORTED:{language}")
    logs = []
    react_runtime_receipt: dict[str, Any] | None = None
    if language == "react":
        react_runtime_receipt = verify_react_runtime_import(toolchain)
        logs.append(
            {
                "command": react_runtime_receipt["command"],
                "stdout": react_runtime_receipt["stdout"],
                "stderr": react_runtime_receipt["stderr"],
            }
        )
    runtime_stdout = ""
    executable_dirs = _toolchain_executable_dirs(toolchain)
    for index, command in enumerate(commands):
        completed = _run(command, output, executable_dirs=executable_dirs)
        logs.append({"command": command, "stdout": completed.stdout[-2_000:], "stderr": completed.stderr[-2_000:]})
        if index == len(commands) - 1:
            runtime_stdout = completed.stdout
    observations = _observations(runtime_stdout, function, len(cases))
    report = {
        "status": "PASSED",
        "language": language,
        "toolchain": _toolchain_evidence(toolchain),
        "commands": logs,
        "case_count": len(cases),
        "observations": observations,
    }
    if react_runtime_receipt is not None:
        report["react_runtime_receipt"] = react_runtime_receipt
    return report


def safe_output(path: Path) -> Path:
    lexical = Path(os.path.abspath(path.expanduser()))
    current = Path(lexical.anchor)
    for component in lexical.parts[1:]:
        current /= component
        if current.is_symlink():
            raise RouteError("OUTPUT_SYMLINK_REJECTED")
    resolved = lexical.resolve(strict=False)
    if resolved == Path.home() or resolved == REPOSITORY_ROOT or len(resolved.parts) < 4:
        raise RouteError("OUTPUT_PATH_TOO_BROAD")
    return lexical


def temporary_output() -> Path:
    return Path(tempfile.mkdtemp(prefix="elmos-polyglot-route-"))
