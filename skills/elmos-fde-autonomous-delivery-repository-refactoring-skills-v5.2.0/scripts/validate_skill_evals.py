#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, re, yaml
from collections import defaultdict
from pathlib import Path

def read_jsonl(path: Path):
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try: yield json.loads(line)
            except Exception as exc: raise ValueError(f"{path}:{i}: {exc}")

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("root", nargs="?", default="."); args=p.parse_args(); root=Path(args.root).resolve()
    errors=[]; ids=set()
    codex_skills={p.parent.name for p in (root/".agents/skills").glob("*/SKILL.md")}
    by=defaultdict(set)
    for case in read_jsonl(root/"evals/codex-skill-triggers.jsonl"):
        if case["id"] in ids: errors.append(f"duplicate eval id {case['id']}")
        ids.add(case["id"]); by[case["expectedSkill"]].add(case["kind"])
    required={"explicit","contextual","negative","boundary"}
    for sid in codex_skills:
        if by[sid] != required: errors.append(f"{sid}: eval kinds {sorted(by[sid])} != {sorted(required)}")
    if set(by)-codex_skills: errors.append(f"unknown Codex skills in evals: {sorted(set(by)-codex_skills)}")

    atomic_ids=set()
    for pth in (root/"skills/atomic").rglob("manifest.yaml"):
        atomic_ids.add(yaml.safe_load(pth.read_text(encoding="utf-8"))["metadata"]["id"])
    kinds=defaultdict(set)
    for case in read_jsonl(root/"evals/atomic-skill-triggers.jsonl"):
        if case["id"] in ids: errors.append(f"duplicate eval id {case['id']}")
        ids.add(case["id"]); kinds[case["expectedSkill"]].add(case["kind"])
    for sid in atomic_ids:
        if not {"positive","negative"}.issubset(kinds[sid]): errors.append(f"{sid}: missing positive/negative trigger evals")
    if set(kinds)-atomic_ids: errors.append(f"unknown atomic skills in evals: {sorted(set(kinds)-atomic_ids)}")
    print(json.dumps({"status":"PASS" if not errors else "FAIL", "evalCases":len(ids), "errors":errors}, ensure_ascii=False, indent=2))
    return 1 if errors else 0
if __name__=="__main__": raise SystemExit(main())
