#!/usr/bin/env python3
"""Package-native structural validator (no third-party imports)."""
from pathlib import Path
import json, re, sys

root = Path(__file__).resolve().parents[1]
manifest_path = root / "PACKAGE_MANIFEST.json"
errors = []

required_docs = [
    "README.md",
    "CODEX_IMPLEMENTATION_PROMPT.md",
    "SKILL.md",
    "SKILL_INDEX.md",
    "IMPLEMENTATION_CHECKLIST.md",
    "VALIDATION_REPORT.md",
    "PACKAGE_MANIFEST.json",
    "ARCHETYPE_MAP.json",
]
for name in required_docs:
    if not (root / name).is_file():
        errors.append("missing " + name)

skills = sorted((root / "skills").glob("*/SKILL.md")) if (root / "skills").is_dir() else []
if not skills:
    errors.append("no skills present")

names = []
for path in skills:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"^name:\s*(\S+)", text, re.M)
    if not match:
        errors.append("missing frontmatter name: " + str(path))
        continue
    names.append(match.group(1))
    for heading in ("## Objective", "## Workflow", "## Required Tests",
                    "## Verification", "## Stop and Escalate", "## Definition of Done"):
        if heading not in text:
            errors.append(f"{path}: missing {heading}")
if len(names) != len(set(names)):
    errors.append("duplicate skill name")

for path in sorted((root / "schemas").glob("*.json")):
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"invalid json {path}: {exc}")

if manifest_path.is_file():
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    import hashlib
    for entry in manifest.get("files", []):
        target = root / entry["path"]
        if not target.is_file():
            errors.append("manifest file missing: " + entry["path"])
            continue
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != entry["sha256"]:
            errors.append("digest mismatch: " + entry["path"])
    if manifest.get("skill_count") != len(skills):
        errors.append("manifest skill_count does not match skills on disk")

if errors:
    print("FAIL")
    print("\n".join(errors))
    sys.exit(1)
print(f"PASS: {len(skills)} skills; schemas, manifest and archetype map valid.")
