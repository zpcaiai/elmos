#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_GLOBAL = [
    "~/.gemini/config/skills",
    "~/.gemini/antigravity-cli/skills",
    "~/.agents/skills",
]


def parse_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return {"name": path.parent.name, "description": ""}
    lines = text.splitlines()
    end = None
    for i in range(1, min(len(lines), 200)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {"name": path.parent.name, "description": ""}
    fm = lines[1:end]
    name = path.parent.name
    description = ""
    i = 0
    while i < len(fm):
        line = fm[i]
        m = re.match(r"^name\s*:\s*(.*)$", line, flags=re.I)
        if m:
            value = m.group(1).strip().strip('"\'')
            if value:
                name = value
            i += 1
            continue
        m = re.match(r"^description\s*:\s*(.*)$", line, flags=re.I)
        if m:
            value = m.group(1).strip()
            if value in {">", "|-", "|", ">-"}:
                buf = []
                i += 1
                while i < len(fm):
                    if fm[i] and not fm[i][0].isspace():
                        break
                    buf.append(fm[i].strip())
                    i += 1
                description = " ".join(x for x in buf if x)
                continue
            description = value.strip('"\'')
        i += 1
    return {"name": name, "description": description}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_config(root: Path) -> dict:
    p = root / ".elmos" / "skill-router.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {
        "project_skill_roots": [".agents/skills"],
        "global_skill_roots": DEFAULT_GLOBAL,
        "include_global": True,
    }


def compact_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        home = Path.home()
        try:
            return "~/" + str(path.relative_to(home))
        except ValueError:
            return str(path)


def discover(root: Path, config: dict) -> list[dict]:
    roots: list[tuple[str, int, Path]] = []
    for rel in config.get("project_skill_roots", [".agents/skills"]):
        roots.append(("project", 0, (root / rel).resolve()))
    if config.get("include_global", True):
        for idx, raw in enumerate(config.get("global_skill_roots", DEFAULT_GLOBAL), start=1):
            roots.append(("global", idx, Path(os.path.expanduser(raw)).resolve()))

    by_name: dict[str, dict] = {}
    for scope, priority, base in roots:
        if not base.is_dir():
            continue
        for skill_file in sorted(base.rglob("SKILL.md")):
            # Avoid nested references accidentally named SKILL.md inside a skill.
            try:
                rel_parts = skill_file.relative_to(base).parts
            except ValueError:
                continue
            if len(rel_parts) > 3:
                continue
            meta = parse_frontmatter(skill_file)
            name = meta["name"] or skill_file.parent.name
            item = {
                "name": name,
                "description": meta.get("description", ""),
                "scope": scope,
                "scope_priority": priority,
                "path": compact_path(skill_file, root),
                "sha256": sha256(skill_file),
                "mtime": skill_file.stat().st_mtime,
            }
            old = by_name.get(name)
            if old is None or priority < old["scope_priority"]:
                by_name[name] = item

    return sorted(by_name.values(), key=lambda x: (x["scope_priority"], x["name"].lower()))


def main() -> int:
    ap = argparse.ArgumentParser(description="Build Antigravity skill index")
    ap.add_argument("--root", default=".")
    ap.add_argument("--output", default=None)
    ap.add_argument("--stdout", action="store_true")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    config = load_config(root)
    skills = discover(root, config)
    payload = {
        "schema": "elmos.skills-index.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_root": str(root),
        "skill_count": len(skills),
        "skills": skills,
        "authoritative_evidence": False,
    }
    encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.stdout:
        print(encoded, end="")
    else:
        out = Path(args.output).resolve() if args.output else root / ".agents" / "skills-index.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(encoded, encoding="utf-8")
        print(f"Indexed {len(skills)} skills -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
