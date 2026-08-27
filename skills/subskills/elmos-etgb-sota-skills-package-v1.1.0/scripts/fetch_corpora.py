#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
import yaml


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch approved ETGB public corpora at locked commits")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--allow-network", action="store_true")
    args = parser.parse_args()
    if not args.allow_network:
        raise SystemExit("Refusing network access. Re-run with --allow-network after license and sandbox review.")
    lock = yaml.safe_load((args.root / "corpora/corpus-lock.yaml").read_text(encoding="utf-8"))
    worktrees = args.root / "corpora/worktrees"
    worktrees.mkdir(parents=True, exist_ok=True)
    for repo in lock["repositories"]:
        if repo["license_review"] != "approved":
            print(f"SKIP {repo['id']}: license_review={repo['license_review']}")
            continue
        dst = worktrees / repo["id"]
        if not dst.exists():
            subprocess.run(["git", "clone", "--filter=blob:none", "--no-checkout", f"https://github.com/{repo['repository']}.git", str(dst)], check=True)
        subprocess.run(["git", "fetch", "--depth", "1", "origin", repo["commit"]], cwd=dst, check=True)
        subprocess.run(["git", "checkout", "--detach", repo["commit"]], cwd=dst, check=True)
        actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=dst, text=True).strip()
        if actual != repo["commit"]:
            raise RuntimeError(f"commit mismatch for {repo['id']}: {actual}")
        print(f"OK {repo['id']} {actual}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
