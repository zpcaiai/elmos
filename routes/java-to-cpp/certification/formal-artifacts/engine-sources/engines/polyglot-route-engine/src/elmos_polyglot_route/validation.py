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
from .toolchains import ExactToolchain, exact_toolchain

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def _run(command: list[str], cwd: Path, *, timeout: int = 180) -> subprocess.CompletedProcess[str]:
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
        detail = (completed.stderr or completed.stdout).strip()[-4_000:]
        raise RouteError(f"TARGET_VALIDATION_FAILED:{command[0]}:{detail}")
    return completed


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
        "profile": list(toolchain.profile),
    }


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
        return (
            "new String(new byte[]{"
            + items
            + "}, java.nio.charset.StandardCharsets.UTF_8)"
        )
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
            _java_literal(value, parameter.type)
            for value, parameter in zip(values, function.parameters, strict=True)
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
                "String.format(java.util.Locale.ROOT, \"%016x\", "
                f"Double.doubleToRawLongBits({actual}))",
            ),
            "boolean": ("bool", f"Boolean.toString({actual})"),
            "string": (
                "hex-utf8",
                "java.util.HexFormat.of().formatHex("
                f"{actual}.getBytes(java.nio.charset.StandardCharsets.UTF_8))",
            ),
        }[function.return_type]
        checks.extend(
            [
                f"        var {actual} = {call};",
                f"        var {expected_name} = {expected};",
                f'        if ({condition}) throw new AssertionError("case {index}");',
                f'        System.out.println("ELMOS_OBSERVATION\\t{index}\\t{encoding}\\t" + '
                f"{rendered});",
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


def _python_harness(
    function: Function,
    cases: list[dict[str, Any]],
    *,
    module: str = "migrated",
) -> str:
    checks = []
    for index, case in enumerate(cases):
        args = ", ".join(_argument(value, "python") for value in case["args"])
        actual = f"actual_{index}"
        checks.extend(
            [
                f"{actual} = {module}.{function.name}({args})",
                f"assert {actual} == {_expected(case['expected'], 'python')}",
                f'print("ELMOS_OBSERVATION\\tjson\\t" + json.dumps('
                f'{{"case_id": {index}, "value": {actual}}}, sort_keys=True, separators=(",", ":")))',
            ]
        )
    return f"import json\nimport {module}\n" + "\n".join(checks) + "\n"


def _typescript_harness(
    function: Function,
    cases: list[dict[str, Any]],
    *,
    module_path: str = "./migrated.js",
) -> str:
    checks = []
    for index, case in enumerate(cases):
        args = ", ".join(_argument(value, "typescript") for value in case["args"])
        expected = _expected(case["expected"], "typescript")
        # Built from the function name directly. An earlier revision templated
        # the literal name `calculate` and then string-replaced it, which also
        # rewrote any occurrence of "calculate" inside a string argument or
        # expected value -- silently changing what the behaviour case asserts.
        actual = f"actual{index}"
        checks.extend(
            [
                f"const {actual} = {function.name}({args});",
                f'if ({actual} !== {expected}) throw new Error("case {index}");',
                f'console.log("ELMOS_OBSERVATION\\tjson\\t" + JSON.stringify({{case_id: {index}, value: {actual}}}));',
            ]
        )
    return "import { " + function.name + f' }} from "{module_path}";\n' + "\n".join(checks) + "\n"


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
            "boolean": ("bool", f"({actual} ? std::string(\"true\") : std::string(\"false\"))"),
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
        "    static constexpr char digits[] = \"0123456789abcdef\";\n"
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
                f'printf("ELMOS_OBSERVATION\\t{index}\\tfp64-hex\\t%s\\n", '
                f'[ElmosHarnessFP64({actual}) UTF8String]);'
            ),
            "boolean": (
                f'printf("ELMOS_OBSERVATION\\t{index}\\tbool\\t%s\\n", {actual} ? "true" : "false");'
            ),
            "string": (
                f'printf("ELMOS_OBSERVATION\\t{index}\\thex-utf8\\t%s\\n", '
                f'[ElmosHarnessHexUTF8({actual}) UTF8String]);'
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
        '#import <Foundation/Foundation.h>\n#include <math.h>\n#include <stdint.h>\n#include <string.h>\n'
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
        "    return [NSString stringWithFormat:@\"%016llx\", "
        "(unsigned long long)ElmosHarnessFP64Bits(value)];\n"
        "}\n\n"
        "static __attribute__((unused)) NSString *ElmosHarnessHexUTF8(NSString *value) {\n"
        "    NSData *data = [value dataUsingEncoding:NSUTF8StringEncoding];\n"
        "    const unsigned char *bytes = data.bytes;\n"
        "    NSMutableString *result = [NSMutableString stringWithCapacity:data.length * 2];\n"
        "    for (NSUInteger index = 0; index < data.length; index++) {\n"
        "        [result appendFormat:@\"%02x\", (unsigned int)bytes[index]];\n"
        "    }\n"
        "    return result;\n"
        "}\n\n"
        "int main() {\n    @autoreleasepool {\n"
        + "\n".join(checks)
        + "\n    }\n    return 0;\n}\n"
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
        "    return String(format: \"%016llx\", value.bitPattern)\n"
        "}\n\n"
        "func elmosHarnessHexUTF8(_ value: String) -> String {\n"
        "    return value.utf8.map { String(format: \"%02x\", $0) }.joined()\n"
        "}\n\n"
        + "\n".join(checks)
        + "\n"
    )


def _go_harness(function: Function, cases: list[dict[str, Any]]) -> str:
    checks = []
    for index, case in enumerate(cases):
        args = ", ".join(_argument(value, "go") for value in case["args"])
        expected = _expected(case["expected"], "go")
        actual = f"actual{index}"
        checks.extend(
            [
                f"    {actual} := {function.name}({args})",
                f'    if {actual} != {expected} {{ panic("case {index}") }}',
                f'    fmt.Printf("ELMOS_OBSERVATION\\t{index}\\tb64\\t%s\\n", '
                f"base64.StdEncoding.EncodeToString([]byte(fmt.Sprint({actual}))))",
            ]
        )
    return (
        'package main\n\nimport (\n    "encoding/base64"\n    "fmt"\n)\n\nfunc main() {\n' + "\n".join(checks) + "\n}\n"
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
) -> str:
    checks: list[str] = []
    for index, case in enumerate(cases):
        args = ", ".join(_argument(value, "go") for value in case["args"])
        expected = _expected(case["expected"], "go")
        actual = f"actual{index}"
        checks.extend(
            [
                f"    {actual} := {function.name}({args})",
                f'    if {actual} != {expected} {{ t.Fatalf("case {index}") }}',
                f'    fmt.Printf("ELMOS_OBSERVATION\\t{index}\\tb64\\t%s\\n", '
                f"base64.StdEncoding.EncodeToString([]byte(fmt.Sprint({actual}))))",
            ]
        )
    return (
        f"package {package_name}\n\n"
        'import (\n    "encoding/base64"\n    "fmt"\n    "testing"\n)\n\n'
        "func TestElmosSourceBehavior(t *testing.T) {\n" + "\n".join(checks) + "\n}\n"
    )


def _safe_source_name(source: Path) -> str:
    stem = source.stem
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", stem):
        raise RouteError("SOURCE_MODULE_NAME_UNSAFE")
    return stem


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
    elif language == "typescript":
        (output / "source_harness.ts").write_text(
            _typescript_harness(function, cases, module_path=f"./{source_name}.js"),
            encoding="utf-8",
        )
        (output / "tsconfig.json").write_text(
            json.dumps(
                {
                    "compilerOptions": {
                        "target": "ES2022",
                        "module": "NodeNext",
                        "moduleResolution": "NodeNext",
                        "strict": True,
                        "outDir": "dist",
                    },
                    "include": ["*.ts"],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        assert toolchain.auxiliary is not None
        commands = [
            [toolchain.auxiliary, "-p", "tsconfig.json"],
            [toolchain.executable, "dist/source_harness.js"],
        ]
    elif language == "go":
        match = re.search(r"(?m)^package\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", source.read_text(encoding="utf-8"))
        if match is None:
            raise RouteError("GO_SOURCE_PACKAGE_REQUIRED")
        (output / "source_behavior_test.go").write_text(
            _go_source_harness(match.group(1), function, cases), encoding="utf-8"
        )
        commands = [
            [
                toolchain.executable,
                "test",
                "-v",
                "-count=1",
                "-run",
                "^TestElmosSourceBehavior$",
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
    else:
        raise RouteError(f"SOURCE_RUNTIME_UNSUPPORTED:{language}")
    logs: list[dict[str, Any]] = []
    runtime_stdout = ""
    for index, command in enumerate(commands):
        completed = _run(command, output)
        logs.append(
            {
                "command": command,
                "stdout": completed.stdout[-2_000:],
                "stderr": completed.stderr[-2_000:],
            }
        )
        if index == len(commands) - 1:
            runtime_stdout = completed.stdout
    observations = _observations(runtime_stdout, function, len(cases))
    return {
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
    else:
        (output / "route_harness.ts").write_text(_typescript_harness(function, cases), encoding="utf-8")
        (output / "tsconfig.json").write_text(
            json.dumps(
                {
                    "compilerOptions": {
                        "target": "ES2022",
                        "module": "NodeNext",
                        "moduleResolution": "NodeNext",
                        "strict": True,
                        "outDir": "dist",
                    },
                    "include": ["*.ts"],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        assert toolchain.auxiliary is not None
        commands = [
            [toolchain.auxiliary, "-p", "tsconfig.json"],
            [toolchain.executable, "dist/route_harness.js"],
        ]
    logs = []
    runtime_stdout = ""
    for index, command in enumerate(commands):
        completed = _run(command, output)
        logs.append({"command": command, "stdout": completed.stdout[-2_000:], "stderr": completed.stderr[-2_000:]})
        if index == len(commands) - 1:
            runtime_stdout = completed.stdout
    observations = _observations(runtime_stdout, function, len(cases))
    return {
        "status": "PASSED",
        "language": language,
        "toolchain": _toolchain_evidence(toolchain),
        "commands": logs,
        "case_count": len(cases),
        "observations": observations,
    }


def safe_output(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved == Path.home() or resolved == REPOSITORY_ROOT or len(resolved.parts) < 4:
        raise RouteError("OUTPUT_PATH_TOO_BROAD")
    if resolved.exists() and resolved.is_symlink():
        raise RouteError("OUTPUT_SYMLINK_REJECTED")
    return resolved


def temporary_output() -> Path:
    return Path(tempfile.mkdtemp(prefix="elmos-polyglot-route-"))
