#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

EN_STOP = {
    "the", "a", "an", "and", "or", "to", "of", "for", "in", "on", "with", "by",
    "use", "using", "implement", "continue", "next", "current", "project", "task",
    "work", "skill", "skills", "elmos"
}
CONTINUE_TERMS = {"continue", "next", "继续", "继续实现", "下一个", "继续下一个"}


def terms(text: str) -> set[str]:
    ascii_tokens = re.findall(r"[a-zA-Z0-9_.+-]{2,}", text.lower())
    words = {t for t in ascii_tokens if t not in EN_STOP}
    # Keep common CJK domain phrases intact because whitespace tokenization is weak for CJK.
    cjk_phrases = re.findall(r"[\u4e00-\u9fff]{2,8}", text)
    words.update(cjk_phrases)
    return words


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def ensure_index(root: Path, no_refresh: bool) -> dict:
    index_path = root / ".agents" / "skills-index.json"
    refresh = root / ".agents" / "skills" / "elmos-auto-skill-router" / "scripts" / "refresh_skill_index.py"
    if not no_refresh and refresh.exists():
        subprocess.run([sys.executable, str(refresh), "--root", str(root)], check=True, stdout=subprocess.DEVNULL)
    return load_json(index_path, {"skills": []})


def is_continue(task: str) -> bool:
    s = task.strip().lower()
    return s in CONTINUE_TERMS or any(x in s for x in ["continue current", "继续当前", "继续上次"])


def route(root: Path, task: str, no_refresh: bool = False) -> list[dict]:
    index = ensure_index(root, no_refresh)
    config = load_json(root / ".elmos" / "skill-router.json", {})
    installed = {s["name"]: s for s in index.get("skills", [])}
    task_low = task.lower()
    task_terms = terms(task)
    scores: dict[str, float] = {}
    reasons: dict[str, list[str]] = {}

    for name, skill in installed.items():
        hay = f"{name} {skill.get('description','')}".lower()
        skill_terms = terms(hay)
        overlap = task_terms & skill_terms
        score = float(len(overlap) * 3)
        if name.lower() in task_low:
            score += 12
        for tok in task_terms:
            if len(tok) >= 4 and tok in hay:
                score += 1
        if score > 0:
            scores[name] = score
            reasons[name] = [f"matched: {', '.join(sorted(overlap)[:8])}" if overlap else "semantic/name match"]

    for name in config.get("always_use_skills", []):
        if name in installed:
            scores[name] = max(scores.get(name, 0), 80)
            reasons.setdefault(name, []).append("configured always_use_skills")

    for rule in config.get("mandatory_rules", []):
        name = rule.get("skill")
        if name not in installed:
            continue
        hits = [x for x in rule.get("when_any", []) if x.lower() in task_low]
        if hits:
            scores[name] = max(scores.get(name, 0), 100)
            reasons.setdefault(name, []).append("mandatory rule: " + ", ".join(hits[:6]))

    # Continuation should preserve last routed skills where available.
    active_path = root / ".elmos" / "active-skills.json"
    active = load_json(active_path, {})
    if is_continue(task):
        for name in active.get("skills", []):
            if name in installed:
                scores[name] = max(scores.get(name, 0), 70)
                reasons.setdefault(name, []).append("continued from last routed task")
        # Strong signal from proof-driven progress file.
        if (root / ".elmos" / "certification-progress.yaml").exists() and "elmos-proof-driven-certification" in installed:
            scores["elmos-proof-driven-certification"] = max(scores.get("elmos-proof-driven-certification", 0), 95)
            reasons.setdefault("elmos-proof-driven-certification", []).append("certification progress detected")

    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], installed[kv[0]]["scope_priority"], kv[0]))
    max_count = int(config.get("max_recommended_skills", 8))
    result = []
    for name, score in ranked[:max_count]:
        skill = installed[name]
        result.append({
            "name": name,
            "score": score,
            "scope": skill["scope"],
            "path": skill["path"],
            "description": skill.get("description", ""),
            "reasons": reasons.get(name, []),
        })
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Route an engineering task to installed Antigravity skills")
    ap.add_argument("--root", default=".")
    ap.add_argument("--task", required=True)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-refresh", action="store_true")
    ap.add_argument("--remember", action="store_true")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    routed = route(root, args.task, args.no_refresh)
    if args.remember:
        state = {
            "schema": "elmos.active-skills.v1",
            "task": args.task,
            "skills": [x["name"] for x in routed],
            "authoritative_evidence": False,
        }
        p = root / ".elmos" / "active-skills.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps({"task": args.task, "skills": routed}, ensure_ascii=False, indent=2))
        return 0

    if not routed:
        print("No deterministic matches. Let Antigravity perform semantic skill discovery from installed skill descriptions.")
        return 0
    print("ROUTED SKILLS:")
    for item in routed:
        reason = "; ".join(item["reasons"])
        print(f"- {item['name']} [{item['scope']}] score={item['score']:.0f} :: {reason}")
    print("\nPROMPT DIRECTIVE:")
    names = ", ".join(x["name"] for x in routed)
    print(f"Automatically use and compose these materially relevant skills when applicable: {names}.")
    print("Inspect repository state before editing. Execute real validation before claiming completion.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
