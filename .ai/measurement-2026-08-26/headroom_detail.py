"""Which functions, exactly, does each candidate feature buy? Names, not counts."""
from __future__ import annotations
import ast, json, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, "/root/eval")
import measure_admission_headroom as H
from elmos_polyglot_route.project_graph import python_coverage_subjects

root = Path("/root/eval/corpus")
records = []
for repo in sorted(e.name for e in root.iterdir() if e.is_dir()):
    base = root / repo
    for path in H.iter_python_files(base):
        rel = path.relative_to(base).as_posix()
        if H.is_test_file(rel):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
        except Exception:
            continue
        index = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                index.setdefault(node.name, node)
        for subject in python_coverage_subjects(tree, rel):
            if not subject.candidate or subject.blocking_reasons:
                continue
            fn = index.get(subject.name)
            if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            sig = H.signature_blockers(fn)
            body: Counter[str] = Counter()
            env = {a.arg: a.annotation.id
                   for a in [*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs]
                   if isinstance(a.annotation, ast.Name) and a.annotation.id in H.CANONICAL_TYPES}
            try:
                H.statement_blockers(H.strip_docstring(fn.body), body, env)
            except RecursionError:
                body["stmt:ANALYZER_RECURSION"] += 1
            records.append({"repo": repo, "path": rel, "fn": subject.name,
                            "sig": dict(sig), "body": dict(body), "node": fn})

def covered_by(rec, prefixes):
    codes = set(rec["sig"]) | set(rec["body"])
    if not codes:
        return False
    return all(any(c.startswith(p) for p in prefixes) for c in codes)

print("=" * 78)
print("A. The 27 functions whose ONLY blocker is a call")
print("=" * 78)
callees: Counter[str] = Counter()
hit = [r for r in records if covered_by(r, ("expr:Call",))]
for r in hit:
    for code in r["body"]:
        callees[code] += 1
    print(f"  {r['repo']}/{r['path']}::{r['fn']}  <- {', '.join(sorted(r['body']))}")
print(f"\n  callee frequency across those {len(hit)} functions:")
for k, v in callees.most_common():
    print(f"    {v:3d}  {k}")

print()
print("=" * 78)
print("B. The 13 functions whose ONLY blocker is a container-of-canonical type")
print("=" * 78)
for r in records:
    if covered_by(r, ("param:CONTAINER_OF_CANONICAL", "return:CONTAINER_OF_CANONICAL")):
        print(f"  {r['repo']}/{r['path']}::{r['fn']}  <- {', '.join(sorted(r['sig']))}")
        print(f"      {ast.unparse(r['node']).splitlines()[0][:100]}")

print()
print("=" * 78)
print("C. Would inferring a MISSING return type from a canonical body pay?")
print("=" * 78)
for label, prefixes in [
    ("return:MISSING alone", ("return:MISSING",)),
    ("return:MISSING + param:MISSING", ("return:MISSING", "param:MISSING")),
    ("calls + return:MISSING", ("expr:Call", "return:MISSING")),
    ("calls + containers", ("expr:Call", "param:CONTAINER_OF_CANONICAL", "return:CONTAINER_OF_CANONICAL")),
    ("calls + unannotated assign", ("expr:Call", "stmt:Assign:unannotated")),
    ("calls + assign + subscript + attribute", ("expr:Call", "stmt:Assign:unannotated", "expr:Subscript", "expr:Attribute")),
    ("string formatting (f-string) alone", ("expr:JoinedStr", "expr:FormattedValue")),
    ("None literal + is/is not", ("expr:Constant:NoneType", "expr:Compare:Is", "expr:Compare:IsNot")),
    ("unary not/neg alone", ("expr:UnaryOp",)),
]:
    n = sum(1 for r in records if covered_by(r, prefixes))
    print(f"  {n:4d}  net new READY  <-  {label}")

print()
print("=" * 78)
print("D. Bounded call whitelists -- what does each actually buy?")
print("=" * 78)

STR_METHODS = {"lower","upper","strip","lstrip","rstrip","replace","capitalize",
               "islower","isupper","startswith","endswith","title","casefold",
               "removeprefix","removesuffix","swapcase","zfill","count","find"}
PURE_BUILTINS = {"len","abs","min","max","round","str","int","float","bool","ord","chr"}

def call_class(code: str) -> str:
    if not code.startswith("expr:Call"):
        return "other"
    if code.startswith("expr:Call:free:"):
        name = code.split(":", 3)[3]
        return "builtin" if name in PURE_BUILTINS else "user-function"
    if code.startswith("expr:Call:attr:"):
        attr = code.rsplit(".", 1)[-1]
        return "str-method" if attr in STR_METHODS else "module-or-object-method"
    return "other"

buckets = Counter()
for r in records:
    for code in r["body"]:
        if code.startswith("expr:Call"):
            buckets[call_class(code)] += 1
print("  every call blocker in the whole candidate set, by class:")
for k, v in buckets.most_common():
    print(f"    {v:5d}  {k}")

def covered_by_pred(rec, pred):
    codes = set(rec["sig"]) | set(rec["body"])
    return bool(codes) and all(pred(c) for c in codes)

scenarios = {
    "str methods on a str value ONLY":
        lambda c: c.startswith("expr:Call") and call_class(c) == "str-method",
    "pure builtins ONLY (len/abs/min/max/...)":
        lambda c: c.startswith("expr:Call") and call_class(c) == "builtin",
    "str methods + pure builtins":
        lambda c: c.startswith("expr:Call") and call_class(c) in {"str-method", "builtin"},
    "str methods + builtins + user functions (needs purity proof)":
        lambda c: c.startswith("expr:Call") and call_class(c) in {"str-method", "builtin", "user-function"},
    "ALL calls incl. module/object methods (re, sys, struct, ...)":
        lambda c: c.startswith("expr:Call"),
}
print()
for label, pred in scenarios.items():
    n = sum(1 for r in records if covered_by_pred(r, pred))
    print(f"  {n:4d}  net new READY  <-  {label}")
