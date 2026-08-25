"""What would relaxing `PYTHON_UNANNOTATED_ASSIGNMENT` actually buy?

`ir_local_bindings` records a deliberate design decision -- "the type is
declared, not inferred" -- and the recommended way to revisit it: accept the
wider form in the Python frontend, run the evidence, and *measure how many real
functions enter the subset* before deciding whether the profile should move to
v2.

This script does the measuring WITHOUT changing the engine. It rewrites
`x = <expr>` to `x: T = <expr>` in a throwaway copy of each source, where T is
derived the way `types.infer` already derives it (the engine trusts that
inference today for its integer-division rule), and then re-runs the real
analyzer. Nothing in `elmos_polyglot_route` is modified.

Reported separately:
  ANNOTATABLE_FROM_LITERAL   `x = 1` -- the type comes from CPython's own
                             literal typing, not from a guess
  ANNOTATABLE_FROM_OPERANDS  `x = a * b` where every operand already has a
                             canonical type -- this is where the design
                             decision actually bites
"""

from __future__ import annotations

import ast
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.project_graph import python_coverage_subjects
from elmos_polyglot_route.python_analyzer import analyze_python

sys.path.insert(0, str(Path(__file__).parent))
from measure_admission import is_test_file, iter_python_files  # noqa: E402

CANON = {"int": "int", "float": "float", "bool": "bool", "str": "str"}
NUMERIC = {"int", "float"}


def literal_type(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return "bool"
        if isinstance(node.value, int):
            return "int"
        if isinstance(node.value, float):
            return "float"
        if isinstance(node.value, str):
            return "str"
    return None


def infer(node: ast.expr, environment: dict[str, str]) -> str | None:
    """Same promotion rule `types.infer` uses; None when it cannot decide."""

    direct = literal_type(node)
    if direct:
        return direct
    if isinstance(node, ast.Name):
        return environment.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(
        node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod)
    ):
        left = infer(node.left, environment)
        right = infer(node.right, environment)
        if left is None or right is None:
            return None
        if isinstance(node.op, ast.Add) and left == "str" and right == "str":
            return "str"
        if left not in NUMERIC or right not in NUMERIC:
            return None
        return "float" if "float" in (left, right) else "int"
    return None


def annotate(function: ast.FunctionDef) -> tuple[ast.FunctionDef, Counter[str]]:
    """Return a copy with unannotated assignments annotated where inferable."""

    origin: Counter[str] = Counter()
    environment: dict[str, str] = {}
    for argument in function.args.args:
        if argument.annotation is not None and isinstance(argument.annotation, ast.Name):
            if argument.annotation.id in CANON:
                environment[argument.arg] = argument.annotation.id

    def walk(body: list[ast.stmt]) -> list[ast.stmt]:
        out: list[ast.stmt] = []
        for statement in body:
            if (
                isinstance(statement, ast.Assign)
                and len(statement.targets) == 1
                and isinstance(statement.targets[0], ast.Name)
            ):
                inferred = infer(statement.value, environment)
                if inferred is not None:
                    origin["ANNOTATABLE_FROM_LITERAL" if literal_type(statement.value)
                           else "ANNOTATABLE_FROM_OPERANDS"] += 1
                    name = statement.targets[0].id
                    environment[name] = inferred
                    out.append(
                        ast.AnnAssign(
                            target=ast.Name(id=name, ctx=ast.Store()),
                            annotation=ast.Name(id=inferred, ctx=ast.Load()),
                            value=statement.value,
                            simple=1,
                        )
                    )
                    continue
                origin["NOT_INFERABLE"] += 1
            elif isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
                if isinstance(statement.annotation, ast.Name) and statement.annotation.id in CANON:
                    environment[statement.target.id] = statement.annotation.id
            if isinstance(statement, ast.If):
                statement = ast.If(
                    test=statement.test, body=walk(statement.body), orelse=walk(statement.orelse)
                )
            out.append(statement)
        return out

    rewritten = ast.FunctionDef(
        name=function.name,
        args=function.args,
        body=walk(list(function.body)),
        decorator_list=[],
        returns=function.returns,
        type_params=[],
    )
    return rewritten, origin


def main() -> int:
    corpus_root = Path(sys.argv[1]).resolve(strict=True)
    scratch = Path(tempfile.mkdtemp())

    before: Counter[str] = Counter()
    after: Counter[str] = Counter()
    origins: Counter[str] = Counter()
    newly_ready: list[dict[str, str]] = []
    examined = 0

    for repository in sorted(p for p in corpus_root.iterdir() if p.is_dir()):
        for path in iter_python_files(repository):
            relative = path.relative_to(repository).as_posix()
            if is_test_file(relative):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            index: dict[str, ast.FunctionDef] = {}
            for node in tree.body:
                if isinstance(node, ast.FunctionDef):
                    index.setdefault(node.name, node)
            for subject in python_coverage_subjects(tree, relative):
                if not subject.candidate or subject.blocking_reasons:
                    continue
                node = index.get(subject.name)
                if node is None:
                    continue
                try:
                    analyze_python(path, subject.name)
                    before["READY"] += 1
                    continue
                except RouteError as error:
                    code = str(error).split(":", 1)[0]
                    before[code] += 1
                except RecursionError:
                    before["RECURSION"] += 1
                    continue
                if code != "PYTHON_UNANNOTATED_ASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET":
                    continue
                examined += 1
                rewritten, origin = annotate(node)
                origins.update(origin)
                module = ast.Module(body=[rewritten], type_ignores=[])
                ast.fix_missing_locations(module)
                candidate = scratch / "candidate.py"
                try:
                    candidate.write_text(ast.unparse(module), encoding="utf-8")
                except Exception:
                    after["UNPARSEABLE_AFTER_REWRITE"] += 1
                    continue
                try:
                    analyze_python(candidate, node.name)
                    after["READY"] += 1
                    newly_ready.append({"repository": repository.name, "path": relative,
                                        "function": node.name})
                except RouteError as error:
                    after[str(error).split(":", 1)[0]] += 1
                except RecursionError:
                    after["RECURSION"] += 1

    report = {
        "kind": "elmos.python-unannotated-assignment-payoff",
        "schema_version": "1.0.0",
        "question": (
            "If the Python frontend inferred a local's type the way types.infer already "
            "does, how many real functions would enter typed-pure-function-v1?"
        ),
        "engine_modified": False,
        "candidates_rejected_on_unannotated_assignment": examined,
        "assignment_sites": dict(origins.most_common()),
        "outcome_after_rewriting_those_candidates": dict(after.most_common()),
        "newly_ready": newly_ready,
        "net_new_ready_units": after["READY"],
        "limitations": [
            "A simulation, not a behaviour change: it rewrites a throwaway copy of each "
            "function and re-runs the real analyzer.",
            "ir_local_bindings records that the type is declared rather than inferred, and "
            "that widening the frontend probably means typed-pure-function-v1 -> v2. This "
            "measures the payoff so that decision has a number attached; it does not take it.",
        ],
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
