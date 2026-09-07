#!/usr/bin/env python3
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def selected_files(profile: str) -> list[tuple[Path, Path]]:
    profile_file = ROOT / "profiles" / f"{profile}.yaml"
    if not profile_file.is_file():
        raise SystemExit(f"unknown profile: {profile}")
    p = yaml.safe_load(profile_file.read_text(encoding="utf-8"))
    selected = set(p["spec"]["skills"])
    mappings: list[tuple[Path,Path]]=[]

    for manifest in ROOT.glob("skills/P*/*/manifest.yaml"):
        name = manifest.parent.name
        if name not in selected:
            continue
        rel = manifest.parent.relative_to(ROOT / "skills")
        for src in manifest.parent.rglob("*"):
            if src.is_file():
                mappings.append((src, Path("skills/formal-assurance-kernel") / rel / src.name))

    directory_maps = {
        "contracts":"contracts/formal-assurance",
        "workflows":"workflows/formal-assurance",
        "policies":"policies/formal-assurance",
        "verifier-adapters":"verifier-adapters/formal-assurance",
        "reference-kernel":"reference/formal-assurance-kernel",
        "golden-routes":"golden-routes/formal-assurance",
        "docs":"docs/formal-assurance",
    }
    for src_dir,dst_dir in directory_maps.items():
        for src in (ROOT/src_dir).rglob("*"):
            if src.is_file() and "__pycache__" not in src.parts and not src.name.endswith(".pyc"):
                mappings.append((src,Path(dst_dir)/src.relative_to(ROOT/src_dir)))

    for src in (ROOT/"db/migration").glob("*.sql"):
        mappings.append((src,Path("db/migration")/src.name))

    for name in ["PACKAGE_MANIFEST.yaml","README.md","SKILLS_INDEX.md","LICENSE-POLICY.md","SECURITY.md","VERSION"]:
        src=ROOT/name
        if src.exists():
            mappings.append((src,Path("skills/formal-assurance-kernel")/name))

    mappings.append((profile_file,Path("skills/formal-assurance-kernel/profiles")/profile_file.name))
    return sorted(mappings,key=lambda x:x[1].as_posix())

def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("target",type=Path)
    parser.add_argument("--profile",default="full")
    parser.add_argument("--force",action="store_true")
    parser.add_argument("--dry-run",action="store_true")
    args=parser.parse_args()
    target=args.target.resolve()
    mappings=selected_files(args.profile)
    conflicts=[]
    for src,rel in mappings:
        dst=target/rel
        if dst.exists() and dst.is_file() and sha(dst)!=sha(src):
            conflicts.append(rel.as_posix())
        elif dst.exists() and not dst.is_file():
            conflicts.append(rel.as_posix()+" (not a file)")
    if conflicts and not args.force:
        print("Install aborted; conflicting files (use --force to backup and replace):")
        print("\n".join(conflicts))
        return 2

    timestamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_root=target/".elmos/backups/formal-assurance"/timestamp
    entries=[]
    for src,rel in mappings:
        dst=target/rel
        backup=None
        same=dst.is_file() and sha(dst)==sha(src)
        if args.dry_run:
            action="reuse" if same else ("replace" if dst.exists() else "create")
            print(f"{action}: {rel}")
            continue
        dst.parent.mkdir(parents=True,exist_ok=True)
        if dst.exists() and not same:
            backup=backup_root/rel
            backup.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(dst,backup)
        if not same:
            shutil.copy2(src,dst)
        entries.append({
            "source":src.relative_to(ROOT).as_posix(),
            "destination":rel.as_posix(),
            "sha256":sha(src),
            "backup":backup.relative_to(target).as_posix() if backup else None,
        })

    if args.dry_run:
        print(f"dry-run complete: {len(mappings)} files")
        return 0

    manifest={
      "packageId":yaml.safe_load((ROOT/"PACKAGE_MANIFEST.yaml").read_text())["metadata"]["packageId"],
      "profile":args.profile,"installedAt":timestamp,"files":entries
    }
    manifest_path=target/".elmos/formal-assurance-install-manifest.json"
    manifest_path.parent.mkdir(parents=True,exist_ok=True)
    manifest_path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(f"installed {len(entries)} files; manifest: {manifest_path}")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
