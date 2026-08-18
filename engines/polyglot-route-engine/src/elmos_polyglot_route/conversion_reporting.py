"""Fail-closed functional conversion reports for repository migrations.

The report counts declared functional obligations, never source files.  It is
written as content-addressed JSON and Chinese Markdown, with deterministic
shards when a complete report would exceed the bounded single-file envelope.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

from .models import Language, RouteError
from .safe_io import atomic_output_file, atomic_write_bytes, stable_read_bytes

SCHEMA_VERSION = "1.0.0"
DEFINITION_ID = "verified-functional-obligation-success-rate/v1"
COMPARISON_BASIS = "DECLARED_BEHAVIOR_ORACLE"
JSON_REPORT_NAME = "functional-conversion-report.json"
MARKDOWN_REPORT_NAME = "FUNCTION_CONVERSION_REPORT.md"
REPORT_INDEX_NAME = "functional-conversion-report-index.json"
REPORT_SHARD_DIRECTORY = "functional-conversion-report-shards"
REPORT_BUNDLE_NAME = "FUNCTION_CONVERSION_REPORT_BUNDLE.zip"
REPORT_BUNDLE_MANIFEST_NAME = "FUNCTION_CONVERSION_REPORT_BUNDLE_MANIFEST.json"
MAX_REPORT_FILE_BYTES = 64 * 1024 * 1024
MAX_CODE_BLOCK_BYTES = 4 * 1024
MAX_SNIPPET_BUDGET_BYTES = 4 * 1024 * 1024
MAX_FAILURE_SUMMARIES = 50
MAX_OBLIGATIONS_PER_SHARD = 2_000
MAX_REPORT_OBLIGATIONS = MAX_OBLIGATIONS_PER_SHARD  # compatibility alias; no longer a total-row cap
MAX_TOTAL_REPORT_OBLIGATIONS = 10_000
MAX_SHARDS = 5
MAX_REPORT_BUNDLE_BYTES = 256 * 1024 * 1024
MARKDOWN_RENDERER_VERSION = "elmos-functional-conversion-markdown/v1"
_COMPLETE_FORMULA = "VERIFIED functional obligations / compiler-completely inventoried functional obligations"
_INCOMPLETE_FORMULA = (
    "Reported VERIFIED obligations / reported known callable obligations; project rate remains indeterminate "
    "because inventory-unknown or capacity-unreported functional scope remains"
)

_SAFE_REASON_CODE = re.compile(r"^[A-Z][A-Z0-9_]{2,119}$")
_UNIT_ID = re.compile(r"^WU-[0-9]{5}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _safe_relative(value: object, error_code: str) -> str:
    relative = str(value or "")
    if (
        not relative
        or len(relative) > 1_024
        or relative.startswith("/")
        or "\\" in relative
        or _CONTROL.search(relative)
        or any(part in {"", ".", ".."} for part in relative.split("/"))
    ):
        raise RouteError(f"{error_code}:{relative[:120]}")
    return relative


def _confined_file(root: Path, relative: str, error_code: str) -> Path:
    safe = _safe_relative(relative, error_code)
    root = root.resolve(strict=True)
    current = root
    for part in Path(safe).parts:
        current /= part
        if current.is_symlink():
            raise RouteError(f"{error_code}:{safe}")
    try:
        resolved = (root / safe).resolve(strict=True)
        resolved.relative_to(root)
    except (FileNotFoundError, ValueError) as error:
        raise RouteError(f"{error_code}:{safe}") from error
    if not resolved.is_file():
        raise RouteError(f"{error_code}:{safe}")
    return resolved


def _stable_bytes(path: Path, error_code: str, *, max_bytes: int = MAX_REPORT_FILE_BYTES) -> bytes:
    return stable_read_bytes(
        path,
        max_bytes=max_bytes,
        unsafe_error=f"{error_code}_MISSING_OR_UNSAFE",
        changed_error=f"{error_code}_CHANGED_DURING_READ",
        limit_error=f"{error_code}_TOO_LARGE",
    )


def _bounded(value: object, maximum: int, *, digest_long: bool = False) -> str:
    text = str(value or "").strip() or "UNKNOWN"
    text = _CONTROL.sub(" ", text)
    if len(text) <= maximum:
        return text
    suffix = f" … sha256:{_digest(text.encode('utf-8'))}"
    if digest_long:
        return text[: max(1, maximum - len(suffix))] + suffix
    return text[:maximum]


def _byte_to_position(content: bytes, offset: int) -> tuple[int, int]:
    prefix = content[:offset]
    line = prefix.count(b"\n") + 1
    last = prefix.rfind(b"\n")
    column = len(prefix) + 1 if last < 0 else len(prefix) - last
    return line, column


def _truncate_utf8(content: bytes, limit: int) -> bytes:
    if len(content) <= limit:
        return content
    candidate = content[:limit]
    while candidate:
        try:
            candidate.decode("utf-8")
            return candidate
        except UnicodeDecodeError:
            candidate = candidate[:-1]
    return b""


class _SnippetBudget:
    def __init__(self) -> None:
        self.remaining = MAX_SNIPPET_BUDGET_BYTES

    def claim(self, content: bytes) -> bytes | None:
        if self.remaining <= 0:
            return None
        bounded = _truncate_utf8(content, min(MAX_CODE_BLOCK_BYTES, self.remaining))
        if not bounded and content:
            return None
        self.remaining -= len(bounded)
        return bounded


def _not_embedded_block(
    obligation_id: str,
    direction: str,
    path: str,
    language: Language,
    document: bytes,
    symbol: str | None,
    reason: str,
    start: int,
    end: int,
    extraction_method: str,
) -> dict[str, Any]:
    start_line, start_column = _byte_to_position(document, start)
    end_line, end_column = _byte_to_position(document, end)
    return {
        "block_id": f"{obligation_id}:{direction}-001",
        "path": path,
        "language": language,
        "symbol_id": _bounded(symbol, 200, digest_long=True) if symbol else None,
        "document_bytes": len(document),
        "document_sha256": _digest(document),
        "block_sha256": _digest(document[start:end]),
        "range": {
            "start_byte": start,
            "end_byte": end,
            "start_line": start_line,
            "start_column": start_column,
            "end_line": end_line,
            "end_column": end_column,
        },
        "snippet": None,
        "truncated": True,
        "omission_reason": _bounded(reason, 120),
        "extraction_method": extraction_method,
    }


def _code_block(
    obligation_id: str,
    direction: str,
    path: str,
    language: Language,
    document: bytes,
    symbol: str | None,
    start: int,
    end: int,
    extraction_method: str,
    budget: _SnippetBudget,
) -> dict[str, Any]:
    if not (0 <= start <= end <= len(document)):
        raise RouteError("FUNCTION_REPORT_BLOCK_RANGE_INVALID")
    original = document[start:end]
    snippet = budget.claim(original)
    if snippet is None:
        return _not_embedded_block(
            obligation_id,
            direction,
            path,
            language,
            document,
            symbol,
            "GLOBAL_SNIPPET_BUDGET_EXCEEDED",
            start,
            end,
            extraction_method,
        )
    try:
        rendered = snippet.decode("utf-8")
    except UnicodeDecodeError:
        return _not_embedded_block(
            obligation_id,
            direction,
            path,
            language,
            document,
            symbol,
            "SOURCE_NOT_UTF8",
            start,
            end,
            extraction_method,
        )
    start_line, start_column = _byte_to_position(document, start)
    end_line, end_column = _byte_to_position(document, end)
    return {
        "block_id": f"{obligation_id}:{direction}-001",
        "path": path,
        "language": language,
        "symbol_id": _bounded(symbol, 200, digest_long=True) if symbol else None,
        "document_bytes": len(document),
        "document_sha256": _digest(document),
        "block_sha256": _digest(original),
        "range": {
            "start_byte": start,
            "end_byte": end,
            "start_line": start_line,
            "start_column": start_column,
            "end_line": end_line,
            "end_column": end_column,
        },
        "snippet": rendered,
        "truncated": len(snippet) < len(original),
        "omission_reason": None,
        "extraction_method": extraction_method,
    }


def sha256_file(path: Path) -> str:
    """Return a raw lowercase SHA-256 after a stable, regular-file read."""
    if path.is_symlink() or not path.is_file():
        raise RouteError("FUNCTION_REPORT_FILE_UNSAFE")
    before = path.stat(follow_symlinks=False)
    content = path.read_bytes()
    after = path.stat(follow_symlinks=False)
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns or len(content) != before.st_size:
        raise RouteError("FUNCTION_REPORT_FILE_CHANGED_DURING_READ")
    return hashlib.sha256(content).hexdigest()


def normalize_reason_code(value: object, fallback: str = "FUNCTION_CONVERSION_FAILED") -> str:
    """Map arbitrary compiler/runtime diagnostics to a machine-safe token."""
    candidate = str(value or "").split(":", 1)[0].strip().upper()
    candidate = re.sub(r"[^A-Z0-9_]+", "_", candidate).strip("_")
    if not _SAFE_REASON_CODE.fullmatch(candidate):
        return fallback
    return candidate


def _python_analysis(document: bytes, source_path: str) -> tuple[dict[str, list[tuple[int, int]]], dict[str, str]]:
    try:
        text = document.decode("utf-8")
        tree = ast.parse(text)
    except (UnicodeDecodeError, SyntaxError):
        return {}, {}
    lines = text.splitlines(keepends=True)
    line_offsets: list[int] = [0]
    for line in lines:
        line_offsets.append(line_offsets[-1] + len(line.encode("utf-8")))
    result: dict[str, list[tuple[int, int]]] = {}
    descriptions: dict[str, str] = {}

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.scope: list[str] = []

        def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            qualified = ".".join([*self.scope, node.name])
            start_line = min([node.lineno, *(item.lineno for item in node.decorator_list)])
            end_line = node.end_lineno or node.lineno
            start = line_offsets[start_line - 1]
            end = line_offsets[min(end_line, len(lines))]
            result.setdefault(qualified, []).append((start, end))
            arguments: list[str] = []
            positional = [*node.args.posonlyargs, *node.args.args]
            defaults_at = len(positional) - len(node.args.defaults)
            for index, argument in enumerate(positional):
                rendered = argument.arg
                if argument.annotation is not None:
                    rendered += f": {ast.unparse(argument.annotation)}"
                if index >= defaults_at:
                    rendered += f" = {ast.unparse(node.args.defaults[index - defaults_at])}"
                arguments.append(rendered)
            if node.args.vararg is not None:
                arguments.append(f"*{node.args.vararg.arg}")
            for argument, default in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=True):
                rendered = argument.arg
                if argument.annotation is not None:
                    rendered += f": {ast.unparse(argument.annotation)}"
                if default is not None:
                    rendered += f" = {ast.unparse(default)}"
                arguments.append(rendered)
            if node.args.kwarg is not None:
                arguments.append(f"**{node.args.kwarg.arg}")
            returns = f" -> {ast.unparse(node.returns)}" if node.returns is not None else ""
            descriptions.setdefault(
                qualified,
                _bounded(
                    f"Callable signature in {source_path}: {qualified}({', '.join(arguments)}){returns}",
                    1_000,
                    digest_long=True,
                ),
            )
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            self._function(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
            self._function(node)

    Visitor().visit(tree)
    return result, descriptions


def _name_span(document: bytes, name: str | None) -> tuple[int, int, str]:
    if name:
        encoded = name.split(".")[-1].encode("utf-8")
        match = re.search(rb"(?<![A-Za-z0-9_$])" + re.escape(encoded) + rb"(?![A-Za-z0-9_$])", document)
        if match:
            start = document.rfind(b"\n", 0, match.start()) + 1
            end = document.find(b"\n", match.end())
            if end < 0:
                end = len(document)
            else:
                end += 1
            # Include a bounded brace-delimited body when possible. This is a
            # display mapping only; eligibility still comes from native analysis.
            brace = document.find(b"{", match.end(), min(len(document), match.end() + 4_096))
            if brace >= 0:
                depth = 0
                for index in range(brace, min(len(document), brace + 64 * 1024)):
                    byte = document[index]
                    if byte == 123:
                        depth += 1
                    elif byte == 125:
                        depth -= 1
                        if depth == 0:
                            end = index + 1
                            if end < len(document) and document[end : end + 1] == b"\n":
                                end += 1
                            break
            return start, end, "NAME_ANCHORED_DOCUMENT_EXCERPT"
    return 0, len(document), "DOCUMENT_PREFIX_EXCERPT"


def _source_block(
    obligation_id: str,
    path: str,
    language: Language,
    document: bytes,
    symbol: str | None,
    python_spans: dict[str, list[tuple[int, int]]],
    occurrences: dict[str, int],
    budget: _SnippetBudget,
) -> dict[str, Any]:
    if language == "python" and symbol in python_spans:
        index = occurrences.get(symbol or "", 0)
        spans = python_spans[symbol or ""]
        start, end = spans[min(index, len(spans) - 1)]
        occurrences[symbol or ""] = index + 1
        return _code_block(
            obligation_id, "SOURCE", path, language, document, symbol, start, end, "PYTHON_AST_FUNCTION", budget
        )
    start, end, method = _name_span(document, symbol)
    return _code_block(obligation_id, "SOURCE", path, language, document, symbol, start, end, method, budget)


def _target_block(
    obligation_id: str,
    batch_output: Path,
    unit_id: str,
    outcome: dict[str, Any],
    target_language: Language,
    symbol: str | None,
    budget: _SnippetBudget,
) -> dict[str, Any] | None:
    raw_path = outcome.get("target_path")
    if raw_path is None:
        return None
    target_name = _safe_relative(raw_path, "TARGET_PATH_UNSAFE")
    if "/" in target_name:
        raise RouteError("TARGET_PATH_UNSAFE")
    unit_root = _confined_file(batch_output, f"units/{unit_id}/{target_name}", "TARGET_PATH_UNSAFE")
    content = _stable_bytes(unit_root, "TARGET")
    expected = str(outcome.get("target_sha256", ""))
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", expected):
        raise RouteError("TARGET_DIGEST_MISSING_OR_INVALID")
    if expected != f"sha256:{_digest(content)}":
        raise RouteError("TARGET_DIGEST_MISMATCH")
    start, end, method = _name_span(content, symbol)
    return _code_block(
        obligation_id,
        "TARGET",
        f"batch/units/{unit_id}/{target_name}",
        target_language,
        content,
        symbol,
        start,
        end,
        method,
        budget,
    )


def _action(obligation_id: str, reason_code: str, stage: str) -> list[dict[str, Any]]:
    if reason_code.endswith("_TIMEOUT"):
        method = "恢复隔离 Runner 健康并核对受控超时预算，再从相同源码、用例和工具链摘要重新执行。"
        steps = ["检查 Runner 资源、进程和固定超时预算。", "重跑预检、分析、全部行为用例和整库构建。"]
        automation = "ASSISTED"
    elif reason_code.startswith("EXACT_TOOLCHAIN_"):
        method = "安装并锁定报告要求的精确源/目标工具链版本，完成版本预检后重新运行全部功能。"
        steps = ["按失败详情安装或切换精确工具链版本。", "执行版本预检并从原始快照重新运行转换。"]
        automation = "ASSISTED"
    elif reason_code.startswith(("NATIVE_ANALYZER_", "SWIFT_ANALYZER_", "TYPESCRIPT_ANALYZER_")):
        method = "修复或重建内容寻址的 native analyzer，并通过协议契约测试后重新清点和转换。"
        steps = ["重建分析器并校验其版本与协议输出。", "从相同源码和用例摘要重新运行完整流水线。"]
        automation = "ASSISTED"
    elif reason_code == "SKIPPED_NO_CASES":
        method = "为该功能补充独立行为用例 JSON，覆盖正常、边界和反例后重新运行转换。"
        steps = ["创建与 work unit 对应的行为用例文件。", "重新运行 repository-pipeline 并确认行为回放通过。"]
        automation = "ASSISTED"
    elif reason_code in {"MULTIPLE_ELIGIBLE_FUNCTIONS_REQUIRE_EXPLICIT_PARTITION", "PARTITION_REQUIRED"}:
        method = "生成逐函数分区清单，并为每个函数绑定独立行为用例后分别转换。"
        steps = ["确认每个声明的唯一符号与源代码范围。", "逐函数执行并验证整库构建。"]
        automation = "ASSISTED"
    elif stage in {"TARGET_BUILD", "ASSEMBLY"}:
        method = "修复目标工程构建诊断，保留已生成代码并重新执行整库构建与行为回放。"
        steps = ["按报告中的构建错误修复目标项目。", "重新运行精确工具链构建并复核全部功能。"]
        automation = "ASSISTED"
    elif stage == "INVENTORY":
        method = "使用该源语言的编译器完整枚举函数声明，再以内容摘要绑定结果并重新生成分片报告。"
        steps = ["运行编译器级声明清单。", "确认清单覆盖完整后重新运行转换报告。"]
        automation = "AUTOMATIC"
    else:
        method = "根据失败代码收窄不支持语义，补充显式适配规则和独立回归用例后重新转换。"
        steps = ["定位失败的源语义并创建最小复现。", "实现适配并通过行为用例和整库构建。"]
        automation = "ASSISTED"
    return [
        {
            "action_id": f"{obligation_id}:ACTION-001",
            "priority": "P0"
            if stage in {"SOURCE_BEHAVIOR_REPLAY", "BEHAVIOR_REPLAY", "TARGET_BUILD", "ASSEMBLY"}
            else "P1",
            "method": method,
            "automation": automation,
            "verification_steps": steps,
        }
    ]


def _description(
    name: str | None,
    result: dict[str, Any],
    kind: str,
    python_descriptions: dict[str, str],
) -> dict[str, str]:
    if kind == "UNKNOWN_SOURCE_UNIT":
        reason = _bounded(result.get("candidate_enumeration_reason") or result.get("reason"), 700)
        return {"text": f"源文件中的功能清单无法完整枚举：{reason}", "source": "UNKNOWN"}
    if name in python_descriptions:
        return {"text": python_descriptions[name or ""], "source": "AST_SIGNATURE_DERIVED"}
    parameters = result.get("parameters")
    return_type = result.get("return_type")
    if isinstance(parameters, list) and return_type:
        rendered = ", ".join(
            f"{item.get('name', '?')}: {item.get('type', '?')}" for item in parameters if isinstance(item, dict)
        )
        return {
            "text": _bounded(f"函数 {name}({rendered}) -> {return_type}", 1_000, digest_long=True),
            "source": "IR_SIGNATURE_DERIVED",
        }
    return {"text": _bounded(f"函数 {name}", 1_000, digest_long=True), "source": "NAME_DERIVED"}


def _failure(
    stage: str,
    reason_code: object,
    description: object,
    target_present: bool,
) -> dict[str, Any]:
    code = normalize_reason_code(reason_code)
    allowed = {
        "INVENTORY",
        "ANALYSIS",
        "SOURCE_BEHAVIOR_REPLAY",
        "LOWERING",
        "EMISSION",
        "TARGET_BUILD",
        "BEHAVIOR_REPLAY",
        "ASSEMBLY",
    }
    safe_stage = stage if stage in allowed else "ANALYSIS"
    return {
        "stage": safe_stage,
        "reason_code": code,
        "description": _bounded(description or code, 2_000),
        "target_absence_reason": None if target_present else "NOT_GENERATED",
    }


def _block_mapping_precision(block: dict[str, Any] | None) -> float:
    if block is None:
        return 0.0
    method = block.get("extraction_method")
    if method == "PYTHON_AST_FUNCTION":
        return 1.0
    if method == "NAME_ANCHORED_DOCUMENT_EXCERPT":
        return 0.7
    return 0.0


def _mapping_confidence(
    source_block: dict[str, Any], target_block: dict[str, Any] | None
) -> float:
    if target_block is None:
        return 0.0
    return min(_block_mapping_precision(source_block), _block_mapping_precision(target_block))


def _row(
    obligation_id: str,
    unit_id: str,
    kind: str,
    description: dict[str, str],
    status: str,
    source_block: dict[str, Any],
    target_block: dict[str, Any] | None,
    evidence_refs: list[str],
    failure: dict[str, Any] | None,
) -> dict[str, Any]:
    target_blocks = [target_block] if target_block is not None else []
    mapping_kind = "SYNTHESIZED" if target_blocks else "UNMAPPED"
    mapping = {
        "mapping_id": f"{obligation_id}:MAP-001",
        "kind": mapping_kind,
        "freshness": "FRESH",
        # Fresh digests prove that the displayed documents are current; they do
        # not make a name-anchored or whole-document excerpt an exact mapping.
        "confidence": _mapping_confidence(source_block, target_block),
        "source_block_ids": [source_block["block_id"]],
        "target_block_ids": [item["block_id"] for item in target_blocks],
        "provenance_refs": [evidence_refs[0]],
    }
    return {
        "obligation_id": obligation_id,
        "work_unit_id": unit_id,
        "kind": kind,
        "functional_description": description,
        "status": status,
        "source_blocks": [source_block],
        "target_blocks": target_blocks,
        "mapping": mapping,
        "evidence_refs": evidence_refs,
        "failure": failure,
        "improvement_actions": (
            [] if failure is None else _action(obligation_id, failure["reason_code"], failure["stage"])
        ),
    }


def _callable_outcome(
    result: dict[str, Any],
    outcome: dict[str, Any],
    name: str,
    selected: bool,
    rejection_reason: str | None,
    build_status: str,
    build_reason: str | None,
) -> tuple[str, dict[str, Any] | None]:
    if outcome.get("analysis_incident") is True:
        reason = outcome.get("reason_code") or outcome.get("reason") or "NATIVE_ANALYSIS_NOT_RUN"
        return "NOT_RUN", _failure(
            "ANALYSIS",
            reason,
            outcome.get("reason") or reason,
            False,
        )
    if not selected:
        reason = rejection_reason or result.get("reason") or "DECLARATION_NOT_SELECTED_FOR_BOUNDED_ROUTE"
        return "UNSUPPORTED", _failure("ANALYSIS", reason, reason, False)
    batch_status = str(outcome.get("status", "NOT_RUN"))
    if batch_status == "PASSED":
        if build_status == "PASSED":
            return "VERIFIED", None
        reason = build_reason or ("ASSEMBLY_BUILD_NOT_RUN" if build_status == "NOT_RUN" else "ASSEMBLY_BUILD_FAILED")
        return "FAILED", _failure("ASSEMBLY", reason, reason, bool(outcome.get("target_path")))
    if batch_status == "FAILED":
        stage = str(outcome.get("failure_stage") or "BEHAVIOR_REPLAY")
        reason = outcome.get("reason_code") or outcome.get("reason") or "FUNCTION_CONVERSION_FAILED"
        return "FAILED", _failure(stage, reason, outcome.get("reason") or reason, bool(outcome.get("target_path")))
    if batch_status == "SKIPPED_NO_CASES":
        return "NOT_RUN", _failure(
            "BEHAVIOR_REPLAY",
            "SKIPPED_NO_CASES",
            outcome.get("reason") or "No independent behavior-case corpus was supplied for this function.",
            False,
        )
    reason = outcome.get("reason_code") or result.get("verdict") or "FUNCTION_CONVERSION_NOT_RUN"
    return "NOT_RUN", _failure(
        str(outcome.get("failure_stage") or "ANALYSIS"), reason, outcome.get("reason") or reason, False
    )


def _validate_inputs(
    discovery: dict[str, Any],
    batch: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    if discovery.get("kind") != "elmos.repository-discovery-report":
        raise RouteError("FUNCTION_REPORT_DISCOVERY_KIND_INVALID")
    if batch.get("kind") != "elmos.repository-batch-report":
        raise RouteError("FUNCTION_REPORT_BATCH_KIND_INVALID")
    results = discovery.get("results")
    units = batch.get("units")
    if not isinstance(results, list) or not results or not isinstance(units, list):
        raise RouteError("FUNCTION_REPORT_INPUTS_INCOMPLETE")
    outcomes: dict[str, dict[str, Any]] = {}
    for raw in units:
        if not isinstance(raw, dict):
            raise RouteError("FUNCTION_REPORT_BATCH_UNIT_INVALID")
        unit_id = str(raw.get("id", ""))
        if not _UNIT_ID.fullmatch(unit_id) or unit_id in outcomes:
            raise RouteError("FUNCTION_REPORT_BATCH_UNIT_ID_INVALID")
        outcomes[unit_id] = raw
    result_ids = [str(item.get("id", "")) for item in results if isinstance(item, dict)]
    if len(result_ids) != len(results) or len(set(result_ids)) != len(result_ids) or set(result_ids) != set(outcomes):
        raise RouteError("FUNCTION_REPORT_WORK_UNIT_SET_MISMATCH")
    if any(not _UNIT_ID.fullmatch(unit_id) for unit_id in result_ids):
        raise RouteError("FUNCTION_REPORT_WORK_UNIT_ID_INVALID")
    return results, outcomes


def build_conversion_report(
    discovery: dict[str, Any],
    batch: dict[str, Any],
    repository_root: Path,
    batch_output: Path,
    *,
    build_status: str,
    build_reason: str | None = None,
    cases_manifest_sha256: str | None = None,
    code_artifact_ready: bool | None = None,
) -> dict[str, Any]:
    """Build the complete logical report before selecting single/sharded storage."""
    results, outcomes = _validate_inputs(discovery, batch)
    source_language = str(discovery.get("source_language", ""))
    target_language = str(discovery.get("target_language", ""))
    languages = {"java", "python", "csharp", "typescript", "go", "rust", "cpp", "objc", "swift"}
    if source_language not in languages or target_language not in languages:
        raise RouteError("FUNCTION_REPORT_LANGUAGE_INVALID")
    if build_status not in {"PASSED", "FAILED", "NOT_RUN"}:
        raise RouteError("FUNCTION_REPORT_BUILD_STATUS_INVALID")
    if cases_manifest_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", cases_manifest_sha256):
        raise RouteError("CASES_MANIFEST_DIGEST_INVALID")
    root = repository_root.resolve(strict=True)
    budget = _SnippetBudget()
    functions: list[dict[str, Any]] = []

    for result in results:
        unit_id = str(result["id"])
        outcome = outcomes[unit_id]
        source_path = _safe_relative(result.get("source_path"), "SOURCE_PATH_UNSAFE")
        source_file = _confined_file(root, source_path, "SOURCE_PATH_UNSAFE")
        source = _stable_bytes(source_file, "SOURCE")
        observed = str(result.get("observed_sha256") or result.get("declared_sha256") or "")
        if not re.fullmatch(r"[0-9a-f]{64}", observed) or _digest(source) != observed:
            raise RouteError("SOURCE_DIGEST_MISMATCH")
        python_spans, python_descriptions = (
            _python_analysis(source, source_path) if source_language == "python" else ({}, {})
        )
        occurrences: dict[str, int] = {}
        raw_candidates = result.get("candidates", [])
        candidates = [str(item) for item in raw_candidates] if isinstance(raw_candidates, list) else []
        if len(functions) + len(candidates) + 1 > MAX_TOTAL_REPORT_OBLIGATIONS + 1:
            raise RouteError("FUNCTIONAL_OBLIGATION_LIMIT_EXCEEDED")
        rejections: dict[str, list[str]] = {}
        for rejection in result.get("rejected_candidates", []):
            if isinstance(rejection, dict):
                rejections.setdefault(str(rejection.get("candidate", "")), []).append(str(rejection.get("reason", "")))
        selected_name = str(result.get("function_name", "")) if result.get("verdict") == "READY" else ""
        selected_consumed = False
        for index, name in enumerate(candidates, start=1):
            obligation_id = f"{unit_id}:FO-{index:03d}"
            selected = bool(selected_name and name == selected_name and not selected_consumed)
            if selected:
                selected_consumed = True
            rejection_list = rejections.get(name, [])
            rejection = rejection_list.pop(0) if rejection_list else None
            status, failure = _callable_outcome(
                result, outcome, name, selected, rejection, build_status, build_reason
            )
            source_block = _source_block(
                obligation_id,
                source_path,
                source_language,  # type: ignore[arg-type]
                source,
                name,
                python_spans,
                occurrences,
                budget,
            )
            target_block = None
            if selected and outcome.get("target_path"):
                target_block = _target_block(
                    obligation_id,
                    batch_output,
                    unit_id,
                    outcome,
                    target_language,  # type: ignore[arg-type]
                    name,
                    budget,
                )
            if failure is not None:
                failure["target_absence_reason"] = None if target_block else "NOT_GENERATED"
            evidence = [
                f"repository-discovery-report.json#results/{unit_id}",
                f"batch/batch-report.json#units/{unit_id}",
            ]
            if selected and outcome.get("evidence_path"):
                evidence.append(f"batch/{_safe_relative(outcome['evidence_path'], 'EVIDENCE_PATH_UNSAFE')}")
            functions.append(
                _row(
                    obligation_id,
                    unit_id,
                    "CALLABLE",
                    _description(name, result, "CALLABLE", python_descriptions),
                    status,
                    source_block,
                    target_block,
                    evidence,
                    failure,
                )
            )

        enumeration_complete = bool(result.get("candidate_enumeration_complete", source_language == "python"))
        if not candidates or not enumeration_complete:
            index = len(candidates) + 1
            obligation_id = f"{unit_id}:FO-{index:03d}"
            reason = (
                result.get("candidate_enumeration_reason")
                or result.get("reason")
                or "FUNCTION_INVENTORY_INCOMPLETE"
            )
            source_block = _source_block(
                obligation_id,
                source_path,
                source_language,  # type: ignore[arg-type]
                source,
                None,
                python_spans,
                occurrences,
                budget,
            )
            failure = _failure("INVENTORY", reason, reason, False)
            functions.append(
                _row(
                    obligation_id,
                    unit_id,
                    "UNKNOWN_SOURCE_UNIT",
                    _description(None, result, "UNKNOWN_SOURCE_UNIT", python_descriptions),
                    "UNKNOWN",
                    source_block,
                    None,
                    [f"repository-discovery-report.json#results/{unit_id}"],
                    failure,
                )
            )

    if not functions:
        raise RouteError("FUNCTION_REPORT_NO_OBLIGATIONS")
    if len(functions) > MAX_TOTAL_REPORT_OBLIGATIONS:
        raise RouteError("FUNCTIONAL_OBLIGATION_LIMIT_EXCEEDED")
    counts = dict(Counter(str(item["status"]) for item in functions))
    numerator = counts.get("VERIFIED", 0)
    denominator = sum(1 for item in functions if item["kind"] == "CALLABLE")
    unknown = len(functions) - denominator
    denominator_complete = unknown == 0
    basis_points = (numerator * 10_000 // denominator) if denominator else 0
    display = f"{basis_points / 100:.2f}%"
    measurement_status = "MEASURED" if denominator_complete else "INDETERMINATE"
    project_display = display if denominator_complete else "0.00%–100.00% (INDETERMINATE)"
    if numerator == len(functions) and denominator_complete and build_status == "PASSED":
        status = "COMPLETE"
    elif numerator == 0:
        status = "BLOCKED"
    else:
        status = "PARTIAL"
    metric = {
        "definition_id": DEFINITION_ID,
        "measurement_unit": "FUNCTIONAL_OBLIGATION",
        "comparison_basis": COMPARISON_BASIS,
        "numerator": numerator,
        "denominator": denominator,
        "exact_fraction": f"{numerator}/{denominator}",
        "success_rate_basis_points": basis_points,
        "display_percent": display,
        "measurement_status": measurement_status,
        "denominator_complete": denominator_complete,
        "reported_obligation_count": len(functions),
        "unknown_scope_count": unknown,
        "unreported_obligation_count": 0,
        "project_success_rate_lower_bound_basis_points": basis_points if denominator_complete else 0,
        "project_success_rate_upper_bound_basis_points": basis_points if denominator_complete else 10_000,
        "project_success_rate_display": project_display,
        "formula": _COMPLETE_FORMULA if denominator_complete else _INCOMPLETE_FORMULA,
    }
    blockers = [item["failure"]["reason_code"] for item in functions if item["failure"] is not None]
    evidence_boundary: dict[str, Any] = {
        "local_target_build": build_status,
        "target_behavior_oracle": "PASSED_PER_VERIFIED_FUNCTION" if numerator > 0 else "NOT_RUN",
        "source_target_declared_case_equivalence": (
            "PASSED_PER_VERIFIED_FUNCTION" if numerator > 0 else "NOT_RUN"
        ),
        "source_target_runtime_equivalence": "NOT_RUN",
        "independent_verification": "NOT_RUN",
        "external_verification": "NOT_RUN",
    }
    if cases_manifest_sha256 is not None:
        evidence_boundary["cases_manifest_sha256"] = cases_manifest_sha256
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "elmos.project-language-conversion-report",
        "report_id": "sha256:" + "0" * 64,
        "status": status,
        "repository": {
            "reference": _bounded(discovery.get("repository_ref"), 180),
            "snapshot_sha256": str(discovery.get("snapshot_sha256")),
        },
        "route": {
            "route_id": _bounded(discovery.get("route_id"), 100),
            "source_language": source_language,
            "target_language": target_language,
            "profile": _bounded(discovery.get("profile"), 100),
        },
        "metric": metric,
        "status_counts": counts,
        "code_artifact_ready": (
            code_artifact_ready
            if code_artifact_ready is not None
            else build_status == "PASSED" and numerator > 0
        ),
        "functions": functions,
        "exclusions": [],
        "blockers": blockers,
        "build_verification": {
            "status": build_status,
            "reason": _bounded(build_reason, 4_000) if build_reason else None,
        },
        "evidence_boundary": evidence_boundary,
        "markdown_renderer_version": MARKDOWN_RENDERER_VERSION,
        "markdown_sha256": "0" * 64,
        "certification_status": "NOT_CERTIFIED",
    }
    report["report_id"] = _report_id(report)
    markdown = render_conversion_markdown(report)
    report["markdown_sha256"] = _digest(markdown.encode("utf-8"))
    validate_conversion_report(report)
    return report


def _report_id(report: dict[str, Any]) -> str:
    identity = copy.deepcopy(report)
    identity.pop("report_id", None)
    identity.pop("markdown_sha256", None)
    identity.pop("code_artifact_ready", None)
    identity.pop("storage_mode", None)
    identity.pop("shard_count", None)
    identity.pop("total_shard_bytes", None)
    identity.pop("shards", None)
    return "sha256:" + _digest(json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


def _markdown_plain(value: object) -> str:
    text = _CONTROL.sub(" ", str(value or ""))
    for source, replacement in (
        ("!", "！"),
        ("[", "［"),
        ("]", "］"),
        ("(", "（"),
        (")", "）"),
        ("<", "＜"),
        (">", "＞"),
        ("&", "＆"),
    ):
        text = text.replace(source, replacement)
    return text


def _fenced(snippet: str, language: str) -> str:
    runs = [len(match.group(0)) for match in re.finditer(r"`+", snippet)]
    fence = "`" * max(3, (max(runs) + 1) if runs else 3)
    return f"{fence}{language}\n{snippet}\n{fence}"


def _render_block(block: dict[str, Any] | None, language: str, absent: str) -> str:
    if block is None:
        return _fenced(absent, language)
    snippet = block.get("snippet")
    if not isinstance(snippet, str):
        reason = str(block.get("omission_reason") or "NOT_EMBEDDED")
        return _fenced(f"NOT_EMBEDDED: {reason}", language)
    return _fenced(snippet, language)


def _render_block_metadata(block: dict[str, Any] | None, absent: str) -> list[str]:
    if block is None:
        return [f"- 状态：`{_markdown_plain(absent)}`"]
    value_range = block["range"]
    method = block["extraction_method"]
    precision = {
        "PYTHON_AST_FUNCTION": "EXACT_DECLARATION_RANGE",
        "NAME_ANCHORED_DOCUMENT_EXCERPT": "APPROXIMATE_NAME_ANCHORED_RANGE",
        "DOCUMENT_PREFIX_EXCERPT": "UNMAPPED_DOCUMENT_RANGE",
    }.get(method, "UNMAPPED_DOCUMENT_RANGE")
    return [
        f"- 路径：`{_markdown_plain(block['path'])}`",
        (
            "- 字节范围："
            f"`{value_range['start_byte']}..{value_range['end_byte']}`；"
            "行列范围："
            f"`{value_range['start_line']}:{value_range['start_column']}.."
            f"{value_range['end_line']}:{value_range['end_column']}`"
        ),
        f"- 代码块 SHA-256：`{block['block_sha256']}`",
        f"- 文档 SHA-256：`{block['document_sha256']}`",
        f"- 提取方式：`{_markdown_plain(block['extraction_method'])}`",
        f"- 范围精度：`{precision}`",
    ]


def render_conversion_markdown(report: dict[str, Any], *, shard_heading: str | None = None) -> str:
    metric = report["metric"]
    source_language = str(report["route"]["source_language"])
    target_language = str(report["route"]["target_language"])
    lines = ["# 项目语言功能转换报告", ""]
    if shard_heading:
        lines.extend([f"> {_markdown_plain(shard_heading)}", ""])
    lines.extend(
        [
            "## 转换总览",
            "",
            f"- 路由：`{_markdown_plain(report['route']['route_id'])}`",
            f"- 原语言：`{source_language}`；目标语言：`{target_language}`",
            f"- 报告状态：`{report['status']}`",
            f"- 代码工件可交付：`{str(report['code_artifact_ready']).lower()}`",
            f"- 已验证功能：`{metric['numerator']}`；已报告可调用功能：`{metric['denominator']}`",
        ]
    )
    if metric["denominator"]:
        lines.append(f"- 功能转换成功率：`{metric['exact_fraction']} = {metric['display_percent']}`")
    else:
        lines.append("- 已报告可调用功能成功率：N/A (NO_REPORTED_CALLABLE_DENOMINATOR)")
    lines.extend(
        [
            f"- 项目成功率：`{metric['project_success_rate_display']}`",
            f"- 分母是否完整：`{str(metric['denominator_complete']).lower()}`",
            "",
            "## 证据边界",
            "",
            "本报告的比较基础为 DECLARED_BEHAVIOR_ORACLE；源/目标运行时等价仍为 NOT_RUN。",
            "独立验证与外部认证保持 NOT_RUN / NOT_CERTIFIED。",
            "",
            "## 逐功能转换结果",
            "",
        ]
    )
    for item in report.get("functions", []):
        source_block = item["source_blocks"][0]
        target_block = item["target_blocks"][0] if item["target_blocks"] else None
        lines.extend(
            [
                f"### {_markdown_plain(item['obligation_id'])} — {_markdown_plain(item['status'])}",
                "",
                f"功能描述：{_markdown_plain(item['functional_description']['text'])}",
                "",
                "原代码块：",
                "",
                *_render_block_metadata(source_block, "SOURCE_NOT_AVAILABLE"),
                "",
                _render_block(source_block, source_language, "SOURCE_NOT_AVAILABLE"),
                "",
                "目标代码块：",
                "",
                *_render_block_metadata(target_block, "NOT_GENERATED"),
                "",
                _render_block(target_block, target_language, "NOT_GENERATED"),
                "",
                (
                    f"映射置信度：`{item['mapping']['confidence']:.2f}`（`"
                    + (
                        "EXACT"
                        if item["mapping"]["confidence"] == 1.0
                        else "APPROXIMATE"
                        if item["mapping"]["confidence"] > 0.0
                        else "UNMAPPED"
                    )
                    + "`）"
                ),
                "",
            ]
        )
        failure = item.get("failure")
        if isinstance(failure, dict):
            lines.extend(
                [
                    f"失败阶段：`{_markdown_plain(failure['stage'])}`",
                    f"失败代码：`{_markdown_plain(failure['reason_code'])}`",
                    f"未成功原因：{_markdown_plain(failure['description'])}",
                    "",
                    "后续提高成功率的方法：",
                    "",
                ]
            )
            for action in item["improvement_actions"]:
                lines.append(f"1. {_markdown_plain(action['method'])}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _validate_block(block: dict[str, Any], obligation_id: str, direction: str) -> None:
    if block.get("block_id") != f"{obligation_id}:{direction}-001":
        raise RouteError("FUNCTION_REPORT_BLOCK_ID_INVALID")
    _safe_relative(block.get("path"), "FUNCTION_REPORT_BLOCK_PATH_INVALID")
    digest = block.get("document_sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise RouteError("FUNCTION_REPORT_DOCUMENT_DIGEST_INVALID")
    block_digest = block.get("block_sha256")
    value_range = block.get("range")
    if not isinstance(block_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", block_digest):
        raise RouteError("FUNCTION_REPORT_BLOCK_DIGEST_INVALID")
    if not isinstance(value_range, dict):
        raise RouteError("FUNCTION_REPORT_BLOCK_RANGE_INVALID")
    start = int(value_range.get("start_byte", -1))
    end = int(value_range.get("end_byte", -1))
    if not 0 <= start <= end <= int(block.get("document_bytes", -1)):
        raise RouteError("FUNCTION_REPORT_BLOCK_RANGE_INVALID")
    snippet = block.get("snippet")
    if snippet is None:
        if not block.get("truncated") or not block.get("omission_reason"):
            raise RouteError("FUNCTION_REPORT_OMITTED_BLOCK_INVALID")
        return
    if not isinstance(snippet, str):
        raise RouteError("FUNCTION_REPORT_BLOCK_SNIPPET_INVALID")
    encoded = snippet.encode("utf-8")
    if len(encoded) > MAX_CODE_BLOCK_BYTES or len(encoded) > end - start:
        raise RouteError("FUNCTION_REPORT_BLOCK_DIGEST_INVALID")
    if not block.get("truncated") and (end - start != len(encoded) or block_digest != _digest(encoded)):
        raise RouteError("FUNCTION_REPORT_BLOCK_DIGEST_INVALID")


def validate_conversion_report(report: dict[str, Any]) -> None:
    if report.get("kind") != "elmos.project-language-conversion-report":
        raise RouteError("FUNCTION_REPORT_KIND_INVALID")
    if not isinstance(report.get("code_artifact_ready"), bool):
        raise RouteError("FUNCTION_REPORT_CODE_ARTIFACT_READINESS_INVALID")
    functions = report.get("functions")
    if not isinstance(functions, list) or not functions or len(functions) > MAX_TOTAL_REPORT_OBLIGATIONS:
        raise RouteError("FUNCTION_REPORT_FUNCTIONS_INVALID")
    seen: set[str] = set()
    counts: Counter[str] = Counter()
    callable_count = 0
    unknown_count = 0
    for item in functions:
        if not isinstance(item, dict):
            raise RouteError("FUNCTION_REPORT_ROW_INVALID")
        obligation_id = str(item.get("obligation_id", ""))
        if obligation_id in seen or not re.fullmatch(r"WU-[0-9]{5}:FO-[0-9]{3,6}", obligation_id):
            raise RouteError("FUNCTION_REPORT_OBLIGATION_ID_INVALID")
        seen.add(obligation_id)
        status = str(item.get("status", ""))
        if status not in {"VERIFIED", "FAILED", "UNSUPPORTED", "NOT_RUN", "UNKNOWN"}:
            raise RouteError("FUNCTION_REPORT_STATUS_INVALID")
        counts[status] += 1
        kind = item.get("kind")
        if kind == "CALLABLE":
            callable_count += 1
        elif kind == "UNKNOWN_SOURCE_UNIT" and status == "UNKNOWN":
            unknown_count += 1
        else:
            raise RouteError("FUNCTION_REPORT_KIND_STATUS_INVALID")
        source_blocks = item.get("source_blocks")
        target_blocks = item.get("target_blocks")
        if not isinstance(source_blocks, list) or len(source_blocks) != 1 or not isinstance(target_blocks, list):
            raise RouteError("FUNCTION_REPORT_BLOCKS_INVALID")
        _validate_block(source_blocks[0], obligation_id, "SOURCE")
        if len(target_blocks) > 1:
            raise RouteError("FUNCTION_REPORT_BLOCKS_INVALID")
        if target_blocks:
            _validate_block(target_blocks[0], obligation_id, "TARGET")
        mapping = item.get("mapping")
        target_block = target_blocks[0] if target_blocks else None
        evidence_refs = item.get("evidence_refs")
        if (
            not isinstance(mapping, dict)
            or not isinstance(evidence_refs, list)
            or not evidence_refs
            or mapping.get("mapping_id") != f"{obligation_id}:MAP-001"
            or mapping.get("kind") != ("SYNTHESIZED" if target_blocks else "UNMAPPED")
            or mapping.get("freshness") != "FRESH"
            or mapping.get("confidence") != _mapping_confidence(source_blocks[0], target_block)
            or mapping.get("source_block_ids") != [source_blocks[0]["block_id"]]
            or mapping.get("target_block_ids")
            != ([target_block["block_id"]] if target_block is not None else [])
            or mapping.get("provenance_refs") != [evidence_refs[0]]
        ):
            raise RouteError("FUNCTION_REPORT_MAPPING_INVALID")
        failure = item.get("failure")
        actions = item.get("improvement_actions")
        if status == "VERIFIED":
            if failure is not None or actions != [] or not target_blocks:
                raise RouteError("FUNCTION_REPORT_VERIFIED_ROW_INVALID")
        elif not isinstance(failure, dict) or not isinstance(actions, list) or not actions:
            raise RouteError("FUNCTION_REPORT_FAILURE_DETAIL_REQUIRED")
    metric = report.get("metric")
    if not isinstance(metric, dict):
        raise RouteError("METRIC_INCONSISTENT")
    numerator = counts.get("VERIFIED", 0)
    expected_bp = numerator * 10_000 // callable_count if callable_count else 0
    complete = unknown_count == 0 and metric.get("unreported_obligation_count") == 0
    if (
        report.get("status_counts") != dict(counts)
        or metric.get("definition_id") != DEFINITION_ID
        or metric.get("comparison_basis") != COMPARISON_BASIS
        or metric.get("numerator") != numerator
        or metric.get("denominator") != callable_count
        or metric.get("exact_fraction") != f"{numerator}/{callable_count}"
        or metric.get("success_rate_basis_points") != expected_bp
        or metric.get("display_percent") != f"{expected_bp / 100:.2f}%"
        or metric.get("reported_obligation_count") != len(functions)
        or metric.get("unknown_scope_count") != unknown_count
        or metric.get("denominator_complete") is not complete
        or metric.get("measurement_status") != ("MEASURED" if complete else "INDETERMINATE")
    ):
        raise RouteError("METRIC_INCONSISTENT")
    if report.get("blockers") != [item["failure"]["reason_code"] for item in functions if item["failure"]]:
        raise RouteError("FUNCTION_REPORT_BLOCKERS_INVALID")
    if report["code_artifact_ready"] and (
        report.get("build_verification", {}).get("status") != "PASSED" or numerator == 0
    ):
        raise RouteError("FUNCTION_REPORT_CODE_ARTIFACT_READINESS_INVALID")
    if report.get("report_id") != _report_id(report):
        raise RouteError("FUNCTION_REPORT_ID_MISMATCH")
    rendered = render_conversion_markdown(report)
    if report.get("markdown_sha256") != _digest(rendered.encode("utf-8")):
        raise RouteError("MARKDOWN_DIGEST_MISMATCH")


def _atomic_write(path: Path, content: bytes) -> dict[str, Any]:
    atomic_write_bytes(
        path,
        content,
        max_bytes=MAX_REPORT_FILE_BYTES,
        unsafe_error="FUNCTION_REPORT_OUTPUT_UNSAFE",
        limit_error=f"FUNCTION_REPORT_FILE_LIMIT_EXCEEDED:{path.name}",
    )
    return {"path": path.as_posix(), "bytes": len(content), "sha256": _digest(content)}


def _relative_descriptor(output: Path, descriptor: dict[str, Any]) -> dict[str, Any]:
    path = Path(str(descriptor["path"]))
    try:
        relative = path.relative_to(output).as_posix()
    except ValueError as error:
        raise RouteError("FUNCTION_REPORT_DESCRIPTOR_ESCAPES_OUTPUT") from error
    _safe_relative(relative, "FUNCTION_REPORT_DESCRIPTOR_PATH_INVALID")
    return {**descriptor, "path": relative}


def reset_conversion_report_outputs(output: Path) -> None:
    if output.exists() and (output.is_symlink() or not output.is_dir()):
        raise RouteError("FUNCTION_REPORT_OUTPUT_UNSAFE")
    output.mkdir(parents=True, exist_ok=True)
    for name in (
        JSON_REPORT_NAME,
        MARKDOWN_REPORT_NAME,
        REPORT_INDEX_NAME,
        REPORT_BUNDLE_NAME,
        REPORT_BUNDLE_MANIFEST_NAME,
    ):
        path = output / name
        if path.is_symlink():
            raise RouteError("FUNCTION_REPORT_OUTPUT_UNSAFE")
        if path.exists():
            if not path.is_file():
                raise RouteError("FUNCTION_REPORT_OUTPUT_UNSAFE")
            path.unlink()
    shard_directory = output / REPORT_SHARD_DIRECTORY
    if shard_directory.is_symlink():
        raise RouteError("FUNCTION_REPORT_OUTPUT_UNSAFE")
    if shard_directory.exists():
        if not shard_directory.is_dir():
            raise RouteError("FUNCTION_REPORT_OUTPUT_UNSAFE")
        for path in sorted(shard_directory.rglob("*"), reverse=True):
            if path.is_symlink():
                raise RouteError("FUNCTION_REPORT_OUTPUT_UNSAFE")
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        shard_directory.rmdir()


def _failure_summaries(report: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for item in report["functions"]:
        failure = item["failure"]
        if failure is None:
            continue
        failures.append(
            {
                "obligation_id": item["obligation_id"],
                "work_unit_id": item["work_unit_id"],
                "function_description": _bounded(item["functional_description"]["text"], 600),
                "source_path": item["source_blocks"][0]["path"],
                "target_path": item["target_blocks"][0]["path"] if item["target_blocks"] else None,
                "status": item["status"],
                "failure_code": failure["reason_code"],
                "failure_reason": _bounded(failure["description"], 1_200),
                "improvement_actions": [
                    _bounded(action["method"], 600) for action in item["improvement_actions"]
                ],
            }
        )
    return failures[:MAX_FAILURE_SUMMARIES]


def _summary(
    report: dict[str, Any],
    json_descriptor: dict[str, Any],
    markdown_descriptor: dict[str, Any],
    *,
    storage_mode: str,
    shard_count: int,
    total_shard_bytes: int,
    report_bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metric = report["metric"]
    failed_count = len(report["functions"]) - int(metric["numerator"])
    failures = _failure_summaries(report)
    summary = {
        "report_id": report["report_id"],
        "definition_id": metric["definition_id"],
        "measurement_unit": metric["measurement_unit"],
        "comparison_basis": metric["comparison_basis"],
        "numerator": metric["numerator"],
        "denominator": metric["denominator"],
        "exact_fraction": metric["exact_fraction"],
        "success_rate_basis_points": metric["success_rate_basis_points"],
        "display_percent": metric["display_percent"],
        "measurement_status": metric["measurement_status"],
        "denominator_complete": metric["denominator_complete"],
        "reported_obligation_count": metric["reported_obligation_count"],
        "unknown_scope_count": metric["unknown_scope_count"],
        "unreported_obligation_count": metric["unreported_obligation_count"],
        "project_success_rate_lower_bound_basis_points": metric[
            "project_success_rate_lower_bound_basis_points"
        ],
        "project_success_rate_upper_bound_basis_points": metric[
            "project_success_rate_upper_bound_basis_points"
        ],
        "project_success_rate_display": metric["project_success_rate_display"],
        "verified_count": metric["numerator"],
        "failed_count": failed_count,
        "code_artifact_ready": report["code_artifact_ready"],
        "status_counts": report["status_counts"],
        "failure_summary_count": len(failures),
        "total_failure_count": failed_count,
        "failure_summaries_truncated": failed_count > len(failures),
        "failure_summaries": failures,
        "json_report": json_descriptor,
        "markdown_report": markdown_descriptor,
        "storage_mode": storage_mode,
        "shard_count": shard_count,
        "total_shard_bytes": total_shard_bytes,
    }
    cases_digest = report.get("evidence_boundary", {}).get("cases_manifest_sha256")
    if cases_digest is not None:
        summary["cases_manifest_sha256"] = cases_digest
    if report_bundle is not None:
        summary["report_bundle"] = report_bundle
    return summary


def _render_index_markdown(index: dict[str, Any]) -> str:
    metric = index["metric"]
    lines = [
        "# 项目语言功能转换报告（分片索引）",
        "",
        "## 转换总览",
        "",
        f"- 报告 ID：`{index['report_id']}`",
        f"- 路由：`{index['route']['route_id']}`",
        f"- 功能转换成功率：`{metric['exact_fraction']} = {metric['display_percent']}`",
        f"- 项目成功率：`{metric['project_success_rate_display']}`",
        f"- 代码工件可交付：`{str(index['code_artifact_ready']).lower()}`",
        f"- 功能总数：`{metric['reported_obligation_count']}`",
        f"- 分片数：`{index['shard_count']}`",
        f"- 分片文件总字节：`{index['total_shard_bytes']}`",
        "",
        "## 分片目录",
        "",
    ]
    for shard in index["shards"]:
        lines.extend(
            [
                f"### 分片 {shard['sequence']:05d}",
                "",
                f"- 功能数：`{shard['function_count']}`",
                f"- 义务 ID 摘要：`{shard['obligation_ids_sha256']}`",
                f"- JSON：`{shard['json']['path']}` (`{shard['json']['sha256']}`)",
                f"- Markdown：`{shard['markdown']['path']}` (`{shard['markdown']['sha256']}`)",
                "",
            ]
        )
    lines.extend(
        [
            "## 证据边界",
            "",
            "所有指标均由上述全部分片重新聚合；容量分片不制造 UNKNOWN，也不缩减分母。",
            "源/目标运行时等价仍为 NOT_RUN；独立验证与外部认证保持 NOT_RUN / NOT_CERTIFIED。",
            "",
        ]
    )
    return "\n".join(lines)


def _write_bundle(output: Path, files: list[dict[str, Any]], report_id: str) -> dict[str, Any]:
    unique_paths = [str(item["path"]) for item in files]
    if len(unique_paths) != len(set(unique_paths)):
        raise RouteError("FUNCTION_REPORT_BUNDLE_DUPLICATE_PATH")
    total_uncompressed = sum(int(item["bytes"]) for item in files)
    manifest_files: list[dict[str, Any]] = sorted(files, key=lambda item: str(item["path"]))
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "kind": "elmos.project-language-conversion-report-bundle-manifest",
        "report_id": report_id,
        "file_count": len(files),
        "total_uncompressed_bytes": total_uncompressed,
        "files": manifest_files,
    }
    manifest_bytes = _json_bytes(manifest)
    if total_uncompressed + len(manifest_bytes) > MAX_REPORT_BUNDLE_BYTES:
        raise RouteError("FUNCTION_REPORT_BUNDLE_LIMIT_EXCEEDED")
    manifest_descriptor = _relative_descriptor(
        output, _atomic_write(output / REPORT_BUNDLE_MANIFEST_NAME, manifest_bytes)
    )
    archive = output / REPORT_BUNDLE_NAME
    with atomic_output_file(
        archive,
        max_bytes=MAX_REPORT_BUNDLE_BYTES,
        unsafe_error="FUNCTION_REPORT_OUTPUT_UNSAFE",
        limit_error="FUNCTION_REPORT_BUNDLE_LIMIT_EXCEEDED",
    ) as handle:
        with zipfile.ZipFile(handle, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
            for descriptor in [*manifest_files, manifest_descriptor]:
                relative = _safe_relative(descriptor["path"], "FUNCTION_REPORT_BUNDLE_PATH_INVALID")
                content = _stable_bytes(output / relative, "FUNCTION_REPORT_BUNDLE_SOURCE")
                if len(content) != descriptor["bytes"] or _digest(content) != descriptor["sha256"]:
                    raise RouteError("FUNCTION_REPORT_BUNDLE_SOURCE_DRIFT")
                info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                bundle.writestr(info, content)
    content = _stable_bytes(archive, "FUNCTION_REPORT_BUNDLE", max_bytes=MAX_REPORT_BUNDLE_BYTES)
    return {"path": REPORT_BUNDLE_NAME, "bytes": len(content), "sha256": _digest(content)}


def write_conversion_reports(report: dict[str, Any], output: Path) -> dict[str, Any]:
    """Persist a single report or an exact, content-addressed shard set."""
    validate_conversion_report(report)
    reset_conversion_report_outputs(output)
    count = len(report["functions"])
    if count <= MAX_OBLIGATIONS_PER_SHARD:
        markdown = render_conversion_markdown(report).encode("utf-8")
        if _digest(markdown) != report["markdown_sha256"]:
            raise RouteError("MARKDOWN_DIGEST_MISMATCH")
        json_descriptor = _relative_descriptor(output, _atomic_write(output / JSON_REPORT_NAME, _json_bytes(report)))
        markdown_descriptor = _relative_descriptor(output, _atomic_write(output / MARKDOWN_REPORT_NAME, markdown))
        return _summary(
            report,
            json_descriptor,
            markdown_descriptor,
            storage_mode="SINGLE",
            shard_count=0,
            total_shard_bytes=0,
        )

    shard_count = (count + MAX_OBLIGATIONS_PER_SHARD - 1) // MAX_OBLIGATIONS_PER_SHARD
    if shard_count > MAX_SHARDS:
        raise RouteError("FUNCTIONAL_OBLIGATION_LIMIT_EXCEEDED")
    shard_directory = output / REPORT_SHARD_DIRECTORY
    shard_directory.mkdir(parents=True)
    descriptors: list[dict[str, Any]] = []
    bundle_files: list[dict[str, Any]] = []
    observed_ids: list[str] = []
    total_shard_bytes = 0
    for sequence in range(1, shard_count + 1):
        start = (sequence - 1) * MAX_OBLIGATIONS_PER_SHARD
        rows = report["functions"][start : start + MAX_OBLIGATIONS_PER_SHARD]
        local_counts = dict(Counter(str(item["status"]) for item in rows))
        ids = [str(item["obligation_id"]) for item in rows]
        if set(ids) & set(observed_ids):
            raise RouteError("FUNCTION_REPORT_SHARD_DUPLICATE_OBLIGATION")
        observed_ids.extend(ids)
        shard = {
            key: copy.deepcopy(value)
            for key, value in report.items()
            if key not in {"functions", "blockers", "markdown_sha256", "kind"}
        }
        shard.update(
            {
                "kind": "elmos.project-language-conversion-report-shard",
                "functions": rows,
                "blockers": [item["failure"]["reason_code"] for item in rows if item["failure"]],
                "shard": {
                    "sequence": sequence,
                    "total": shard_count,
                    "function_count": len(rows),
                    "status_counts": local_counts,
                    "obligation_ids_sha256": _digest("\n".join(ids).encode("utf-8")),
                },
                "markdown_sha256": "0" * 64,
            }
        )
        heading = f"分片 {sequence}/{shard_count}；本分片 {len(rows)} 个功能；总指标来自全部分片"
        markdown = render_conversion_markdown(shard, shard_heading=heading).encode("utf-8")
        shard["markdown_sha256"] = _digest(markdown)
        json_path = shard_directory / f"report-{sequence:05d}.json"
        markdown_path = shard_directory / f"report-{sequence:05d}.md"
        json_descriptor = _relative_descriptor(output, _atomic_write(json_path, _json_bytes(shard)))
        markdown_descriptor = _relative_descriptor(output, _atomic_write(markdown_path, markdown))
        total_shard_bytes += int(json_descriptor["bytes"]) + int(markdown_descriptor["bytes"])
        descriptors.append(
            {
                "sequence": sequence,
                "function_count": len(rows),
                "status_counts": local_counts,
                "first_obligation_id": ids[0],
                "last_obligation_id": ids[-1],
                "obligation_ids_sha256": shard["shard"]["obligation_ids_sha256"],
                "json": json_descriptor,
                "markdown": markdown_descriptor,
            }
        )
        bundle_files.extend([json_descriptor, markdown_descriptor])
    all_ids = [str(item["obligation_id"]) for item in report["functions"]]
    if observed_ids != all_ids or sum(item["function_count"] for item in descriptors) != count:
        raise RouteError("FUNCTION_REPORT_SHARD_COVERAGE_INVALID")
    aggregate_counts: Counter[str] = Counter()
    for descriptor in descriptors:
        aggregate_counts.update(descriptor["status_counts"])
    if dict(aggregate_counts) != report["status_counts"]:
        raise RouteError("FUNCTION_REPORT_SHARD_METRIC_MISMATCH")
    index = {
        key: copy.deepcopy(value)
        for key, value in report.items()
        if key not in {"functions", "blockers", "markdown_sha256", "kind"}
    }
    index.update(
        {
            "kind": "elmos.project-language-conversion-report-index",
            "storage_mode": "SHARDED",
            "shard_count": shard_count,
            "total_shard_bytes": total_shard_bytes,
            "shards": descriptors,
            "blockers": report["blockers"],
            "markdown_sha256": "0" * 64,
        }
    )
    index_markdown = _render_index_markdown(index).encode("utf-8")
    index["markdown_sha256"] = _digest(index_markdown)
    root_json = _relative_descriptor(output, _atomic_write(output / JSON_REPORT_NAME, _json_bytes(index)))
    root_markdown = _relative_descriptor(output, _atomic_write(output / MARKDOWN_REPORT_NAME, index_markdown))
    bundle_files.extend([root_json, root_markdown])
    bundle = _write_bundle(output, bundle_files, report["report_id"])
    return _summary(
        report,
        root_json,
        root_markdown,
        storage_mode="SHARDED",
        shard_count=shard_count,
        total_shard_bytes=total_shard_bytes,
        report_bundle=bundle,
    )


def write_functional_conversion_reports(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Compatibility facade for callers that want build + write in one step."""
    output = kwargs.pop("output", None)
    if output is None and len(args) >= 5:
        *build_args, output = args
        report = build_conversion_report(*build_args, **kwargs)
    else:
        report = build_conversion_report(*args, **kwargs)
    if output is None:
        raise RouteError("FUNCTION_REPORT_OUTPUT_REQUIRED")
    return write_conversion_reports(report, Path(output))
