"""What would actually raise the admission rate? A joint measurement of both walls.

`measure_admission.py` reports where each candidate dies. That is not enough to
choose what to build, for two reasons:

1. **Only the first blocker is reported.** Remove one wall and the next one
   appears; the count that looked like a payoff was a queue.
2. **There are two independent gates**, and a function must clear BOTH:

       Wall A  the signature type gate -- every parameter and the return
               annotated with one of `int/float/bool/str`.
       Wall B  the body gate -- every statement and expression inside the
               IR's whitelist (Return / If / annotated-let; name, literal,
               + - * / %, six comparisons, two-operand and/or).

   Widening one wall alone moves functions from dying at A to dying at B.
   Net admission gain is zero. This is exactly what the
   UNANNOTATED_ASSIGNMENT payoff measurement already demonstrated once.

So this script classifies every clean candidate on BOTH axes independently and
enumerates **every** blocker in the body rather than stopping at the first.
That makes the decisive number computable:

    body_clean_but_signature_blocked
        -- the upper bound on what any type-surface widening can ever buy.

    signature_clean_but_body_blocked
        -- the upper bound on what any IR widening can ever buy.

    both_clean
        -- today's READY set.

and, per feature, the **net new READY** if that feature (or bundle) shipped:
functions whose entire remaining blocker set is covered by the bundle.

Nothing here changes the engine. The subset surface below is READ from
`python_analyzer` semantics and mirrored; the mirror is checked against the
real analyzer at the end -- if the mirror and the analyzer disagree about
which functions are READY, the run aborts rather than reporting a number.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.project_graph import python_coverage_subjects
from elmos_polyglot_route.python_analyzer import analyze_python

CANONICAL_TYPES = {"int", "float", "bool", "str"}

SKIP_DIR_PARTS = {
    ".git", ".hg", "node_modules", "__pycache__", ".venv", "venv",
    ".tox", ".mypy_cache", ".pytest_cache", "build", "dist", "target",
    "vendor", ".idea", "site-packages", ".eggs",
}

BIN_OPS = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.Mod: "%"}
CMP_OPS = {ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq}
ORDERING_OPS = {ast.Lt, ast.LtE, ast.Gt, ast.GtE}

# ---------------------------------------------------------------- Wall A ----

def classify_annotation(node: ast.expr | None) -> tuple[str, str]:
    """(bucket, rendered) -- bucket is what a widening would have to cover."""
    if node is None:
        return "MISSING", ""
    text = ast.unparse(node)
    if isinstance(node, ast.Name) and node.id in CANONICAL_TYPES:
        return "CANONICAL", text
    if isinstance(node, ast.Constant) and node.value is None:
        return "NONE_RETURN", text
    if isinstance(node, ast.Name) and node.id == "bytes":
        return "BYTES", text
    # `T | None` / `Optional[T]`
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        parts = [ast.unparse(node.left), ast.unparse(node.right)]
        if "None" in parts:
            inner = [p for p in parts if p != "None"]
            return ("OPTIONAL_CANONICAL" if inner and inner[0] in CANONICAL_TYPES
                    else "OPTIONAL_OTHER"), text
    if isinstance(node, ast.Subscript):
        base = ast.unparse(node.value)
        if base in {"Optional", "t.Optional", "typing.Optional"}:
            inner = ast.unparse(node.slice)
            return ("OPTIONAL_CANONICAL" if inner in CANONICAL_TYPES
                    else "OPTIONAL_OTHER"), text
        if base in {"list", "List", "t.List", "typing.List",
                    "Sequence", "Iterable", "Iterator", "tuple", "Tuple",
                    "set", "Set", "frozenset", "dict", "Dict", "Mapping"}:
            inner = ast.unparse(node.slice)
            return ("CONTAINER_OF_CANONICAL" if inner in CANONICAL_TYPES
                    else "CONTAINER_OTHER"), text
        return "OTHER", text
    if isinstance(node, ast.Name) and node.id in {"Any", "object"}:
        return "ANY", text
    if text in {"t.Any", "typing.Any"}:
        return "ANY", text
    return "OTHER", text


def signature_blockers(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> Counter[str]:
    """Every reason the signature fails Wall A -- not just the first."""
    found: Counter[str] = Counter()
    args = fn.args
    for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs]:
        bucket, _ = classify_annotation(arg.annotation)
        if bucket != "CANONICAL":
            found[f"param:{bucket}"] += 1
    if args.vararg is not None:
        found["param:VARARG"] += 1
    if args.kwarg is not None:
        found["param:KWARG"] += 1
    bucket, _ = classify_annotation(fn.returns)
    if bucket != "CANONICAL":
        found[f"return:{bucket}"] += 1
    return found

# ---------------------------------------------------------------- Wall B ----

def _infer(node: ast.expr, env: dict[str, str]) -> str:
    """A deliberately small mirror of `types.infer`, only enough to decide
    whether a `/` has two integer operands. Fails to "" (unknown) rather than
    guessing -- and the mirror-vs-analyzer assertion at the end is what proves
    it is enough."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return "bool"
        if isinstance(node.value, int):
            return "int"
        if isinstance(node.value, float):
            return "float"
        if isinstance(node.value, str):
            return "str"
        return ""
    if isinstance(node, ast.Name):
        return env.get(node.id, "")
    if isinstance(node, ast.Compare) or isinstance(node, ast.BoolOp):
        return "bool"
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return "bool"
    if isinstance(node, ast.BinOp) and type(node.op) in BIN_OPS:
        left, right = _infer(node.left, env), _infer(node.right, env)
        if isinstance(node.op, ast.Div):
            return "float"
        if left == right:
            return left
        if {left, right} == {"int", "float"}:
            return "float"
        return ""
    return ""


def expression_blockers(
    node: ast.expr, out: Counter[str], env: dict[str, str], bound: set[str] | None = None
) -> None:
    if isinstance(node, ast.Name):
        # A name that is neither a parameter nor a `let` is a FREE VARIABLE --
        # a module-level global. `types.infer` refuses it as `UNDECLARED_NAME`,
        # and the mirror used to accept it silently, which is how it reported
        # 11 functions as "one annotation away" when the analyzer accepts 5.
        if bound is not None and node.id not in bound:
            out[f"expr:Name:free-variable:{node.id}"] += 1
        return
    if isinstance(node, ast.Constant):
        if isinstance(node.value, str | int | float | bool):
            return
        out[f"expr:Constant:{type(node.value).__name__}"] += 1
        return
    if isinstance(node, ast.BinOp):
        if type(node.op) in BIN_OPS:
            # `_reject_python_only_arithmetic`: `%` never survives lifting
            # (Python follows the sign of the divisor, the C family truncates),
            # and `/` on two integers is true division in Python only.
            left_type, right_type = _infer(node.left, env), _infer(node.right, env)
            if "str" in (left_type, right_type) and not (
                isinstance(node.op, ast.Add) and left_type == right_type == "str"
            ):
                # `types.infer`: only `+` on two strings is defined. `"-" * n`
                # is `OPERAND_TYPE_MISMATCH:*:string:...`, not a supported
                # operator. The mirror used to wave every arithmetic operator
                # through without looking at the operand types.
                out[f"expr:BinOp:{type(node.op).__name__}:non-numeric-operand"] += 1
            if isinstance(node.op, ast.Mod):
                out["expr:BinOp:Mod:python-floored"] += 1
            elif isinstance(node.op, ast.Div) and left_type == right_type == "int":
                out["expr:BinOp:Div:python-true-division"] += 1
            expression_blockers(node.left, out, env, bound)
            expression_blockers(node.right, out, env, bound)
            return
        out[f"expr:BinOp:{type(node.op).__name__}"] += 1
        expression_blockers(node.left, out, env, bound)
        expression_blockers(node.right, out, env, bound)
        return
    if isinstance(node, ast.Compare):
        if len(node.ops) == 1 and len(node.comparators) == 1 and type(node.ops[0]) in CMP_OPS:
            if type(node.ops[0]) in ORDERING_OPS and "str" in (
                _infer(node.left, env), _infer(node.comparators[0], env)
            ):
                # Java orders strings by UTF-16 code unit, Python by code point.
                out["expr:Compare:string-ordering"] += 1
            expression_blockers(node.left, out, env, bound)
            expression_blockers(node.comparators[0], out, env, bound)
            return
        if len(node.ops) != 1:
            out["expr:Compare:chained"] += 1
        else:
            out[f"expr:Compare:{type(node.ops[0]).__name__}"] += 1
        expression_blockers(node.left, out, env, bound)
        for comparator in node.comparators:
            expression_blockers(comparator, out, env, bound)
        return
    if isinstance(node, ast.BoolOp):
        # 2026-08-26: any arity is lifted by a left fold.
        for value in node.values:
            expression_blockers(value, out, env, bound)
        return
    if isinstance(node, ast.UnaryOp):
        # 2026-08-26: a signed numeric literal folds into the literal, and
        # `not` on a canonical boolean becomes `== False`. Everything else
        # under UnaryOp is still refused.
        operand = node.operand
        if isinstance(node.op, ast.USub | ast.UAdd):
            if (isinstance(operand, ast.Constant)
                    and not isinstance(operand.value, bool)
                    and isinstance(operand.value, int | float)):
                return
            out["expr:UnaryOp:sign-on-expression"] += 1
            expression_blockers(operand, out, env, bound)
            return
        if isinstance(node.op, ast.Not):
            if _infer(operand, env) != "bool":
                # Python truthiness -- fails in the type checker as
                # OPERAND_TYPE_MISMATCH:==
                out["expr:UnaryOp:Not:non-boolean-operand"] += 1
            expression_blockers(operand, out, env, bound)
            return
        out[f"expr:UnaryOp:{type(node.op).__name__}"] += 1
        expression_blockers(operand, out, env, bound)
        return
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name):
            out[f"expr:Call:free:{func.id}"] += 1
        elif isinstance(func, ast.Attribute):
            base = ast.unparse(func.value)
            out[f"expr:Call:attr:{base}.{func.attr}" if base.isidentifier()
                else f"expr:Call:attr:<expr>.{func.attr}"] += 1
            # The RECEIVER is an expression too, and it can hold further
            # blockers: `_PATTERN.sub(x).lower()` is a `.sub` inside a
            # `.lower`. Skipping it under-reports the blocker set, which
            # silently OVERSTATES every net-new-READY number computed from it.
            # (The mirror-vs-analyzer assertion does not catch this: it only
            # validates functions with ZERO blockers, and a function with a
            # missed blocker still has the others.)
            expression_blockers(func.value, out, env, bound)
        else:
            out["expr:Call:other"] += 1
            expression_blockers(func, out, env, bound)
        for arg in node.args:
            expression_blockers(arg, out, env, bound)
        for keyword in node.keywords:
            expression_blockers(keyword.value, out, env, bound)
        return
    out[f"expr:{type(node).__name__}"] += 1
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.expr):
            expression_blockers(child, out, env, bound)


def statement_blockers(
    nodes: list[ast.stmt], out: Counter[str], env: dict[str, str], bound: set[str]
) -> None:
    for node in nodes:
        if isinstance(node, ast.Return):
            if node.value is None:
                out["stmt:Return:bare"] += 1
            else:
                expression_blockers(node.value, out, env, bound)
        elif isinstance(node, ast.If):
            expression_blockers(node.test, out, env, bound)
            # branches get a copy, matching `_check_statements`'s scope rule
            statement_blockers(node.body, out, dict(env), set(bound))
            statement_blockers(node.orelse, out, dict(env), set(bound))
        elif isinstance(node, ast.AnnAssign):
            if node.value is None:
                out["stmt:AnnAssign:no-value"] += 1
                continue
            if node.simple != 1 or not isinstance(node.target, ast.Name):
                out["stmt:AnnAssign:target"] += 1
            bucket, rendered = classify_annotation(node.annotation)
            if bucket != "CANONICAL":
                out[f"stmt:AnnAssign:type:{bucket}"] += 1
            expression_blockers(node.value, out, env, bound)
            # bind AFTER the initializer, never before -- same as the analyzer
            if isinstance(node.target, ast.Name):
                bound.add(node.target.id)
                if bucket == "CANONICAL":
                    env[node.target.id] = rendered
        elif isinstance(node, ast.Assign):
            out["stmt:Assign:unannotated"] += 1
            expression_blockers(node.value, out, env, bound)
            for target in node.targets:
                if isinstance(target, ast.Name):
                    bound.add(target.id)
        elif isinstance(node, ast.Expr):
            out["stmt:Expr"] += 1
            expression_blockers(node.value, out, env, bound)
        else:
            out[f"stmt:{type(node).__name__}"] += 1
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.expr):
                    expression_blockers(child, out, env, bound)
                elif isinstance(child, ast.stmt):
                    statement_blockers([child], out, env, bound)


def strip_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    """The engine now lifts a leading docstring out of the body (2026-08-25)."""
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        return body[1:]
    return body

# ------------------------------------------------------------------ run ----

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
    return (name.startswith("test_") or name.endswith("_test.py")
            or "tests" in parts[:-1] or "test" in parts[:-1] or "testing" in parts[:-1])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-root", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()

    corpus_root = arguments.corpus_root.resolve(strict=True)
    repositories = sorted(e.name for e in corpus_root.iterdir() if e.is_dir() and not e.is_symlink())

    records: list[dict] = []
    mirror_ready: set[tuple[str, str]] = set()
    analyzer_ready: set[tuple[str, str]] = set()

    for name in repositories:
        root = corpus_root / name
        print(f"[headroom] {name}", file=sys.stderr, flush=True)
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
                fn = index.get(subject.name)
                if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue

                sig = signature_blockers(fn)
                body: Counter[str] = Counter()
                env = {
                    arg.arg: arg.annotation.id
                    for arg in [*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs]
                    if isinstance(arg.annotation, ast.Name)
                    and arg.annotation.id in CANONICAL_TYPES
                }
                bound = {
                    arg.arg
                    for arg in [*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs]
                }
                try:
                    statement_blockers(strip_docstring(fn.body), body, env, bound)
                except RecursionError:
                    body["stmt:ANALYZER_RECURSION"] += 1

                key = (f"{name}/{relative}", subject.name)
                if not sig and not body:
                    mirror_ready.add(key)
                try:
                    analyze_python(path, subject.name)
                except (RouteError, RecursionError):
                    pass
                else:
                    analyzer_ready.add(key)

                records.append({
                    "repository": name,
                    "path": relative,
                    "function": subject.name,
                    "signature_blockers": dict(sig),
                    "body_blockers": dict(body),
                })

    # ---- the mirror must agree with the real analyzer, or the run is void ----
    if mirror_ready != analyzer_ready:
        print("ABORT: mirror disagrees with analyzer", file=sys.stderr)
        print(f"  mirror-only:   {sorted(mirror_ready - analyzer_ready)[:10]}", file=sys.stderr)
        print(f"  analyzer-only: {sorted(analyzer_ready - mirror_ready)[:10]}", file=sys.stderr)
        return 2

    total = len(records)
    sig_clean = [r for r in records if not r["signature_blockers"]]
    body_clean = [r for r in records if not r["body_blockers"]]
    both = [r for r in records if not r["signature_blockers"] and not r["body_blockers"]]

    sig_reasons: Counter[str] = Counter()
    body_reasons: Counter[str] = Counter()
    body_reasons_distinct_fns: Counter[str] = Counter()
    for record in records:
        sig_reasons.update(record["signature_blockers"])
        body_reasons.update(record["body_blockers"])
        for code in record["body_blockers"]:
            body_reasons_distinct_fns[code] += 1

    # Among the functions that already clear Wall A, what is left?
    remaining_after_wall_a: Counter[str] = Counter()
    for record in sig_clean:
        for code in record["body_blockers"]:
            remaining_after_wall_a[code] += 1

    # Among the functions that already clear Wall B, what is left?
    remaining_after_wall_b: Counter[str] = Counter()
    for record in body_clean:
        for code in record["signature_blockers"]:
            remaining_after_wall_b[code] += 1

    def net_new_ready(feature_prefixes: tuple[str, ...]) -> int:
        """Functions that become READY if EVERY listed feature ships -- i.e.
        whose entire remaining blocker set is covered. Not an occurrence count."""
        gained = 0
        for record in records:
            if not record["signature_blockers"] and not record["body_blockers"]:
                continue  # already ready
            codes = set(record["signature_blockers"]) | set(record["body_blockers"])
            if all(any(code.startswith(p) for p in feature_prefixes) for code in codes):
                gained += 1
        return gained

    bundles = {
        "bytes_only": ("param:BYTES", "return:BYTES"),
        "optional_canonical_only": ("param:OPTIONAL_CANONICAL", "return:OPTIONAL_CANONICAL"),
        "none_return_only": ("return:NONE_RETURN",),
        "container_of_canonical_only": ("param:CONTAINER_OF_CANONICAL", "return:CONTAINER_OF_CANONICAL"),
        "whole_type_surface_widening": (
            "param:BYTES", "return:BYTES",
            "param:OPTIONAL_CANONICAL", "return:OPTIONAL_CANONICAL",
            "param:OPTIONAL_OTHER", "return:OPTIONAL_OTHER",
            "param:CONTAINER_OF_CANONICAL", "return:CONTAINER_OF_CANONICAL",
            "param:CONTAINER_OTHER", "return:CONTAINER_OTHER",
            "param:ANY", "return:ANY", "return:NONE_RETURN",
            "param:OTHER", "return:OTHER", "param:MISSING", "return:MISSING",
        ),
        "unannotated_assignment_only": ("stmt:Assign:unannotated",),
        "unary_ops_only": ("expr:UnaryOp",),
        "python_only_arithmetic_only": ("expr:BinOp:Mod:python-floored", "expr:BinOp:Div:python-true-division"),
        "calls_only": ("expr:Call",),
        "whole_body_widening": ("stmt:", "expr:"),
        "everything": ("param:", "return:", "stmt:", "expr:"),
    }

    report = {
        "kind": "elmos.admission-headroom-measurement",
        "schema_version": "1.0.0",
        "profile": "typed-pure-function-v1",
        "instruments": {
            "coverage_inventory": "elmos_polyglot_route.project_graph.python_coverage_subjects",
            "semantic_subset_check": "elmos_polyglot_route.python_analyzer.analyze_python",
            "mirror_agreement": "VERIFIED -- mirror READY set == analyzer READY set",
        },
        "corpus": {"repositories": len(repositories), "names": repositories},
        "candidates_examined": total,
        "walls": {
            "signature_clean (clears Wall A)": len(sig_clean),
            "body_clean (clears Wall B)": len(body_clean),
            "both_clean (READY today)": len(both),
        },
        "headroom": {
            "max_gain_from_any_type_surface_widening": len(body_clean) - len(both),
            "max_gain_from_any_ir_widening": len(sig_clean) - len(both),
            "note": (
                "Each is an UPPER BOUND: it counts functions already clear on the "
                "other wall. A widening that does not clear a function's ENTIRE "
                "remaining blocker set buys nothing."
            ),
        },
        "net_new_ready_by_bundle": {k: net_new_ready(v) for k, v in bundles.items()},
        "signature_blocker_occurrences": dict(sig_reasons.most_common(30)),
        "body_blocker_occurrences": dict(body_reasons.most_common(40)),
        "body_blocker_distinct_functions": dict(body_reasons_distinct_fns.most_common(40)),
        "remaining_blockers_for_functions_that_clear_wall_a": dict(
            remaining_after_wall_a.most_common(40)
        ),
        "remaining_blockers_for_functions_that_clear_wall_b": dict(
            remaining_after_wall_b.most_common(40)
        ),
        "ready_units": sorted(f"{r['repository']}/{r['path']}::{r['function']}" for r in both),
        "limitations": [
            "Blocker enumeration is exhaustive per function, unlike the analyzer's "
            "first-blocker rejection code. Occurrence counts here are therefore NOT "
            "comparable to measure_admission.py's semantic_rejections.",
            "net_new_ready counts FUNCTIONS THAT BECOME READY, not occurrences removed.",
            "A call is counted as one blocker regardless of whether the callee is pure. "
            "Supporting calls needs a purity proof for the callee; this number is an "
            "upper bound on that feature's payoff, not an estimate of its cost.",
            "toolchain attestation NOT_RUN -- analyze_python called directly, as in "
            "measure_admission.py.",
        ],
    }

    text = json.dumps(report, indent=2)
    if arguments.output:
        arguments.output.write_text(text, encoding="utf-8")
        print(f"wrote {arguments.output}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
