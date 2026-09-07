"""Would a METHOD profile buy anything? Lift methods to free functions and ask.

`typed-pure-function-v1` is a FREE-FUNCTION profile, and the headroom measurement
showed that is where the mass is: 4,128 of 16,046 subjects (25.7%) are class
methods, refused as `NESTED_SYMBOL` before any type or body rule is consulted.
That is the largest single block outside the profile, so "extend the profile to
methods" is the obvious next proposal.

It is also, so far, an unverified one -- and every unverified projection this
week has come back smaller than claimed, six times out of six. So: verify.

The verification is a LIFT. A method whose first parameter is `self`/`cls` and
which never references it is mechanically a free function; a `@staticmethod` is
one already. Move it to module level (keeping the rest of the module intact, so
its global references still resolve), and the CURRENT analyzer can judge it.
READY after lifting means the method profile would admit it; anything else is
the code the method profile would ALSO have to defeat.

Methods that do use `self` are reported, not lifted: `self` has an object type,
and the canonical types are `int/float/bool/str`. Admitting those is not a
profile widening, it is a different type system -- and saying so is the point.

    python method_profile_headroom.py --corpus-root ./corpus --output out.json
"""

from __future__ import annotations

import argparse
import ast
import copy
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engines/polyglot-route-engine/src"))

from elmos_polyglot_route.models import RouteError  # noqa: E402
from elmos_polyglot_route.python_analyzer import analyze_python  # noqa: E402

SKIP_DIR_PARTS = {".git", ".tox", ".venv", "venv", "build", "dist", "__pycache__", "node_modules"}
CANONICAL = {"int", "float", "bool", "str"}


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


def decorator_names(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    names: set[str] = set()
    for decorator in fn.decorator_list:
        node = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


def references(fn: ast.FunctionDef | ast.AsyncFunctionDef, name: str) -> bool:
    """Does the body mention `name` at all -- load, store, or attribute base?"""

    return any(
        isinstance(node, ast.Name) and node.id == name
        for statement in fn.body
        for node in ast.walk(statement)
    )


def classify(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, bool]:
    """(kind, liftable-to-a-free-function)."""

    decorators = decorator_names(fn)
    args = fn.args
    positional = [*args.posonlyargs, *args.args]
    if "staticmethod" in decorators:
        return "staticmethod", True
    if "property" in decorators or "setter" in decorators or "getter" in decorators:
        kind = "property"
    elif "classmethod" in decorators:
        kind = "classmethod"
    elif fn.name.startswith("__") and fn.name.endswith("__"):
        kind = "dunder"
    else:
        kind = "instance-method"
    if not positional:
        # No receiver parameter at all and no @staticmethod: calling it as a
        # method would fail. Treat as free-function-shaped anyway.
        return kind, True
    receiver = positional[0].arg
    if receiver not in {"self", "cls"}:
        return kind, False  # not a conventional receiver; refuse to guess
    return kind, not references(fn, receiver)


def lift(module: ast.Module, fn: ast.FunctionDef | ast.AsyncFunctionDef, new_name: str):
    """A module-level copy of `fn`, receiver dropped, decorators stripped."""

    lifted = copy.deepcopy(fn)
    lifted.name = new_name
    lifted.decorator_list = []
    positional = [*lifted.args.posonlyargs, *lifted.args.args]
    if positional and positional[0].arg in {"self", "cls"}:
        if lifted.args.posonlyargs:
            lifted.args.posonlyargs = lifted.args.posonlyargs[1:]
        else:
            lifted.args.args = lifted.args.args[1:]
    carrier = copy.deepcopy(module)
    carrier.body.append(lifted)
    ast.fix_missing_locations(carrier)
    return carrier


def verdict(path: Path, function: str) -> tuple[bool, str]:
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
    scratch = Path(tempfile.mkdtemp(prefix="elmos-method-profile-"))

    kinds: Counter[str] = Counter()
    liftable_kinds: Counter[str] = Counter()
    outcomes: Counter[str] = Counter()
    blockers: Counter[str] = Counter()
    ready: list[dict] = []
    records: list[dict] = []
    serial = 0

    for repository in repositories:
        root = corpus_root / repository
        print(f"[method-profile] {repository}", file=sys.stderr, flush=True)
        for path in iter_python_files(root):
            relative = path.relative_to(root).as_posix()
            if is_test_file(relative):
                continue
            try:
                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=path.name)
            except (UnicodeDecodeError, OSError, SyntaxError, ValueError, RecursionError):
                continue

            methods: list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    for child in node.body:
                        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                            methods.append((node.name, child))

            for class_name, method in methods:
                kind, liftable = classify(method)
                kinds[kind] += 1
                if not liftable:
                    outcomes["USES_RECEIVER_OR_UNCONVENTIONAL"] += 1
                    continue
                liftable_kinds[kind] += 1

                serial += 1
                new_name = f"elmos_lifted_{serial}"
                try:
                    carrier = lift(tree, method, new_name)
                    text = ast.unparse(carrier)
                except (RecursionError, ValueError, AttributeError) as error:
                    outcomes["LIFT_FAILED"] += 1
                    records.append({"repository": repository, "path": relative,
                                    "class": class_name, "method": method.name,
                                    "outcome": "LIFT_FAILED",
                                    "detail": f"{type(error).__name__}: {error}"})
                    continue

                scratch_file = scratch / f"{serial}_{relative.replace('/', '_')}"
                scratch_file.write_text(text, encoding="utf-8")
                ok, code = verdict(scratch_file, new_name)
                outcome = "READY_AFTER_LIFT" if ok else "BLOCKED_AFTER_LIFT"
                outcomes[outcome] += 1
                if ok:
                    ready.append({"repository": repository, "path": relative,
                                  "class": class_name, "method": method.name, "kind": kind})
                else:
                    blockers[code.split(":")[0]] += 1
                records.append({"repository": repository, "path": relative,
                                "class": class_name, "method": method.name,
                                "kind": kind, "outcome": outcome, "blocked_by": code})

    report = {
        "instrument": "method_profile_headroom.py",
        "method": "lift a receiver-free method to module level inside its own module, "
                  "then the REAL analyze_python decides",
        "methods_by_kind": dict(kinds.most_common()),
        "liftable_by_kind": dict(liftable_kinds.most_common()),
        "outcomes": dict(outcomes.most_common()),
        "blockers_after_lift": dict(blockers.most_common(20)),
        #: Split by kind on purpose. A `@property` is READ as an attribute, not
        #: called, so "the analyzer accepts its body" is NOT the same claim as
        #: "the method profile would admit it as a callable unit". Reported
        #: separately rather than folded into a flattering headline.
        "ready_by_kind": dict(Counter(r["kind"] for r in ready).most_common()),
        "ready_after_lift": ready,
        "records": records,
    }
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if arguments.output:
        arguments.output.write_text(text, encoding="utf-8")
    print(json.dumps({k: report[k] for k in
                      ("methods_by_kind", "liftable_by_kind", "outcomes",
                       "blockers_after_lift", "ready_by_kind")},
                     indent=2, ensure_ascii=False))
    print(f"READY_AFTER_LIFT = {len(ready)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
