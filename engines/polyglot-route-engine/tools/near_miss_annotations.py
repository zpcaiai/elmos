"""Which functions are one annotation away from converting -- verified, not predicted.

`measure_admission_headroom.py` says 11 functions in the 20-project corpus fail
ONLY because a parameter or return type is missing. That is a statistic. This
turns it into a work list: which file, which line, which parameter, and which
canonical type actually makes the engine accept it.

THE CLAIM IS EXECUTED, NOT PREDICTED
------------------------------------
Inferring "this parameter is probably an int" and reporting it would be the
analyzer guessing a type -- the exact thing `ir_local_bindings` refuses to do,
and a guess that is wrong turns a work list into a wild goose chase. So instead:

  1. Ask the REAL analyzer why the function was refused.
  2. If the first refusal is a type-gate code, find the unannotated slots.
  3. Enumerate canonical type assignments for those slots, write each one out,
     and run the REAL analyzer again.
  4. Report only assignments that actually produced READY.

An assignment that reaches READY is a proof: the engine accepted it. Anything
else is reported as still-blocked, with the code that blocked it -- because
"first blocker was a type" does NOT mean the type was the only blocker.

WHAT THIS DELIBERATELY DOES NOT DO
----------------------------------
* It does not rank or choose among several working assignments. If both
  `(int, int)` and `(float, float)` are accepted, both are reported; picking
  is the author's call, and the two are not the same program.
* It does not touch a function whose annotations are PRESENT but outside the
  canonical four (`bytes`, `Path`, `str | None`, ...). Those are a type-surface
  decision, not a missing annotation, and are counted separately.
* It does not brute-force beyond `--max-slots` slots. Past that the
  combinatorics stop being evidence and start being noise; those functions are
  reported with their slot count and no assignment.
"""

from __future__ import annotations

import argparse
import ast
import itertools
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.project_graph import python_coverage_subjects
from elmos_polyglot_route.python_analyzer import analyze_python

CANONICAL_TYPES = ("int", "float", "bool", "str")

#: The two refusals that mean "the type gate stopped this one FIRST". They do
#: not mean the type gate was the only thing in the way.
_TYPE_GATE_CODES = ("PYTHON_PARAMETER_TYPE_REQUIRED", "PYTHON_RETURN_TYPE_REQUIRED")

SKIP_DIR_PARTS = {
    ".git", ".hg", "node_modules", "__pycache__", ".venv", "venv", ".tox",
    ".mypy_cache", ".pytest_cache", "build", "dist", "target", "vendor",
    ".idea", "site-packages", ".eggs",
}


def iter_python_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for path in sorted(root.rglob("*.py")):
        if not path.is_file() or path.is_symlink():
            continue
        if SKIP_DIR_PARTS & set(path.relative_to(root).parts[:-1]):
            continue
        out.append(path)
    return out


def is_test_file(relative: str) -> bool:
    parts = relative.split("/")
    name = parts[-1]
    return (
        name.startswith("test_") or name.endswith("_test.py")
        or "tests" in parts[:-1] or "test" in parts[:-1] or "testing" in parts[:-1]
    )


def refusal(path: Path, name: str) -> str | None:
    """The real analyzer's verdict. `None` means READY."""
    try:
        analyze_python(path, name)
    except RouteError as error:
        return str(error)
    except RecursionError:
        return "ANALYZER_RECURSION_LIMIT"
    return None


def slots(function: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[list[str], bool, list[str]]:
    """(unannotated parameter names, return is unannotated, non-canonical annotations)."""
    missing_parameters: list[str] = []
    non_canonical: list[str] = []
    arguments = function.args
    for argument in [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]:
        if argument.annotation is None:
            missing_parameters.append(argument.arg)
        elif not (
            isinstance(argument.annotation, ast.Name)
            and argument.annotation.id in CANONICAL_TYPES
        ):
            non_canonical.append(f"{argument.arg}: {ast.unparse(argument.annotation)}")
    missing_return = function.returns is None
    if function.returns is not None and not (
        isinstance(function.returns, ast.Name) and function.returns.id in CANONICAL_TYPES
    ):
        non_canonical.append(f"-> {ast.unparse(function.returns)}")
    return missing_parameters, missing_return, non_canonical


def annotated_source(
    source: str,
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    parameter_types: dict[str, str],
    return_type: str | None,
) -> str:
    """Rewrite ONE function's signature, leaving the rest of the file alone.

    Done on the AST and unparsed, so the result is what Python itself considers
    the same program with types added -- not a textual splice that might not
    even parse.
    """

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if node.name != function.name or node.lineno != function.lineno:
            continue
        arguments = node.args
        for argument in [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]:
            if argument.arg in parameter_types:
                argument.annotation = ast.Name(id=parameter_types[argument.arg], ctx=ast.Load())
        if return_type is not None:
            node.returns = ast.Name(id=return_type, ctx=ast.Load())
        break
    return ast.unparse(ast.fix_missing_locations(tree))


def accepted_assignments(
    source: str,
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    missing_parameters: list[str],
    missing_return: bool,
    scratch: Path,
    limit: int,
) -> tuple[list[dict[str, str]], str | None]:
    """Every canonical assignment the REAL analyzer accepts, and, when none is
    accepted, the code that blocked the last attempt."""

    accepted: list[dict[str, str]] = []
    last_block: str | None = None
    slot_count = len(missing_parameters) + (1 if missing_return else 0)
    if slot_count == 0 or slot_count > limit:
        return accepted, "SLOT_COUNT_OUT_OF_RANGE"

    parameter_space = itertools.product(CANONICAL_TYPES, repeat=len(missing_parameters))
    for parameter_choice in parameter_space:
        parameter_types = dict(zip(missing_parameters, parameter_choice, strict=True))
        for return_type in (CANONICAL_TYPES if missing_return else (None,)):
            candidate = scratch / "candidate.py"
            candidate.write_text(
                annotated_source(source, function, parameter_types, return_type),
                encoding="utf-8",
            )
            block = refusal(candidate, function.name)
            if block is None:
                assignment = dict(parameter_types)
                if return_type is not None:
                    assignment["->"] = return_type
                accepted.append(assignment)
            else:
                last_block = block
    return accepted, last_block


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path, action="append")
    parser.add_argument("--max-slots", type=int, default=3)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", type=Path)
    arguments = parser.parse_args()

    findings: list[dict] = []
    counters: Counter[str] = Counter()

    with tempfile.TemporaryDirectory(prefix="elmos-near-miss-") as directory:
        scratch = Path(directory)
        for repository in arguments.repository:
            root = repository.resolve(strict=True)
            print(f"[near-miss] {root.name}", file=sys.stderr, flush=True)
            for path in iter_python_files(root):
                relative = path.relative_to(root).as_posix()
                if is_test_file(relative):
                    continue
                try:
                    source = path.read_text(encoding="utf-8")
                    tree = ast.parse(source, filename=path.name)
                except (UnicodeDecodeError, OSError, SyntaxError, ValueError, RecursionError):
                    continue

                index: dict[str, ast.AST] = {}
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                        index.setdefault(node.name, node)

                for subject in python_coverage_subjects(tree, relative):
                    if not subject.candidate or subject.blocking_reasons:
                        continue
                    function = index.get(subject.name)
                    if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
                        continue
                    counters["candidates_examined"] += 1

                    verdict = refusal(path, subject.name)
                    if verdict is None:
                        counters["already_ready"] += 1
                        continue
                    if not verdict.startswith(_TYPE_GATE_CODES):
                        counters["blocked_before_the_type_gate"] += 1
                        continue

                    missing_parameters, missing_return, non_canonical = slots(function)
                    if not missing_parameters and not missing_return:
                        # Annotated, but outside the canonical four. A type
                        # surface decision, not a missing annotation.
                        counters["annotated_but_not_canonical"] += 1
                        continue
                    counters["type_gate_with_missing_annotations"] += 1

                    accepted, last_block = accepted_assignments(
                        source, function, missing_parameters, missing_return,
                        scratch, arguments.max_slots,
                    )
                    slot_count = len(missing_parameters) + (1 if missing_return else 0)
                    record = {
                        "repository": root.name,
                        "path": relative,
                        "line": function.lineno,
                        "function": subject.name,
                        "signature": ast.unparse(function).splitlines()[0].rstrip(":"),
                        "annotations_missing": slot_count,
                        "parameters_missing": missing_parameters,
                        "return_missing": missing_return,
                        "non_canonical_annotations": non_canonical,
                        "first_refusal": verdict,
                    }
                    if accepted:
                        record["status"] = "ONE_STEP_AWAY"
                        record["accepted_assignments"] = accepted
                        record["ambiguous"] = len(accepted) > 1
                        counters["one_step_away"] += 1
                        counters["one_step_away_ambiguous" if len(accepted) > 1
                                 else "one_step_away_single"] += 1
                    elif last_block == "SLOT_COUNT_OUT_OF_RANGE":
                        record["status"] = "NOT_SEARCHED"
                        record["reason"] = (
                            f"{slot_count} slots exceeds --max-slots={arguments.max_slots}"
                        )
                        counters["not_searched"] += 1
                    else:
                        record["status"] = "STILL_BLOCKED"
                        record["next_refusal"] = last_block
                        counters["still_blocked_after_annotating"] += 1
                    findings.append(record)

    report = {
        "kind": "elmos.python-near-miss-annotations",
        "schema_version": "1.0.0",
        "profile": "typed-pure-function-v1",
        "method": (
            "Every reported assignment was written out and re-analysed by "
            "elmos_polyglot_route.python_analyzer.analyze_python. ONE_STEP_AWAY "
            "means the engine returned READY for that exact signature -- it is a "
            "proof, not an inference."
        ),
        "max_slots": arguments.max_slots,
        "counts": dict(counters.most_common()),
        "findings": sorted(
            findings,
            key=lambda item: (item["status"] != "ONE_STEP_AWAY", item["annotations_missing"],
                              item["repository"], item["path"], item["line"]),
        ),
        "limitations": [
            "Only the canonical four types are tried. A function that needs "
            "`bytes` or a nullable type is reported STILL_BLOCKED, correctly.",
            "READY means the unit entered the subset. It does NOT mean its "
            "conversion was executed or certified.",
            "Two accepted assignments are two different programs. This tool "
            "reports both and picks neither.",
            "toolchain attestation NOT_RUN off Darwin/arm64 -- analyze_python is "
            "called directly, as in the other measurement scripts.",
        ],
    }

    text = json.dumps(report, indent=2)
    if arguments.output:
        arguments.output.write_text(text, encoding="utf-8")
        print(f"wrote {arguments.output}", file=sys.stderr)
    else:
        print(text)

    if arguments.markdown:
        lines = [
            "# 只差注解就能转的函数（逐条已验证）",
            "",
            "每一条的 `accepted` 都是**真的把补好注解的版本喂给分析器、它返回 READY**，",
            "不是推断。两个都被接受时两个都列出来——那是两个不同的程序，选哪个是作者的事。",
            "",
            f"- 检查的候选：{counters['candidates_examined']}",
            f"- **只差注解（已验证）：{counters['one_step_away']}**"
            f"（唯一解 {counters['one_step_away_single']}，多解 {counters['one_step_away_ambiguous']}）",
            f"- 补完注解仍被别的东西挡住：{counters['still_blocked_after_annotating']}",
            f"- 已标注但类型不在规范四类：{counters['annotated_but_not_canonical']}",
            f"- 槽位太多没搜（> {arguments.max_slots}）：{counters['not_searched']}",
            "",
            "## 待办",
            "",
        ]
        for item in report["findings"]:
            if item["status"] != "ONE_STEP_AWAY":
                continue
            lines.append(f"### `{item['repository']}/{item['path']}:{item['line']}` — `{item['function']}`")
            lines.append("")
            lines.append(f"```python\n{item['signature']}\n```")
            lines.append("")
            for assignment in item["accepted_assignments"]:
                rendered = ", ".join(
                    f"`-> {value}`" if key == "->" else f"`{key}: {value}`"
                    for key, value in assignment.items()
                )
                lines.append(f"- 加上 {rendered} → 引擎接受")
            if item["ambiguous"]:
                lines.append("- ⚠️ 多个赋值都被接受，它们**不是同一个程序**，需要作者判断")
            lines.append("")
        arguments.markdown.write_text("\n".join(lines), encoding="utf-8")
        print(f"wrote {arguments.markdown}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
