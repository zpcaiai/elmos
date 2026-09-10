#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

BEGIN = "<!-- ELMOS_AUTO_SKILL_ROUTER_BEGIN -->"
END = "<!-- ELMOS_AUTO_SKILL_ROUTER_END -->"


def inject_block(existing: str, block: str) -> str:
    if BEGIN in existing and END in existing:
        before = existing.split(BEGIN, 1)[0].rstrip()
        after = existing.split(END, 1)[1].lstrip("\n")
        pieces = [x for x in [before, block.strip(), after.rstrip()] if x]
        return "\n\n".join(pieces).rstrip() + "\n"
    if existing.strip():
        return existing.rstrip() + "\n\n" + block.strip() + "\n"
    return block.strip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Install Elmos Auto Skill Router into an Antigravity project")
    ap.add_argument("project", nargs="?", default=".")
    ap.add_argument("--force-config", action="store_true", help="replace existing .elmos/skill-router.json")
    args = ap.parse_args()

    package = Path(__file__).resolve().parent
    project = Path(args.project).expanduser().resolve()
    project.mkdir(parents=True, exist_ok=True)

    src_skill = package / "elmos-auto-skill-router"
    dst_skill = project / ".agents" / "skills" / "elmos-auto-skill-router"
    dst_skill.parent.mkdir(parents=True, exist_ok=True)
    if dst_skill.exists():
        shutil.rmtree(dst_skill)
    shutil.copytree(src_skill, dst_skill)

    config_src = src_skill / "templates" / "skill-router.json"
    config_dst = project / ".elmos" / "skill-router.json"
    config_dst.parent.mkdir(parents=True, exist_ok=True)
    if args.force_config or not config_dst.exists():
        shutil.copy2(config_src, config_dst)

    agents = project / ".agents" / "AGENTS.md"
    agents.parent.mkdir(parents=True, exist_ok=True)
    old = agents.read_text(encoding="utf-8") if agents.exists() else ""
    block = (package / "AGENTS.autoload.snippet.md").read_text(encoding="utf-8")
    agents.write_text(inject_block(old, block), encoding="utf-8")

    refresh = dst_skill / "scripts" / "refresh_skill_index.py"
    subprocess.run([sys.executable, str(refresh), "--root", str(project)], check=True)

    print("Installed Elmos Auto Skill Router v1.0.0")
    print(f"Project: {project}")
    print(f"Skill:   {dst_skill}")
    print(f"Rules:   {agents}")
    print(f"Config:  {config_dst}")
    print(f"Index:   {project / '.agents' / 'skills-index.json'}")
    print("\nIn Antigravity, ordinary requests and 'continue' can now rely on automatic skill routing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
