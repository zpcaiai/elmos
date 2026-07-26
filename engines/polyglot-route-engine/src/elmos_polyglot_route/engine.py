from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .emitter import emit
from .models import SUPPORTED_LANGUAGES, Language, RouteError
from .native import analyze
from .validation import safe_output, validate


def _digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _load_cases(path: Path, parameter_count: int) -> list[dict[str, Any]]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, list) or not loaded:
        raise RouteError("BEHAVIOR_CASES_REQUIRED")
    result: list[dict[str, Any]] = []
    for item in loaded:
        if not isinstance(item, dict) or not isinstance(item.get("args"), list) or "expected" not in item:
            raise RouteError("INVALID_BEHAVIOR_CASE")
        if len(item["args"]) != parameter_count:
            raise RouteError("BEHAVIOR_ARGUMENT_COUNT_MISMATCH")
        result.append(item)
    return result


def migrate(
    source: Path,
    source_language: Language,
    target_language: Language,
    function_name: str,
    cases_path: Path,
    output: Path,
) -> dict[str, Any]:
    if source_language not in SUPPORTED_LANGUAGES or target_language not in SUPPORTED_LANGUAGES:
        raise RouteError("UNSUPPORTED_ROUTE_LANGUAGE")
    if source_language == target_language:
        raise RouteError("SOURCE_AND_TARGET_MUST_DIFFER")
    output = safe_output(output)
    ir = analyze(source, source_language, function_name)
    if len(ir.functions) != 1:
        raise RouteError("EXACTLY_ONE_FUNCTION_REQUIRED")
    function = ir.functions[0]
    cases = _load_cases(cases_path, len(function.parameters))
    emitted = emit(ir, target_language)
    evidence = validate(emitted, target_language, function, cases, output)
    ir_path = output / "semantic-ir.json"
    ir_path.write_text(
        json.dumps(ir.to_mapping(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    source_bytes = source.read_bytes()
    emitted_bytes = (output / emitted.relative_path).read_bytes()
    report = {
        "schema_version": "1.0.0",
        "status": "PASSED",
        "route": f"{source_language}-to-{target_language}",
        "scope": "typed-pure-function-v1",
        "source": {
            "path": source.name,
            "sha256": _digest(source_bytes),
            "language": source_language,
            "analyzer": ir.analyzer,
            "analyzer_version": ir.analyzer_version,
        },
        "target": {
            "path": emitted.relative_path,
            "sha256": _digest(emitted_bytes),
            "language": target_language,
        },
        "semantic_ir_sha256": _digest(ir_path.read_bytes()),
        "source_map_coverage": 1.0,
        "behavior_case_count": len(cases),
        "behavior_pass_rate": 1.0,
        "critical_unknown_semantics": 0,
        "limitations": [
            "Only typed, side-effect-free functions using return, if, literals, names, "
            "and supported binary operators are in scope.",
            "Object graphs, exceptions, async, reflection, I/O, framework, database, "
            "and concurrency semantics remain outside this route profile.",
        ],
        "validation": evidence,
        "certification_status": "EXPERIMENTAL",
        "external_certification_status": "NOT_RUN",
    }
    (output / "route-evidence.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report
