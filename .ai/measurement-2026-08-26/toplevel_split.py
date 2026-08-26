"""The 7,784 top-level-effect subjects: what are they actually?"""
from __future__ import annotations
import ast, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, "/root/eval")
import measure_admission_headroom as H
from elmos_polyglot_route.project_graph import python_coverage_subjects

root = Path("/root/eval/corpus")
kinds = Counter()
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
        n = sum(1 for s in python_coverage_subjects(tree, rel)
                if s.subject_kind == "top-level-effect")
        if not n:
            continue
        for node in tree.body:
            if isinstance(node, ast.Import | ast.ImportFrom):
                kinds["import"] += 1
            elif isinstance(node, ast.Assign | ast.AnnAssign):
                target = node.targets[0] if isinstance(node, ast.Assign) else node.target
                name = ast.unparse(target)
                kinds["module constant (__all__ etc.)" if name.startswith("__")
                      else "module-level assignment"] += 1
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                continue
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                kinds["module docstring"] += 1
            elif isinstance(node, ast.If):
                kinds["conditional (TYPE_CHECKING / version guard)"] += 1
            elif isinstance(node, ast.Try):
                kinds["try (optional import)"] += 1
            else:
                kinds[f"other: {type(node).__name__}"] += 1
total = sum(kinds.values())
print(f"module-body statements in files that have top-level effects: {total}")
for k, v in kinds.most_common(12):
    print(f"  {v:6d}  {v/total:6.2%}  {k}")
