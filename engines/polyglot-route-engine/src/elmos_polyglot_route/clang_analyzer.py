"""C++ and Objective-C source analysis, backed by clang's own AST.

Same posture as the other analyzers in this engine: a real compiler frontend,
never string matching. `clang -Xclang -ast-dump=json -fsyntax-only` gives the
same tree the compiler type-checked, so the lifted semantic IR carries clang's
resolved types rather than a guess at them.

One module serves both languages because for the certified
`typed-pure-function-v1` subset they differ in exactly three places, all of
them explicit below: the boolean spelling (`bool` vs `BOOL`), the string type
(`std::string` vs `NSString *`), and how a string operation appears in the
tree (`CXXOperatorCallExpr` vs `ObjCMessageExpr`).

Two source spellings are refused rather than lifted, for the same reason the
Java analyzer refuses `float` and the boxed wrappers:

* `float` -- a 24-bit significand does not round-trip through the canonical
  `number` (binary64): `0.1f + 0.2f != 0.1 + 0.2`.
* `==` / `!=` on `NSString *` -- that is a *pointer* comparison in
  Objective-C. Two equal strings at different addresses answer NO, so lifting
  it as canonical equality would change the program's meaning on every other
  target. `isEqualToString:` is the value comparison and is lifted.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from .models import Language, RouteError, SemanticIR
from .process_io import (
    MAX_ALLOWED_PROCESS_STREAM_BYTES,
    ProcessOutputLimitError,
    run_bounded,
)
from .toolchains import sanitized_subprocess_env

#: Nodes that wrap a value without changing it in the certified subset.
_TRANSPARENT = frozenset(
    {
        "ImplicitCastExpr",
        "CStyleCastExpr",
        "ParenExpr",
        "ExprWithCleanups",
        "MaterializeTemporaryExpr",
        "CXXBindTemporaryExpr",
        "ConstantExpr",
        "NoOp",
    }
)

_BINARY_OPERATORS = frozenset({"+", "-", "*", "/", "%", "<", "<=", ">", ">=", "==", "!=", "&&", "||"})

#: Canonical integer is signed and exactly 64 bits. Narrow or platform-sized
#: integer spellings are rejected: widening a source `int` would erase its
#: overflow behaviour, while `long`/`NSInteger` change width across targets.
_CPP_INTEGER_TYPES = frozenset({"int64_t", "std::int64_t"})
_OBJC_INTEGER_TYPES = frozenset({"long long", "int64_t"})
_NON_CANONICAL_INTEGER_TYPES = frozenset(
    {
        "short",
        "int",
        "long",
        "int8_t",
        "int16_t",
        "int32_t",
        "std::int8_t",
        "std::int16_t",
        "std::int32_t",
        "NSInteger",
    }
)
_STRING_TYPES = frozenset({"std::string", "string", "NSString *", "NSString"})
_BOOLEAN_TYPES = frozenset({"bool", "BOOL"})

_OPERATOR_METHOD = re.compile(r"^operator(==|!=|\+|-|\*|/|%|<=|>=|<|>)$")
_LATER_HEADER_DIRECTIVE = re.compile(
    rb"^[ \t]*#[ \t]*(?:include|import)\b",
    re.MULTILINE,
)
_TRUSTED_EMITTER_PRELUDES: dict[Language, bytes] = {
    "cpp": b"#include <cstdint>\n#include <stdexcept>\n#include <string>\n\n",
    "objc": b"#import <Foundation/Foundation.h>\n\n",
}

_EMITTED_HELPERS: dict[Language, dict[str, tuple[str, int]]] = {
    "cpp": {
        "elmos_checked_add": ("+", 2),
        "elmos_checked_sub": ("-", 2),
        "elmos_checked_mul": ("*", 2),
        "elmos_checked_div": ("/", 2),
        "elmos_checked_mod": ("%", 2),
        "elmos_non_zero": ("identity", 1),
    },
    "objc": {
        "ElmosCheckedAdd": ("+", 2),
        "ElmosCheckedSub": ("-", 2),
        "ElmosCheckedMul": ("*", 2),
        "ElmosCheckedDiv": ("/", 2),
        "ElmosCheckedMod": ("%", 2),
        "ElmosNonZero": ("identity", 1),
    },
}


def _position(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RouteError("CLANG_SOURCE_POSITION_REQUIRED")
    position: dict[str, Any] = value
    for nested in ("expansionLoc", "spellingLoc"):
        nested_position = position.get(nested)
        if isinstance(nested_position, dict):
            position = nested_position
            break
    if not isinstance(position.get("offset"), int):
        raise RouteError("CLANG_SOURCE_OFFSET_REQUIRED")
    return position


def _source_span(node: dict[str, Any], source_file: str) -> dict[str, object]:
    source_range = node.get("range")
    if not isinstance(source_range, dict):
        location = _position(node.get("loc"))
        start = int(location["offset"])
        end = start + int(location.get("tokLen", 0))
    else:
        begin = _position(source_range.get("begin"))
        finish = _position(source_range.get("end"))
        start = int(begin["offset"])
        end = int(finish["offset"]) + int(finish.get("tokLen", 0))
    if start < 0 or end <= start:
        raise RouteError("CLANG_SOURCE_SPAN_INVALID")
    return {"file": source_file, "start_byte": start, "end_byte": end}


def _sdk_path(explicit: str | None) -> str:
    if explicit:
        path = Path(explicit)
    else:
        xcrun = Path("/usr/bin/xcrun")
        if not xcrun.is_file():
            raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:xcrun")
        with tempfile.TemporaryDirectory(prefix="elmos-clang-sdk-env-") as temporary:
            root = Path(temporary)
            home = root / "home"
            scratch = root / "tmp"
            home.mkdir(mode=0o700)
            scratch.mkdir(mode=0o700)
            completed = run_bounded(
                [str(xcrun), "--sdk", "macosx", "--show-sdk-path"],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
                env=sanitized_subprocess_env(
                    home=home,
                    temp_dir=scratch,
                    executable_dirs=(xcrun.parent,),
                ),
            )
        path = Path(completed.stdout.strip())
        if completed.returncode != 0:
            raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:macosx-sdk")
    # Xcode exposes versioned SDK names as trusted in-bundle symlinks (for
    # example MacOSX26.5.sdk -> MacOSX.sdk); the exact-toolchain gate already
    # pins and verifies the containing Xcode/SDK tuple.
    if not path.is_dir():
        raise RouteError(f"EXACT_TOOLCHAIN_APPLE_SDK_INVALID:{path}")
    return str(path)


def _system_header_prelude(
    source: Path,
    language: Language,
) -> tuple[bytes, bytes, bytes] | None:
    """Split an exact emitter-owned system prelude without changing offsets.

    Clang's unfiltered JSON AST eagerly serializes every declaration from C++
    and Foundation headers. New Xcode SDKs can turn a two-kilobyte module into
    hundreds of megabytes of JSON, which must not bypass the process output
    budget. A compiler PCH keeps those already type-checked declarations lazy.

    This optimization is deliberately restricted to the two canonical byte
    sequences emitted by this engine. Arbitrary angle headers, quoted,
    computed, conditional, continued, interleaved, or later headers retain the
    ordinary fail-closed analyzer path and cannot drive PCH artifact creation.
    """

    source_bytes = source.read_bytes()
    trusted_prelude = _TRUSTED_EMITTER_PRELUDES.get(language)
    if trusted_prelude is None or not source_bytes.startswith(trusted_prelude):
        return None
    prelude_end = len(trusted_prelude)
    if _LATER_HEADER_DIRECTIVE.search(source_bytes[prelude_end:]):
        return None
    masked = bytearray(source_bytes)
    for index in range(prelude_end):
        if masked[index] not in (ord("\r"), ord("\n")):
            masked[index] = ord(" ")
    return trusted_prelude, bytes(masked), source_bytes


def _clang_driver_prefix(
    executable: str,
    language: Language,
    sdk_path: str,
    *,
    header: bool,
) -> list[str]:
    mode = (
        "c++-header"
        if header and language == "cpp"
        else "objective-c-header"
        if header
        else "c++"
        if language == "cpp"
        else "objective-c"
    )
    command = [
        executable,
        "-x",
        mode,
        "-std=c++20" if language == "cpp" else "-std=c17",
    ]
    if language == "objc":
        command.append("-fobjc-arc")
        if not header:
            command.extend(["-framework", "Foundation"])
    command.extend(["-isysroot", sdk_path])
    return command


def _require_clang_success(
    completed: subprocess.CompletedProcess[str],
    executable: str,
) -> None:
    errors = [
        line
        for line in completed.stderr.splitlines()
        if ": error:" in line or ": fatal error:" in line
    ]
    if errors:
        raise RouteError("SOURCE_DIAGNOSTICS_BLOCK_ANALYSIS:" + "; ".join(errors[:5])[:2_000])
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-2_000:]
        raise RouteError(f"NATIVE_ANALYZER_FAILED:{executable}:{detail}")


def _stable_clang_detail(
    completed: subprocess.CompletedProcess[str],
    replacements: tuple[tuple[str, str], ...],
) -> str:
    detail = (completed.stderr or completed.stdout).strip()
    for transient, stable in replacements:
        spellings = {transient, str(Path(transient).resolve())}
        if transient.startswith("/private/"):
            spellings.add(transient.removeprefix("/private"))
        elif transient.startswith("/var/"):
            spellings.add("/private" + transient)
        for spelling in sorted(spellings, key=len, reverse=True):
            detail = detail.replace(spelling, stable)
    return detail[-2_000:]


def _require_pch_success(
    completed: subprocess.CompletedProcess[str],
    executable: str,
    replacements: tuple[tuple[str, str], ...],
) -> None:
    if completed.returncode != 0:
        detail = _stable_clang_detail(completed, replacements)
        raise RouteError(f"NATIVE_ANALYZER_PCH_FAILED:{executable}:{detail}")


def _remaining_clang_timeout(deadline: float, executable: str) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise RouteError(f"NATIVE_ANALYZER_TIMEOUT:{executable}")
    return remaining


def _run_clang(
    executable: str,
    source: Path,
    language: Language,
    sdk_path: str | None,
    timeout: float = 600,
    *,
    declaration_filter: str | None = None,
    precompile_system_prelude: bool = False,
) -> dict[str, Any]:
    resolved_sdk_path = _sdk_path(sdk_path)
    prelude = (
        _system_header_prelude(source, language)
        if precompile_system_prelude
        else None
    )
    deadline = time.monotonic() + timeout
    source_snapshot: bytes | None = None
    pch_replacements: tuple[tuple[str, str], ...] = ()
    with tempfile.TemporaryDirectory(prefix="elmos-clang-env-") as temporary:
        root = Path(temporary)
        home = root / "home"
        scratch = root / "tmp"
        home.mkdir(mode=0o700)
        scratch.mkdir(mode=0o700)
        environment = sanitized_subprocess_env(
            home=home,
            temp_dir=scratch,
            executable_dirs=(Path(executable).resolve().parent,),
        )
        analysis_source = source
        command = _clang_driver_prefix(
            executable,
            language,
            resolved_sdk_path,
            header=False,
        )
        if prelude is not None:
            prelude_bytes, masked_source_bytes, source_snapshot = prelude
            pch_path = root / "prelude.pch"
            masked_root = root / "source"
            prelude_root = root / "prelude-source"
            masked_root.mkdir(mode=0o700)
            prelude_root.mkdir(mode=0o700)
            analysis_source = masked_root / source.name
            prelude_source = prelude_root / source.name
            stable_source = str(source.resolve())
            pch_replacements = (
                (str(prelude_source), stable_source),
                (str(analysis_source), stable_source),
                (str(pch_path), "<ELMOS_PCH>"),
                (str(root), "<ELMOS_CLANG_WORKDIR>"),
            )
            source_map = f"-ffile-prefix-map={masked_root.resolve()}={source.parent.resolve()}"
            prelude_source_map = (
                f"-ffile-prefix-map={prelude_root.resolve()}={source.parent.resolve()}"
            )
            pch_command = _clang_driver_prefix(
                executable,
                language,
                resolved_sdk_path,
                header=True,
            )
            pch_command.extend(
                [
                    prelude_source_map,
                    "-Xclang",
                    "-main-file-name",
                    "-Xclang",
                    source.name,
                    str(prelude_source),
                    "-o",
                    "-",
                ]
            )
            validation_command = _clang_driver_prefix(
                executable,
                language,
                resolved_sdk_path,
                header=False,
            )
            validation_command.extend(["-fsyntax-only", str(source)])
            try:
                validation_completed = run_bounded(
                    validation_command,
                    cwd=source.parent,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=_remaining_clang_timeout(deadline, executable),
                    max_stream_bytes=MAX_ALLOWED_PROCESS_STREAM_BYTES,
                    env=environment,
                )
            except ProcessOutputLimitError as error:
                raise RouteError(f"NATIVE_ANALYZER_OUTPUT_LIMIT:{executable}") from error
            except subprocess.TimeoutExpired as error:
                raise RouteError(f"NATIVE_ANALYZER_TIMEOUT:{executable}") from error
            _require_clang_success(validation_completed, executable)
            try:
                prelude_source.write_bytes(prelude_bytes)
                with pch_path.open("xb") as pch_output:
                    pch_completed = run_bounded(
                        pch_command,
                        cwd=source.parent,
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=_remaining_clang_timeout(deadline, executable),
                        max_stream_bytes=MAX_ALLOWED_PROCESS_STREAM_BYTES,
                        env=environment,
                        stdout_log=pch_output,
                        retain_stdout=False,
                    )
            except ProcessOutputLimitError as error:
                raise RouteError(f"NATIVE_ANALYZER_OUTPUT_LIMIT:{executable}") from error
            except subprocess.TimeoutExpired as error:
                raise RouteError(f"NATIVE_ANALYZER_TIMEOUT:{executable}") from error
            except OSError as error:
                raise RouteError(f"NATIVE_ANALYZER_PCH_IO:{executable}") from error
            _require_pch_success(pch_completed, executable, pch_replacements)
            try:
                pch_status = pch_path.stat()
            except OSError as error:
                raise RouteError(f"NATIVE_ANALYZER_PCH_IO:{executable}") from error
            if (
                pch_path.is_symlink()
                or not pch_path.is_file()
                or not 0 < pch_status.st_size <= MAX_ALLOWED_PROCESS_STREAM_BYTES
            ):
                raise RouteError(f"NATIVE_ANALYZER_PCH_INVALID:{executable}")
            if source.read_bytes() != source_snapshot:
                raise RouteError("SOURCE_CHANGED_DURING_ANALYSIS")
            try:
                analysis_source.write_bytes(masked_source_bytes)
            except OSError as error:
                raise RouteError(f"NATIVE_ANALYZER_PCH_IO:{executable}") from error
            command.extend(
                [
                    "-include-pch",
                    str(pch_path),
                    source_map,
                ]
            )
        command.extend(["-Xclang", "-ast-dump=json"])
        if declaration_filter is not None:
            # clang still parses and type-checks the complete translation unit, but
            # emits only declaration subtrees whose qualified name contains this
            # host-selected function identifier. This prevents SDK/header ASTs from
            # dominating the bounded subprocess channel.
            command.extend(["-Xclang", "-ast-dump-filter", "-Xclang", declaration_filter])
        command.extend(["-fsyntax-only", str(analysis_source)])
        try:
            completed = run_bounded(
                command,
                cwd=source.parent,
                check=False,
                capture_output=True,
                text=True,
                timeout=_remaining_clang_timeout(deadline, executable),
                max_stream_bytes=MAX_ALLOWED_PROCESS_STREAM_BYTES,
                env=environment,
            )
        except ProcessOutputLimitError as error:
            raise RouteError(f"NATIVE_ANALYZER_OUTPUT_LIMIT:{executable}") from error
        except subprocess.TimeoutExpired as error:
            raise RouteError(f"NATIVE_ANALYZER_TIMEOUT:{executable}") from error
        if source_snapshot is not None and source.read_bytes() != source_snapshot:
            raise RouteError("SOURCE_CHANGED_DURING_ANALYSIS")
    if prelude is None:
        _require_clang_success(completed, executable)
    else:
        _require_pch_success(completed, executable, pch_replacements)
    if not completed.stdout.strip():
        if declaration_filter is not None:
            return {"kind": "TranslationUnitDecl", "inner": []}
        raise RouteError(f"NATIVE_ANALYZER_FAILED:{executable}:")
    try:
        if declaration_filter is None:
            value = json.loads(completed.stdout)
        else:
            # ast-dump-filter can match more than one declaration. clang emits
            # those JSON objects consecutively, so parse the exact sequence and
            # restore the TranslationUnit shape consumed below.
            decoder = json.JSONDecoder()
            offset = 0
            declarations: list[dict[str, Any]] = []
            while offset < len(completed.stdout):
                while offset < len(completed.stdout) and completed.stdout[offset].isspace():
                    offset += 1
                if offset == len(completed.stdout):
                    break
                declaration, offset = decoder.raw_decode(completed.stdout, offset)
                if not isinstance(declaration, dict):
                    raise RouteError("NATIVE_ANALYZER_OBJECT_REQUIRED")
                declarations.append(declaration)
            value = {"kind": "TranslationUnitDecl", "inner": declarations}
    except json.JSONDecodeError as error:
        raise RouteError(f"NATIVE_ANALYZER_INVALID_JSON:{executable}") from error
    if not isinstance(value, dict):
        raise RouteError("NATIVE_ANALYZER_OBJECT_REQUIRED")
    return value


def _strip(type_name: str) -> str:
    """Drop the qualifiers the canonical model has no notion of.

    `const std::string &` is the idiomatic way to pass a string by value in
    C++; for a pure function it reads exactly like the canonical `string`.
    """
    cleaned = type_name.replace("const", " ").replace("__strong", " ").replace("&", " ").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if cleaned.endswith(" *"):
        return cleaned
    return cleaned.replace(" *", " *").strip()


def _canonical_type(type_name: str, language: Language) -> str:
    cleaned = _strip(type_name)
    integer_types = _CPP_INTEGER_TYPES if language == "cpp" else _OBJC_INTEGER_TYPES
    if cleaned in integer_types:
        return "integer"
    if language == "cpp" and cleaned == "long long":
        raise RouteError(f"CPP_INTEGER_SPELLING_OUTSIDE_EXACT_PROFILE:{type_name}")
    if cleaned in _NON_CANONICAL_INTEGER_TYPES:
        raise RouteError(f"{language.upper()}_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:{type_name}")
    if cleaned == "double":
        return "number"
    if cleaned in _BOOLEAN_TYPES:
        return "boolean"
    if cleaned in _STRING_TYPES:
        return "string"
    if cleaned == "float":
        raise RouteError(f"{language.upper()}_FLOAT_PRECISION_OUTSIDE_CERTIFIED_SUBSET:{type_name}")
    raise RouteError(f"{language.upper()}_UNSUPPORTED_TYPE:{type_name}")


def _qual_type(node: dict[str, Any]) -> str:
    value = node.get("type")
    if not isinstance(value, dict) or "qualType" not in value:
        raise RouteError("CLANG_NODE_WITHOUT_TYPE")
    return str(value["qualType"])


def _desugared_type(node: dict[str, Any]) -> str | None:
    value = node.get("type")
    if not isinstance(value, dict) or not value.get("desugaredQualType"):
        return None
    return str(value["desugaredQualType"])


def _canonical_node_type(node: dict[str, Any], language: Language) -> str:
    source_type = _qual_type(node)
    canonical = _canonical_type(source_type, language)
    if canonical != "integer":
        return canonical
    cleaned = _strip(source_type)
    direct_type = language == "objc" and cleaned == "long long"
    if direct_type:
        return canonical
    desugared = _desugared_type(node)
    if desugared is None or _strip(desugared) != "long long":
        raise RouteError(
            f"{language.upper()}_INTEGER_TYPEDEF_NOT_EXACT_INT64:{source_type}:{desugared or 'missing-desugared-type'}"
        )
    return canonical


def _return_type(function: dict[str, Any]) -> str:
    signature = _qual_type(function)
    head = signature.split("(")[0].strip()
    if not head:
        raise RouteError("CLANG_UNREADABLE_RETURN_TYPE")
    return head


def _verify_integer_return_width(
    body: dict[str, Any],
    language: Language,
    canonical_return_type: str,
) -> None:
    if canonical_return_type != "integer":
        return
    returns: list[dict[str, Any]] = []

    def visit(node: dict[str, Any]) -> None:
        if node.get("kind") == "ReturnStmt":
            returns.append(node)
        for child in _inner(node):
            visit(child)

    visit(body)
    if not returns:
        raise RouteError(f"{language.upper()}_INTEGER_FUNCTION_RETURN_REQUIRED")
    for returning in returns:
        children = _inner(returning)
        if len(children) != 1:
            raise RouteError(f"{language.upper()}_INTEGER_RETURN_EXPRESSION_REQUIRED")
        expression = children[0]
        source_type = _qual_type(expression)
        direct_type = language == "objc" and _strip(source_type) == "long long"
        desugared = _desugared_type(expression)
        if not direct_type and (desugared is None or _strip(desugared) != "long long"):
            raise RouteError(
                f"{language.upper()}_INTEGER_RETURN_NOT_EXACT_INT64:"
                f"{source_type}:{desugared or 'missing-desugared-type'}"
            )


def _inner(node: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in node.get("inner", []) if isinstance(item, dict)]


def _mapped(node: dict[str, Any], source_file: str, value: dict[str, Any]) -> dict[str, Any]:
    return {**value, "source_span": _source_span(node, source_file)}


def _boolean_literal_value(node: dict[str, Any], language: Language) -> bool:
    raw = node.get("value")
    if node.get("kind") == "CXXBoolLiteralExpr" and language == "cpp":
        if isinstance(raw, bool):
            return raw
        if raw == "true":
            return True
        if raw == "false":
            return False
        raise RouteError(f"CPP_BOOLEAN_LITERAL_AST_VALUE_INVALID:{raw!r}")
    if node.get("kind") == "ObjCBoolLiteralExpr" and language == "objc":
        if raw == "__objc_yes":
            return True
        if raw == "__objc_no":
            return False
        raise RouteError(f"OBJC_BOOLEAN_LITERAL_AST_VALUE_INVALID:{raw!r}")
    raise RouteError(f"{language.upper()}_BOOLEAN_LITERAL_AST_KIND_INVALID:{node.get('kind')}")


def _objc_stdbool_macro_value(node: dict[str, Any]) -> bool | None:
    source_range = node.get("range")
    begin = source_range.get("begin") if isinstance(source_range, dict) else None
    spelling = begin.get("spellingLoc") if isinstance(begin, dict) else None
    expansion = begin.get("expansionLoc") if isinstance(begin, dict) else None
    if not isinstance(spelling, dict) or not isinstance(expansion, dict):
        return None
    spelling_file = str(spelling.get("file", ""))
    if Path(spelling_file).name != "stdbool.h" or not isinstance(expansion.get("offset"), int):
        return None
    raw = str(node.get("value", ""))
    if raw == "0":
        return False
    if raw == "1":
        return True
    raise RouteError(f"OBJC_STDBOOL_LITERAL_AST_VALUE_INVALID:{raw!r}")


def _unwrap(node: dict[str, Any]) -> dict[str, Any]:
    while node.get("kind") in _TRANSPARENT:
        children = _inner(node)
        if len(children) != 1:
            raise RouteError(f"CPP_UNSUPPORTED_EXPRESSION:{node.get('kind')}")
        node = children[0]
    return node


def _string_message(node: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]] | None:
    """`[a isEqualToString:b]` / `[a stringByAppendingString:b]` -> canonical."""
    selector = str(node.get("selector", ""))
    operands = [_unwrap(item) for item in _inner(node)]
    if len(operands) != 2:
        return None
    if selector == "isEqualToString:":
        return "==", operands[0], operands[1]
    if selector == "stringByAppendingString:":
        return "+", operands[0], operands[1]
    return None


def _callee_name(node: dict[str, Any]) -> str:
    node = _unwrap(node)
    if node.get("kind") == "DeclRefExpr":
        referenced = node.get("referencedDecl")
        if isinstance(referenced, dict) and referenced.get("name"):
            return str(referenced["name"])
    children = _inner(node)
    return _callee_name(children[0]) if len(children) == 1 else ""


def _expression(
    node: dict[str, Any],
    language: Language,
    source_file: str,
    emitted_target: bool,
    expected_type: str | None = None,
) -> dict[str, Any]:
    node = _unwrap(node)
    kind = node.get("kind")

    if kind == "DeclRefExpr":
        referenced = node.get("referencedDecl")
        if not isinstance(referenced, dict) or not referenced.get("name"):
            raise RouteError("CLANG_UNRESOLVED_NAME")
        return _mapped(node, source_file, {"kind": "name", "value": str(referenced["name"])})

    if kind == "IntegerLiteral":
        if expected_type == "boolean":
            if language == "objc":
                value = _objc_stdbool_macro_value(node)
                if value is not None:
                    return _mapped(node, source_file, {"kind": "literal", "value": value})
            raise RouteError(f"{language.upper()}_BOOLEAN_INTEGER_COERCION_OUTSIDE_CERTIFIED_SUBSET")
        return _mapped(node, source_file, {"kind": "literal", "value": int(str(node["value"]))})
    if kind == "FloatingLiteral":
        return _mapped(node, source_file, {"kind": "literal", "value": float(str(node["value"]))})
    if kind in ("CXXBoolLiteralExpr", "ObjCBoolLiteralExpr"):
        if expected_type not in (None, "boolean"):
            raise RouteError(f"{language.upper()}_BOOLEAN_LITERAL_TYPE_MISMATCH:{expected_type}")
        return _mapped(
            node,
            source_file,
            {"kind": "literal", "value": _boolean_literal_value(node, language)},
        )
    if kind == "StringLiteral":
        return _mapped(node, source_file, {"kind": "literal", "value": json.loads(str(node["value"]))})
    if kind == "ObjCStringLiteral":
        children = _inner(node)
        if len(children) == 1:
            mapped_expression = _expression(children[0], language, source_file, emitted_target)
            return {**mapped_expression, "source_span": _source_span(node, source_file)}

    if kind == "CXXConstructExpr" and language == "cpp":
        children = _inner(node)
        if _strip(_qual_type(node)) != "std::string" or len(children) != 1:
            raise RouteError("CPP_STRING_CONSTRUCTION_OUTSIDE_CERTIFIED_SUBSET")
        child = _unwrap(children[0])
        if _strip(_qual_type(child)) not in _STRING_TYPES and child.get("kind") != "StringLiteral":
            raise RouteError("CPP_STRING_CONSTRUCTION_OUTSIDE_CERTIFIED_SUBSET")
        mapped_expression = _expression(child, language, source_file, emitted_target)
        return {**mapped_expression, "source_span": _source_span(node, source_file)}

    if kind == "BinaryOperator":
        operator = str(node.get("opcode", ""))
        if operator not in _BINARY_OPERATORS:
            raise RouteError(f"{language.upper()}_UNSUPPORTED_OPERATOR:{operator}")
        operands = _inner(node)
        if len(operands) != 2:
            raise RouteError("CLANG_MALFORMED_BINARY_OPERATOR")
        if emitted_target and operator in {"+", "-", "*", "/", "%"}:
            integer_types = _CPP_INTEGER_TYPES if language == "cpp" else _OBJC_INTEGER_TYPES

            def emitted_integer_operand(operand: dict[str, Any]) -> bool:
                unwrapped = _unwrap(operand)
                return _strip(_qual_type(unwrapped)) in integer_types or unwrapped.get("kind") == "IntegerLiteral"

            if all(emitted_integer_operand(operand) for operand in operands):
                raise RouteError(f"{language.upper()}_EMITTED_INTEGER_OPERATOR_WITHOUT_EXACT_HELPER:{operator}")
            if operator == "/":
                right = _unwrap(operands[1])
                expected_guard = "elmos_non_zero" if language == "cpp" else "ElmosNonZero"
                right_children = _inner(right)
                if _strip(_qual_type(_unwrap(operands[0]))) == "double" and (
                    right.get("kind") != "CallExpr"
                    or not right_children
                    or _callee_name(right_children[0]) != expected_guard
                ):
                    raise RouteError(f"{language.upper()}_EMITTED_FLOAT_DIVISOR_WITHOUT_EXACT_HELPER")
        if operator in ("==", "!=") and language == "objc":
            left_type = _strip(_qual_type(_unwrap(operands[0])))
            if left_type in _STRING_TYPES:
                # Pointer identity, not value equality -- see the module
                # docstring.
                raise RouteError("OBJC_STRING_POINTER_COMPARISON_OUTSIDE_CERTIFIED_SUBSET")
        return _mapped(
            node,
            source_file,
            {
                "kind": "binary",
                "operator": operator,
                "left": _expression(
                    operands[0],
                    language,
                    source_file,
                    emitted_target,
                    "boolean" if operator in {"&&", "||"} else None,
                ),
                "right": _expression(
                    operands[1],
                    language,
                    source_file,
                    emitted_target,
                    "boolean" if operator in {"&&", "||"} else None,
                ),
            },
        )

    if kind == "CXXOperatorCallExpr":
        children = _inner(node)
        if len(children) == 3:
            callee = _unwrap(children[0])
            referenced = callee.get("referencedDecl")
            name = str(referenced.get("name", "")) if isinstance(referenced, dict) else ""
            match = _OPERATOR_METHOD.match(name)
            if match:
                return _mapped(
                    node,
                    source_file,
                    {
                        "kind": "binary",
                        "operator": match.group(1),
                        "left": _expression(children[1], language, source_file, emitted_target),
                        "right": _expression(children[2], language, source_file, emitted_target),
                    },
                )

    if kind == "ObjCMessageExpr":
        lifted = _string_message(node)
        if lifted is not None:
            operator, left, right = lifted
            return _mapped(
                node,
                source_file,
                {
                    "kind": "binary",
                    "operator": operator,
                    "left": _expression(left, language, source_file, emitted_target),
                    "right": _expression(right, language, source_file, emitted_target),
                },
            )

    if kind == "CallExpr" and emitted_target:
        children = _inner(node)
        if not children:
            raise RouteError(f"{language.upper()}_EMITTED_HELPER_CALLEE_REQUIRED")
        name = _callee_name(children[0])
        helper = _EMITTED_HELPERS[language].get(name)
        if helper is None:
            raise RouteError(f"{language.upper()}_EMITTED_HELPER_UNRECOGNIZED:{name}")
        operator, arity = helper
        arguments = children[1:]
        if len(arguments) != arity:
            raise RouteError(f"{language.upper()}_EMITTED_HELPER_ARITY:{name}")
        if operator == "identity":
            mapped_expression = _expression(arguments[0], language, source_file, emitted_target)
            return {**mapped_expression, "source_span": _source_span(node, source_file)}
        return _mapped(
            node,
            source_file,
            {
                "kind": "binary",
                "operator": operator,
                "left": _expression(arguments[0], language, source_file, emitted_target),
                "right": _expression(arguments[1], language, source_file, emitted_target),
            },
        )

    raise RouteError(f"{language.upper()}_UNSUPPORTED_EXPRESSION:{kind}")


def _statements(
    nodes: list[dict[str, Any]],
    language: Language,
    source_file: str,
    emitted_target: bool,
    return_type: str,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for node in nodes:
        kind = node.get("kind")
        if kind == "ReturnStmt":
            children = _inner(node)
            if len(children) != 1:
                raise RouteError("CLANG_RETURN_WITHOUT_VALUE")
            result.append(
                _mapped(
                    node,
                    source_file,
                    {
                        "kind": "return",
                        "expression": _expression(
                            children[0],
                            language,
                            source_file,
                            emitted_target,
                            return_type,
                        ),
                    },
                )
            )
            continue
        if kind == "IfStmt":
            children = _inner(node)
            if node.get("hasInit") or node.get("isConstexpr") or len(children) < 2:
                raise RouteError(f"{language.upper()}_UNSUPPORTED_STATEMENT:IfStmt")
            condition, then_branch = children[0], children[1]
            else_branch = children[2] if node.get("hasElse") and len(children) > 2 else None
            result.append(
                _mapped(
                    node,
                    source_file,
                    {
                        "kind": "if",
                        "condition": _expression(
                            condition,
                            language,
                            source_file,
                            emitted_target,
                            "boolean",
                        ),
                        "then": _statement_body(
                            then_branch,
                            language,
                            source_file,
                            emitted_target,
                            return_type,
                        ),
                        "else": (
                            _statement_body(
                                else_branch,
                                language,
                                source_file,
                                emitted_target,
                                return_type,
                            )
                            if else_branch
                            else []
                        ),
                    },
                )
            )
            continue
        raise RouteError(f"{language.upper()}_UNSUPPORTED_STATEMENT:{kind}")
    return result


def _statement_body(
    node: dict[str, Any],
    language: Language,
    source_file: str,
    emitted_target: bool,
    return_type: str,
) -> list[dict[str, Any]]:
    if node.get("kind") == "CompoundStmt":
        return _statements(_inner(node), language, source_file, emitted_target, return_type)
    return _statements([node], language, source_file, emitted_target, return_type)


def _function(
    node: dict[str, Any],
    language: Language,
    source_file: str,
    emitted_target: bool,
) -> dict[str, Any]:
    parameters = []
    body: dict[str, Any] | None = None
    for child in _inner(node):
        if child.get("kind") == "ParmVarDecl":
            name = str(child.get("name", "")).strip()
            if not name:
                raise RouteError(f"{language.upper()}_PARAMETER_NAME_REQUIRED")
            parameters.append(
                _mapped(
                    child,
                    source_file,
                    {"name": name, "type": _canonical_node_type(child, language)},
                )
            )
        elif child.get("kind") == "CompoundStmt":
            body = child
    if body is None:
        raise RouteError(f"{language.upper()}_FUNCTION_BODY_REQUIRED")
    canonical_return_type = _canonical_type(_return_type(node), language)
    _verify_integer_return_width(body, language, canonical_return_type)
    return _mapped(
        node,
        source_file,
        {
            "name": str(node["name"]),
            "parameters": parameters,
            "return_type": canonical_return_type,
            "body": _statements(_inner(body), language, source_file, emitted_target, canonical_return_type),
        },
    )


def _is_unqualified_cpp_function(node: dict[str, Any]) -> bool:
    """Accept only a plain global C++ function from a filtered Clang root.

    ``-ast-dump-filter`` emits matching declarations without their lexical
    parents.  The compiler-owned Itanium symbol therefore remains the only
    scope identity in the JSON root: plain global names start with a decimal
    source-name length (or ``L`` plus that length for file-static functions),
    while namespace/anonymous-namespace names use the nested-name ``N`` form.
    Missing/non-Itanium names include C-linkage declarations and fail closed;
    the exact route toolchains use this ABI on both Darwin and Linux.
    """

    # Hidden friends have global Itanium linkage but are not ordinary
    # top-level declarations. Clang preserves their lexical owner explicitly
    # even when the filtered dump omits the record node.
    if node.get("parentDeclContextId") is not None:
        return False
    mangled = node.get("mangledName")
    if not isinstance(mangled, str):
        return False
    encoded = mangled.lstrip("_")
    if not encoded.startswith("Z"):
        return False
    source_name = encoded[1:]
    if source_name.startswith("L"):
        source_name = source_name[1:]
    return bool(source_name) and source_name[0].isdigit()


def analyze_clang(
    source: Path,
    language: Language,
    function_name: str,
    executable: str,
    version: str,
    *,
    emitted_target: bool = False,
    sdk_path: str | None = None,
) -> SemanticIR:
    """Lift one named C++/Objective-C function into the semantic IR."""
    if language not in ("cpp", "objc"):
        raise RouteError(f"UNSUPPORTED_SOURCE_LANGUAGE:{language}")
    tree = _run_clang(
        executable,
        source,
        language,
        sdk_path,
        declaration_filter=function_name,
    )
    candidates = [
        node
        for node in _inner(tree)
        if node.get("kind") == "FunctionDecl"
        and node.get("name") == function_name
        and not node.get("isImplicit")
        and any(child.get("kind") == "CompoundStmt" for child in _inner(node))
        and _inventory_span(node, source) is not None
        and (language != "cpp" or _is_unqualified_cpp_function(node))
    ]
    if not candidates:
        raise RouteError(f"FUNCTION_NOT_FOUND:{function_name}")
    if len(candidates) > 1:
        raise RouteError(f"AMBIGUOUS_FUNCTION_DEFINITION:{function_name}")
    semantic_markers = _function_semantic_markers(candidates[0])
    unsupported_markers = [
        marker for marker in semantic_markers if marker != "storage-class:static"
    ]
    if unsupported_markers:
        raise RouteError(
            f"{language.upper()}_FUNCTION_SEMANTIC_MARKERS_OUTSIDE_CERTIFIED_SUBSET:"
            + ",".join(unsupported_markers)
        )
    return SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": language,
            "source_file": source.name,
            "analyzer": "clang AST (JSON)",
            "analyzer_version": version,
            "functions": [_function(candidates[0], language, source.name, emitted_target)],
            "diagnostics": [],
        }
    )


def _inventory_span(
    node: dict[str, Any],
    source: Path,
) -> dict[str, object] | None:
    try:
        span = _source_span(node, source.name)
    except (KeyError, RouteError, TypeError, ValueError):
        return None
    end_byte = span.get("end_byte")
    if not isinstance(end_byte, int) or end_byte > source.stat().st_size:
        return None
    locations: list[object] = [node.get("loc")]
    source_range = node.get("range")
    if isinstance(source_range, dict):
        locations.extend((source_range.get("begin"), source_range.get("end")))
    for raw_location in locations:
        if not isinstance(raw_location, dict):
            continue
        location = raw_location
        for nested in ("expansionLoc", "spellingLoc"):
            if isinstance(location.get(nested), dict):
                location = location[nested]
                break
        if isinstance(location.get("includedFrom"), dict):
            return None
        explicit_file = location.get("file")
        if isinstance(explicit_file, str) and Path(explicit_file).name != source.name:
            return None
    return span


def _function_semantic_markers(node: dict[str, Any]) -> list[str]:
    markers: list[str] = []
    for child in _inner(node):
        kind = str(child.get("kind", ""))
        if kind == "ParmVarDecl" and (
            child.get("init") is not None or child.get("hasInheritedDefaultArg") is True
        ):
            markers.append("default-argument")
        elif kind.endswith("Attr"):
            markers.append(f"attribute:{kind}")
    for field, marker in (
        ("storageClass", "storage-class"),
        ("inline", "inline"),
        ("constexpr", "constexpr"),
        ("variadic", "variadic"),
    ):
        value = node.get(field)
        if value not in (None, False, ""):
            markers.append(f"{marker}:{value}" if not isinstance(value, bool) else marker)
    return sorted(set(markers))


def _inventory_signature(node: dict[str, Any]) -> dict[str, object]:
    parameters: list[dict[str, object]] = []
    for child in _inner(node):
        if child.get("kind") != "ParmVarDecl":
            continue
        raw_type = child.get("type")
        parameters.append(
            {
                "name": str(child.get("name", "")),
                "source_type": (
                    str(raw_type.get("qualType", "")) if isinstance(raw_type, dict) else ""
                ),
            }
        )
    raw_type = node.get("type")
    storage_class = str(node.get("storageClass", "none"))
    return {
        "parameters": parameters,
        "source_type": str(raw_type.get("qualType", "")) if isinstance(raw_type, dict) else "",
        "storage": storage_class,
        "visibility": "internal" if storage_class == "static" else "external",
        "semantic_markers": _function_semantic_markers(node),
    }


def _inventory_node_is_external(node: dict[str, Any], source: Path) -> bool:
    locations: list[object] = [node.get("loc")]
    source_range = node.get("range")
    if isinstance(source_range, dict):
        locations.extend((source_range.get("begin"), source_range.get("end")))

    def external(location: object) -> bool:
        if not isinstance(location, dict):
            return False
        if isinstance(location.get("includedFrom"), dict):
            return True
        explicit_file = location.get("file")
        if isinstance(explicit_file, str) and Path(explicit_file).name != source.name:
            return True
        return any(
            external(location.get(key))
            for key in ("expansionLoc", "spellingLoc", "includedFrom")
        )

    return any(external(location) for location in locations)


def inventory_clang_module(
    source: Path,
    language: Language,
    executable: str,
    version: str,
    *,
    sdk_path: str | None = None,
) -> dict[str, Any]:
    """Enumerate main-file declarations from clang's type-checked JSON AST."""

    if language not in ("cpp", "objc"):
        raise RouteError(f"UNSUPPORTED_SOURCE_LANGUAGE:{language}")
    tree = _run_clang(
        executable,
        source,
        language,
        sdk_path,
        precompile_system_prelude=True,
    )
    subjects: list[dict[str, object]] = []
    diagnostics: list[str] = []
    scope_kinds = {
        "CXXRecordDecl",
        "ClassTemplateDecl",
        "EnumDecl",
        "FunctionTemplateDecl",
        "LinkageSpecDecl",
        "NamespaceDecl",
        "ObjCImplementationDecl",
        "ObjCInterfaceDecl",
        "RecordDecl",
        "TypeAliasDecl",
        "TypedefDecl",
        "VarDecl",
    }

    def visit(node: dict[str, Any], scope: tuple[str, ...], *, top_level: bool) -> None:
        kind = str(node.get("kind", ""))
        name = str(node.get("name", "")).strip()
        span = _inventory_span(node, source)
        explicit_declaration = (
            kind != "TranslationUnitDecl"
            and kind.endswith("Decl")
            and not node.get("isImplicit")
        )
        if span is not None and explicit_declaration:
            if kind == "FunctionDecl" and name:
                has_body = any(child.get("kind") == "CompoundStmt" for child in _inner(node))
                semantic_markers = _function_semantic_markers(node)
                unsupported_markers = [
                    marker
                    for marker in semantic_markers
                    if marker != "storage-class:static"
                ]
                qualified_name = "::".join((*scope, name))
                subjects.append(
                    {
                        "name": name,
                        "qualified_name": qualified_name,
                        "declaration_kind": kind,
                        "analyzable": (
                            kind == "FunctionDecl"
                            and top_level
                            and has_body
                            and not unsupported_markers
                        ),
                        "source_span": span,
                        "signature": _inventory_signature(node),
                    }
                )
            else:
                obligation_name = name or f"<{kind}>"
                subjects.append(
                    {
                        "name": obligation_name,
                        "qualified_name": "::".join((*scope, obligation_name)),
                        "declaration_kind": kind,
                        "analyzable": False,
                        "source_span": span,
                        "signature": _inventory_signature(node),
                    }
                )
        elif (
            explicit_declaration
            and top_level
            and not _inventory_node_is_external(node, source)
        ):
            diagnostics.append(
                f"MAIN_FILE_DECLARATION_SPAN_INVALID:{kind}:{name or '<unnamed>'}"
            )
        child_scope = (*scope, name) if name and kind in scope_kinds else scope
        for child in _inner(node):
            if kind == "TranslationUnitDecl":
                visit(child, scope, top_level=True)
            elif kind in scope_kinds:
                # An explicit C++ linkage specification restates the language's
                # default linkage and does not introduce a lexical scope. Keep
                # the wrapper itself as an obligation, but let its plain global
                # functions retain the same analyzability as an unwrapped
                # declaration. C linkage and nested wrappers remain fail-closed.
                transparent_cpp_linkage = (
                    top_level
                    and kind == "LinkageSpecDecl"
                    and node.get("language") == "C++"
                )
                visit(child, child_scope, top_level=transparent_cpp_linkage)

    visit(tree, (), top_level=True)
    return {
        "schema_version": "1.0.0",
        "kind": "elmos.typed-pure-module-inventory",
        "profile": "typed-pure-module-v1",
        "source_language": language,
        "source_file": source.name,
        "analyzer": "clang AST (JSON)",
        "analyzer_version": version,
        "enumeration_status": "PASSED" if not diagnostics else "FAILED",
        "subjects": subjects,
        "diagnostics": sorted(set(diagnostics)),
    }
