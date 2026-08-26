"""Where the 16,046 go BEFORE the analyzer -- distinct subjects, not occurrences."""
from __future__ import annotations
import ast, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, "/root/eval")
import measure_admission_headroom as H
from elmos_polyglot_route.project_graph import python_coverage_subjects

root = Path("/root/eval/corpus")
total = 0
kinds = Counter(); first = Counter(); combos = Counter()
candidate_clean = 0; candidate_blocked = 0
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
        for s in python_coverage_subjects(tree, rel):
            total += 1
            kinds[s.subject_kind] += 1
            if s.candidate and not s.blocking_reasons:
                candidate_clean += 1
                continue
            if s.candidate:
                candidate_blocked += 1
            reasons = list(s.blocking_reasons)
            if reasons:
                first[reasons[0]] += 1
                combos[" + ".join(sorted(reasons))] += 1

print(f"coverage subjects            {total}")
print(f"  reach the analyzer         {candidate_clean}   ({candidate_clean/total:.2%})")
print(f"  candidate but blocked      {candidate_blocked}")
print(f"  not a candidate            {total - candidate_clean - candidate_blocked}")
print("\nsubject kinds (distinct subjects):")
for k, v in kinds.most_common():
    print(f"  {v:6d}  {v/total:6.2%}  {k}")
print("\nFIRST structural blocker, distinct subjects:")
for k, v in first.most_common(12):
    print(f"  {v:6d}  {v/total:6.2%}  {k}")
print("\nmost common blocker COMBINATIONS:")
for k, v in combos.most_common(8):
    print(f"  {v:6d}  {k}")
