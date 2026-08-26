"""Of the 4,539 subjects rejected as NESTED_SYMBOL: methods, or closures?"""
from __future__ import annotations
import ast, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, "/root/eval")
import measure_admission_headroom as H
from elmos_polyglot_route.project_graph import python_coverage_subjects

root = Path("/root/eval/corpus")
shape = Counter()
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
        # parent map + set of names defined directly under a ClassDef
        method_names, closure_names = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for child in node.body:
                    if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                        method_names.add(child.name)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                for child in node.body:
                    if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                        closure_names.add(child.name)
        for s in python_coverage_subjects(tree, rel):
            if "PYTHON_NESTED_SYMBOL_CONVERSION_UNCOVERED" not in s.blocking_reasons:
                continue
            if s.name in method_names and s.name in closure_names:
                shape["both-spellings-in-file"] += 1
            elif s.name in method_names:
                shape["class method"] += 1
            elif s.name in closure_names:
                shape["inner function / closure"] += 1
            else:
                shape["other nesting"] += 1
total = sum(shape.values())
print(f"NESTED_SYMBOL subjects: {total}")
for k, v in shape.most_common():
    print(f"  {v:6d}  {v/total:6.2%}  {k}")
