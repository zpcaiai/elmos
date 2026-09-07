#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from etgb.skills import audit_skills

EXCLUDED = {"PACKAGE_MANIFEST.json", "SHA256SUMS"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def files() -> list[Path]:
    return sorted(
        p for p in ROOT.rglob("*")
        if p.is_file() and p.relative_to(ROOT).as_posix() not in EXCLUDED
        and "__pycache__" not in p.parts and ".pytest_cache" not in p.parts
    )


def main() -> int:
    rows = [{"path": p.relative_to(ROOT).as_posix(), "size": p.stat().st_size, "sha256": sha256(p)} for p in files()]
    summary = json.loads((ROOT / "suites/summary.json").read_text(encoding="utf-8"))
    skills = audit_skills(ROOT)
    manifest = {
        "schema_version": "2.0",
        "package": "elmos-etgb-full-product-assurance-skills-package",
        "version": (ROOT / "VERSION").read_text().strip(),
        "generated_at": (ROOT / "GENERATED_AT").read_text().strip(),
        "file_count": len(rows),
        "total_bytes": sum(row["size"] for row in rows),
        "case_summary": summary,
        "skill_count": skills["skill_count"],
        "skills_valid": skills["valid"],
        "files": rows,
    }
    (ROOT / "PACKAGE_MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    checksum_files = files() + [ROOT / "PACKAGE_MANIFEST.json"]
    lines = [f"{sha256(p)}  {p.relative_to(ROOT).as_posix()}" for p in sorted(checksum_files)]
    (ROOT / "SHA256SUMS").write_text("\n".join(lines) + "\n")
    print(json.dumps({"file_count": len(rows), "total_bytes": manifest["total_bytes"], "skill_count": skills["skill_count"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
