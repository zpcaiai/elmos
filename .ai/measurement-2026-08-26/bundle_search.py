"""Which SMALL set of features unlocks the most? Exhaustive over bundles of 1-4.

Single-feature payoffs are almost all zero, because a function must have its
ENTIRE blocker set covered. The interesting question is therefore combinatorial:
what is the cheapest *combination* that clears whole functions?

Features are normalized blocker families (e.g. all `expr:Call:attr:*` collapse
to one `CALL:str-method` / `CALL:object-method` family), so the search is over
things you could actually decide to build, not over individual call sites.
"""
from __future__ import annotations
import ast, itertools, json, sys
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0, "/root/eval")
import measure_admission_headroom as H
from elmos_polyglot_route.project_graph import python_coverage_subjects

STR_METHODS = {"lower","upper","strip","lstrip","rstrip","replace","capitalize",
               "islower","isupper","startswith","endswith","title","casefold",
               "removeprefix","removesuffix","swapcase","zfill","count","find","split","join"}
PURE_BUILTINS = {"len","abs","min","max","round","str","int","float","bool","ord","chr"}

def family(code: str) -> str:
    """Collapse a raw blocker into a buildable feature."""
    if code.startswith("expr:Call:free:"):
        name = code.split(":", 3)[3]
        return "CALL:pure-builtin" if name in PURE_BUILTINS else "CALL:user-function"
    if code.startswith("expr:Call:attr:"):
        attr = code.rsplit(".", 1)[-1]
        return "CALL:str-method" if attr in STR_METHODS else "CALL:object-or-module-method"
    if code.startswith("expr:Call"):
        return "CALL:other"
    if code.startswith("expr:UnaryOp"):
        return "EXPR:unary-op"
    if code.startswith("expr:BinOp:"):
        return "EXPR:other-binary-operator"
    if code.startswith("expr:Compare:"):
        return "EXPR:other-comparison(in/is/chained)"
    if code.startswith("expr:BoolOp"):
        return "EXPR:n-ary-boolean"
    if code.startswith("expr:Constant:NoneType"):
        return "EXPR:none-literal"
    if code.startswith("expr:JoinedStr") or code.startswith("expr:FormattedValue"):
        return "EXPR:f-string"
    if code.startswith("expr:"):
        return "EXPR:" + code.split(":", 1)[1].split(":", 1)[0]
    if code.startswith("stmt:AnnAssign:type"):
        return "STMT:let-of-non-canonical-type"
    if code.startswith("stmt:"):
        return "STMT:" + code.split(":", 1)[1].split(":", 1)[0]
    if code.startswith("param:") or code.startswith("return:"):
        side, bucket = code.split(":", 1)
        return f"TYPE:{bucket}"
    return code

root = Path("/root/eval/corpus")
needs: list[frozenset[str]] = []
ready_now = 0
for repo in sorted(e.name for e in root.iterdir() if e.is_dir()):
    base = root / repo
    for path in H.iter_python_files(base):
        rel = path.relative_to(base).as_posix()
        if H.is_test_file(rel):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        idx = {}
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef):
                idx.setdefault(n.name, n)
        for s in python_coverage_subjects(tree, rel):
            if not s.candidate or s.blocking_reasons:
                continue
            fn = idx.get(s.name)
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
            codes = frozenset(family(c) for c in (set(sig) | set(body)))
            if not codes:
                ready_now += 1
            else:
                needs.append(codes)

print(f"candidates: {len(needs) + ready_now}   READY today: {ready_now}")
vocabulary = sorted({f for s in needs for f in s})
print(f"feature families: {len(vocabulary)}\n")

freq = Counter(f for s in needs for f in s)
print("how many functions MENTION each family (not the same as payoff):")
for f, n in freq.most_common():
    print(f"  {n:5d}  {f}")

# only families that appear in some small requirement set can ever be in a cheap bundle
small = [s for s in needs if len(s) <= 4]
useful = sorted({f for s in small for f in s})
print(f"\nfunctions needing <=4 families: {len(small)}; families involved: {len(useful)}")

def payoff(bundle: frozenset[str]) -> int:
    return sum(1 for s in needs if s <= bundle)

print("\nbest bundles by size (exhaustive over the families that appear in <=4-family requirements):")
for size in (1, 2, 3, 4):
    best = []
    for combo in itertools.combinations(useful, size):
        b = frozenset(combo)
        p = payoff(b)
        if p:
            best.append((p, combo))
    best.sort(reverse=True)
    print(f"\n  --- size {size} ---")
    seen = set()
    shown = 0
    for p, combo in best:
        if shown >= 6:
            break
        print(f"    +{p:4d} READY   {'  +  '.join(combo)}")
        shown += 1
    if not best:
        print("    (nothing)")
