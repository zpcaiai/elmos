"""Is `CALL:user-function` really worth +18? Ask the analyzer, not the mirror.

The bundle search ranked cross-unit calls the single best lever at +18 net-new
READY. That number came from the hand-written mirror -- the same class of claim
as "11 functions are one annotation away", which turned out to be 5 when it was
actually verified. A lever worth building an inter-procedural purity proof for
deserves a verified number first.

Verification without an engine change, by INLINING:

    If a candidate's only obstacle is that it calls a user function, and that
    callee is itself a single `return <expr>`, then substituting the callee's
    body into the caller produces source the CURRENT analyzer can judge. If the
    inlined form comes back READY, the call was genuinely the only obstacle --
    proved by the real analyzer on real source, not projected by a mirror.

This also forces the question the +18 hides: **a call to a function that is
itself outside the subset does not become liftable by allowing calls.** The
inlined form answers that too -- it simply comes back with the callee's own
blocker.

Four outcomes, and only the first is a payoff:

    VERIFIED_BY_INLINE   the real analyzer returns READY after inlining
    BLOCKED_AFTER_INLINE the real analyzer still refuses -- the code says which
    CALLEE_NOT_INLINABLE the callee is not a single return-expression, or is
                         not in this module, or the call graph has a cycle
    UNRESOLVED_CALL      the call target is not a module-level user function
                         (builtin, method, import) -- outside this lever

Every rewrite that could change evaluation order or count is reported, never
silently counted. Inlining `f(g())` where the parameter appears twice evaluates
`g()` twice; inside this subset that is harmless, but "harmless" is a claim
about the subset, not about inlining, so it is recorded.

    python call_lever_verification.py --corpus-root ./corpus --output out.json
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engines/polyglot-route-engine/src"))

from elmos_polyglot_route.models import RouteError  # noqa: E402
from elmos_polyglot_route.project_graph import python_coverage_subjects  # noqa: E402
from elmos_polyglot_route.python_analyzer import analyze_python  # noqa: E402

SKIP_DIR_PARTS = {".git", ".tox", ".venv", "venv", "build", "dist", "__pycache__", "node_modules"}
MAX_INLINE_DEPTH = 3


# --------------------------------------------------------------- corpus ----

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


def strip_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        return body[1:]
    return body


# --------------------------------------------------------------- inline ----

class Substitute(ast.NodeTransformer):
    """Replace parameter names with argument expressions, counting each use.

    A NodeTransformer and not a string rewrite: `x` inside a string literal or
    an attribute name is not a parameter reference, and only the AST knows the
    difference.
    """

    def __init__(self, mapping: dict[str, ast.expr]) -> None:
        self.mapping = mapping
        self.uses: Counter[str] = Counter()

    def visit_Name(self, node: ast.Name) -> ast.AST:  # noqa: N802 - ast API
        if isinstance(node.ctx, ast.Load) and node.id in self.mapping:
            self.uses[node.id] += 1
            return ast.copy_location(
                ast.parse(ast.unparse(self.mapping[node.id]), mode="eval").body, node
            )
        return node


def return_expression_of(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.expr | None:
    """The single returned expression, or None if this is not that shape."""

    body = strip_docstring(fn.body)
    if len(body) != 1 or not isinstance(body[0], ast.Return) or body[0].value is None:
        return None
    return body[0].value


def plain_parameters(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str] | None:
    """Parameter names, or None when the signature is anything but positional.

    Defaults, `*args`, `**kwargs` and keyword-only parameters all change what a
    call site means, and getting that wrong would produce a rewrite that is not
    the program. Refused rather than approximated.
    """

    args = fn.args
    if args.vararg or args.kwarg or args.kwonlyargs or args.defaults or args.posonlyargs:
        return None
    return [a.arg for a in args.args]


def import_table(tree: ast.Module) -> dict[str, tuple[str, int, str]]:
    """`local name -> (module, relative-level, name IN that module)`.

    The third element is not decoration. `from .reexport import triple as
    triple_again` binds `triple_again` here and names `triple` there; looking
    the LOCAL name up in the target module finds nothing and silently reports
    the call unresolved. Caught by a negative control, not by reading the code.
    """

    table: dict[str, tuple[str, int, str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name != "*":
                    table[alias.asname or alias.name] = (node.module or "", node.level, alias.name)
    return table


def resolve_module(origin: Path, repository: Path, module: str, level: int) -> Path | None:
    """The file `from <module> import ...` names, if it is inside this repository.

    Absolute imports are only followed when they land inside the repository --
    a `from typing import cast` must stay unresolved, because a purity proof
    over the user's own units says nothing about the standard library.
    """

    parts = [p for p in module.split(".") if p]
    if level:
        base = origin.parent
        for _ in range(level - 1):
            base = base.parent
        candidates = [base.joinpath(*parts)]
    else:
        if not parts:
            return None
        # Absolute: try every directory on the way down from the repository root
        # that actually contains the first component as a package or module.
        candidates = []
        for anchor in {repository, *(p for p in origin.parents if repository in p.parents or p == repository)}:
            candidates.append(anchor.joinpath(*parts))
            if len(parts) > 1:
                candidates.append(anchor.joinpath(*parts[1:]))
    for candidate in candidates:
        for path in (candidate.with_suffix(".py"), candidate / "__init__.py"):
            try:
                resolved = path.resolve()
            except OSError:
                continue
            if path.is_file() and (repository == resolved or repository in resolved.parents):
                return path
    return None


def module_level_function(
    path: Path, name: str, repository: Path, depth: int = 0
) -> tuple[ast.FunctionDef | ast.AsyncFunctionDef, ast.Module] | None:
    """Find `name` in `path`, following ONE level of re-export."""

    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError, RecursionError):
        return None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name:
            return node, tree
    if depth >= 1:
        return None
    entry = import_table(tree).get(name)
    if entry is None:
        return None
    forwarded = resolve_module(path, repository, entry[0], entry[1])
    if forwarded is None or forwarded.resolve() == path.resolve():
        return None
    return module_level_function(forwarded, entry[2], repository, depth + 1)


class Inliner(ast.NodeTransformer):
    """Replace calls to same-module single-return functions with their bodies."""

    def __init__(
        self,
        index: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
        *,
        origin: Path | None = None,
        repository: Path | None = None,
        imports: dict[str, tuple[str, int, str]] | None = None,
    ) -> None:
        self.index = index
        self.origin = origin
        self.repository = repository
        self.imports = imports or {}
        self.cross_unit = 0
        self.notes: list[str] = []
        self.inlined = 0
        self.unresolved: list[str] = []
        self.not_inlinable: list[str] = []
        self.repeated_use_of_complex_argument: list[str] = []
        self._active: set[str] = set()
        self._depth = 0

    def visit_Call(self, node: ast.Call) -> ast.AST:
        node = self.generic_visit(node)  # type: ignore[assignment]
        if not isinstance(node.func, ast.Name):
            self.unresolved.append(ast.unparse(node.func)[:60])
            return node
        name = node.func.id
        callee = self.index.get(name)
        cross_unit = False
        if callee is None:
            callee = self._imported_callee(name)
            cross_unit = callee is not None
        if callee is None:
            self.unresolved.append(name)
            return node
        if name in self._active or self._depth >= MAX_INLINE_DEPTH:
            self.not_inlinable.append(f"{name}:recursive-or-too-deep")
            return node
        if node.keywords:
            self.not_inlinable.append(f"{name}:keyword-arguments")
            return node
        parameters = plain_parameters(callee)
        expression = return_expression_of(callee)
        if parameters is None or expression is None:
            self.not_inlinable.append(f"{name}:not-a-single-return-expression")
            return node
        if len(parameters) != len(node.args):
            self.not_inlinable.append(f"{name}:arity-mismatch")
            return node

        mapping = dict(zip(parameters, node.args, strict=True))
        substituted = Substitute(mapping)
        body = substituted.visit(ast.parse(ast.unparse(expression), mode="eval").body)
        for parameter, count in substituted.uses.items():
            argument = mapping[parameter]
            if count > 1 and not isinstance(argument, ast.Name | ast.Constant):
                # Inlining duplicated a non-trivial argument expression. Inside
                # this subset that cannot observe a difference, but that is a
                # claim about the subset -- so it is recorded, not assumed.
                self.repeated_use_of_complex_argument.append(
                    f"{name}:{parameter}x{count}:{ast.unparse(argument)[:40]}"
                )

        self._active.add(name)
        self._depth += 1
        try:
            body = self.visit(body)
        finally:
            self._depth -= 1
            self._active.discard(name)

        self.inlined += 1
        if cross_unit:
            self.cross_unit += 1
        return ast.copy_location(body, node)

    def _imported_callee(self, name: str):
        """The callee `name` refers to, when it lives in another unit of THIS repository."""

        if self.origin is None or self.repository is None:
            return None
        entry = self.imports.get(name)
        if entry is None:
            return None
        module = resolve_module(self.origin, self.repository, entry[0], entry[1])
        if module is None:
            return None
        found = module_level_function(module, entry[2], self.repository)
        return found[0] if found else None


# ------------------------------------------------------------------ run ----

def analyzer_verdict(path: Path, function: str) -> tuple[bool, str]:
    try:
        analyze_python(path, function)
    except RouteError as error:
        return False, str(error)
    except RecursionError:
        return False, "ANALYZER_RECURSION"
    return True, ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-root", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()

    corpus_root = arguments.corpus_root.resolve(strict=True)
    repositories = sorted(e.name for e in corpus_root.iterdir() if e.is_dir() and not e.is_symlink())

    records: list[dict] = []
    tally: Counter[str] = Counter()
    scratch = Path(tempfile.mkdtemp(prefix="elmos-call-lever-"))

    for repository in repositories:
        root = corpus_root / repository
        print(f"[call-lever] {repository}", file=sys.stderr, flush=True)
        for path in iter_python_files(root):
            relative = path.relative_to(root).as_posix()
            if is_test_file(relative):
                continue
            try:
                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=path.name)
            except (UnicodeDecodeError, OSError, SyntaxError, ValueError, RecursionError):
                continue

            index: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
            for node in tree.body:  # module level only -- a method is not callable by bare name
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    index.setdefault(node.name, node)

            for subject in python_coverage_subjects(tree, relative):
                if not subject.candidate or subject.blocking_reasons:
                    continue
                target = index.get(subject.name)
                if target is None:
                    continue

                already_ready, _ = analyzer_verdict(path, subject.name)
                if already_ready:
                    tally["ALREADY_READY"] += 1
                    continue
                if not any(isinstance(n, ast.Call) for n in ast.walk(target)):
                    tally["NO_CALLS_AT_ALL"] += 1
                    continue

                rewritten_tree = ast.parse(source, filename=path.name)
                rewritten_index = {
                    node.name: node
                    for node in rewritten_tree.body
                    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
                }
                subject_node = rewritten_index.get(subject.name)
                if subject_node is None:
                    continue
                inliner = Inliner(
                    rewritten_index,
                    origin=path,
                    repository=root,
                    imports=import_table(rewritten_tree),
                )
                try:
                    inliner.visit(subject_node)
                    ast.fix_missing_locations(rewritten_tree)
                    rewritten_source = ast.unparse(rewritten_tree)
                except (RecursionError, ValueError, AttributeError) as error:
                    tally["REWRITE_FAILED"] += 1
                    records.append({
                        "repository": repository, "path": relative, "function": subject.name,
                        "outcome": "REWRITE_FAILED", "detail": f"{type(error).__name__}: {error}",
                    })
                    continue

                if inliner.inlined == 0:
                    outcome = "UNRESOLVED_CALL" if inliner.unresolved else "CALLEE_NOT_INLINABLE"
                    tally[outcome] += 1
                    records.append({
                        "repository": repository, "path": relative, "function": subject.name,
                        "outcome": outcome,
                        "unresolved": sorted(set(inliner.unresolved))[:8],
                        "not_inlinable": sorted(set(inliner.not_inlinable))[:8],
                    })
                    continue

                scratch_file = scratch / f"{repository}_{relative.replace('/', '_')}"
                scratch_file.write_text(rewritten_source, encoding="utf-8")
                ready, code = analyzer_verdict(scratch_file, subject.name)
                outcome = "VERIFIED_BY_INLINE" if ready else "BLOCKED_AFTER_INLINE"
                tally[outcome] += 1
                records.append({
                    "repository": repository, "path": relative, "function": subject.name,
                    "outcome": outcome,
                    "inlined_calls": inliner.inlined,
                    "cross_unit_inlined": inliner.cross_unit,
                    "blocked_by": code,
                    "still_unresolved": sorted(set(inliner.unresolved))[:8],
                    "not_inlinable": sorted(set(inliner.not_inlinable))[:8],
                    "repeated_complex_arguments": inliner.repeated_use_of_complex_argument[:8],
                })

    report = {
        "instrument": "call_lever_verification.py",
        "method": "AST inline of same-module single-return callees, then the REAL "
                  "elmos_polyglot_route.python_analyzer.analyze_python decides",
        "tally": dict(sorted(tally.items())),
        "verified": sorted(
            (r["repository"], r["path"], r["function"], r.get("inlined_calls"))
            for r in records if r["outcome"] == "VERIFIED_BY_INLINE"
        ),
        "blocked_after_inline_codes": dict(Counter(
            r["blocked_by"].split(":")[0] for r in records
            if r["outcome"] == "BLOCKED_AFTER_INLINE" and r.get("blocked_by")
        ).most_common()),
        "records": records,
    }
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if arguments.output:
        arguments.output.write_text(text, encoding="utf-8")
    print(json.dumps({"tally": report["tally"],
                      "verified_count": len(report["verified"]),
                      "blocked_codes": report["blocked_after_inline_codes"]},
                     indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
