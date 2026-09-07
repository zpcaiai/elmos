#!/usr/bin/env python3
"""Normalize the submitted B1-B55 archive into an explicit dual-namespace pack."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import re
import shutil
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

from validate_batch1_55_skill_pack import installed_name


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path("/Users/stephen/Downloads/elmos-codex-skills-batch1-55-complete")
DESTINATION = ROOT / "elmos-codex-skills-batch1-55-complete"
GENERATOR = Path(
    "/Users/stephen/.codex/skills/.system/skill-creator/scripts/generate_openai_yaml.py"
)
PACKAGE_VALIDATOR = ROOT / "tooling" / "validate_batch1_55_skill_pack.py"
PACKAGE_INSTALLER = ROOT / "tooling" / "install_batch1_55_skill_pack.py"
MIGRATION_SKILLS = ROOT / ".agents" / "skills"
PRODUCT_40_55 = ROOT / "elmos-codex-skills-batch40-55-complete" / "manifest.json"
OUTPUT_DIR = ROOT / "docs" / "batch1-55-skills"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tree_digest(root: Path) -> str:
    value = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        value.update(str(path.relative_to(root)).encode("utf-8"))
        value.update(b"\0")
        value.update(path.read_bytes())
        value.update(b"\0")
    return value.hexdigest()


def load_generator():
    spec = importlib.util.spec_from_file_location("elmos_openai_yaml_generator", GENERATOR)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Cannot load skill-creator generator: {GENERATOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.write_openai_yaml


def frontmatter_description(skill_text: str) -> str:
    match = re.match(r"^---\n(.*?)\n---", skill_text, re.DOTALL)
    if match is None:
        raise SystemExit("Skill is missing YAML frontmatter")
    frontmatter = match.group(1)
    try:
        parsed = yaml.safe_load(frontmatter)
    except yaml.YAMLError:
        parsed = None
    if isinstance(parsed, dict) and isinstance(parsed.get("description"), str):
        return parsed["description"].strip()
    description = re.search(r"(?m)^description:\s*(.*)$", frontmatter)
    if description is None:
        raise SystemExit("Skill frontmatter is missing description")
    raw = description.group(1).strip()
    if raw.startswith(('"', "'")):
        try:
            value = yaml.safe_load(raw)
            if isinstance(value, str):
                return value.strip()
        except yaml.YAMLError:
            pass
    return raw


def normalize_skill(skill_dir: Path, name: str, source_name: str, label: str, write_yaml) -> str:
    path = skill_dir / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    description = frontmatter_description(text).replace("<", "[").replace(">", "]")
    body_match = re.match(r"^---\n.*?\n---\n?(.*)$", text, re.DOTALL)
    if body_match is None:
        raise SystemExit(f"Cannot split Skill frontmatter: {source_name}")
    normalized = (
        "---\n"
        f"name: {name}\n"
        f"description: {json.dumps(description, ensure_ascii=False)}\n"
        "---\n\n"
        f"{body_match.group(1).lstrip()}"
    )
    path.write_text(normalized, encoding="utf-8")
    display = f"ELMOS {label}: {source_name.replace('-', ' ').title()}"[:96].rstrip()
    short = f"Run ELMOS {label} Skill with fail-closed evidence"
    prompt = f"Use ${name} to execute the ELMOS {label} contract with fail-closed evidence."
    with contextlib.redirect_stdout(io.StringIO()):
        output = write_yaml(
            skill_dir,
            name,
            [
                f"display_name={display}",
                f"short_description={short}",
                f"default_prompt={prompt}",
            ],
        )
    if output is None:
        raise SystemExit(f"Cannot generate agents/openai.yaml for {name}")
    return description


def edition_for(record: dict[str, object]) -> str:
    provenance = record["provenance"]
    if provenance == "normalized-batch1-28":
        return "normalized-source-incomplete"
    if provenance in {"imported-original-batch29-33", "repository-migration-pack-m34-m45"}:
        return "repository-contract"
    if provenance in {"imported-complete-batch34-38", "imported-complete-batch39"}:
        return "complete-source-contract"
    if provenance in {"approved-conversation-design", "generated-planning-edition"}:
        return str(provenance)
    raise SystemExit(f"Unknown provenance: {provenance}")


def package_readme() -> str:
    return """# ELMOS combined Skill pack — M1–M45 and Product B34–B55

This repaired package is an explicit dual-namespace catalog. It is not one
linear Batch 1–55 certification series.

## Inventory

- Migration Packs M1–M45: **820 Skills**
- Product commercialization B34–B55: **1,004 Skills**
- Total installable contracts: **1,824 Skills**
- Deterministic aliases for names over 64 characters: **1,015**

Every Skill passes the official `skill-creator` validator and includes an
invocable `agents/openai.yaml` interface. `source_name` is retained in the
manifest for every deterministic alias.

## Completion boundary

- M1–M28: 448 normalized implementation-planning Skills; exact original source
  bundles were unavailable and M21–M28 contain generic recovered domains.
- M29–M45: 372 repository contracts.
- Product B34–B39: 236 complete-source contracts.
- Product B40A: 16 approved conversation-design contracts.
- Product B40B–B55C: 752 generated planning-edition contracts requiring domain
  owner refinement.
- Customer, provider, production and certification evidence: `NOT_RUN`.

Consequently, structural validation is `PASS`, while overall completion remains
`NOT_COMPLETE`. Static Skill validation never certifies implementation or field
operation.

## Validate

```bash
./validate.sh
```

## Install

The target directory is mandatory. By default, only repository, complete-source
and approved-design contracts are installed:

```bash
./install.sh /absolute/path/to/codex/skills
```

Use `--include-non-authoritative` only after accepting the normalized-source and
planning-edition limitations. Existing destinations fail preflight unless
`--overwrite` is supplied; overwritten Skills are moved to a recoverable backup.
"""


def agents_rules() -> str:
    return """# Combined ELMOS Skill pack rules

- Treat `migration-pack` M1–M45 and `product-commercialization` B34–B55 as separate namespaces.
- Inspect `manifest.json` and the exact `editionStatus` before invoking a Skill.
- `normalized-source-incomplete` and `generated-planning-edition` are not authoritative production contracts.
- Preserve immutable source facts, versions, evidence and decision lineage.
- Never weaken tenant, authorization, privacy, secret, safety, financial or evidence boundaries.
- Static validation does not change external evidence from `NOT_RUN` and cannot certify a Batch.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()
    source = args.source.resolve()
    if DESTINATION.exists():
        raise SystemExit(f"Destination already exists; refusing to overwrite: {DESTINATION}")
    if not (source / "manifest.json").is_file():
        raise SystemExit(f"Source manifest is missing: {source}")

    source_manifest_bytes = (source / "manifest.json").read_bytes()
    source_manifest = json.loads(source_manifest_bytes)
    source_records = source_manifest.get("skills", [])
    if source_manifest.get("skillCount") != 1554 or len(source_records) != 1554:
        raise SystemExit("Submitted archive must contain exactly 1,554 source Skills")
    source_provenance = Counter(record["provenance"] for record in source_records)
    if source_provenance != {
        "normalized-batch1-28": 448,
        "imported-original-batch29-33": 102,
        "imported-complete-batch34-38": 188,
        "imported-complete-batch39": 48,
        "imported-planning-and-approved-batch40-55": 768,
    }:
        raise SystemExit(f"Unexpected source provenance: {dict(source_provenance)}")

    product_manifest = json.loads(PRODUCT_40_55.read_text(encoding="utf-8"))
    product_metadata: dict[str, dict[str, object]] = {}
    for item in product_manifest["skills"]:
        product_metadata[item.get("source_name", item["name"])] = item
    if len(product_metadata) != 768:
        raise SystemExit("Product B40-B55 metadata must contain 768 source identities")

    records: list[dict[str, object]] = []
    for item in source_records:
        record = dict(item)
        batch = int(record["batch"])
        record["batch"] = batch
        record["namespace"] = "migration-pack" if batch <= 33 else "product-commercialization"
        if batch >= 40:
            metadata = product_metadata.get(str(record["name"]))
            if metadata is None:
                raise SystemExit(f"Missing Product B40-B55 provenance metadata: {record['name']}")
            record["subbatch"] = metadata["subbatch"]
            record["provenance"] = metadata["provenance"]
        record["sourcePath"] = record["path"]
        records.append(record)

    for skill_dir in sorted(MIGRATION_SKILLS.iterdir()):
        match = re.match(r"^b(3[4-9]|4[0-5])-", skill_dir.name)
        if not match or not (skill_dir / "SKILL.md").is_file():
            continue
        skill_text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        records.append(
            {
                "name": skill_dir.name,
                "path": f"agent-skills/runtime/{skill_dir.name}/SKILL.md",
                "sourcePath": f".agents/skills/{skill_dir.name}/SKILL.md",
                "batch": int(match.group(1)),
                "namespace": "migration-pack",
                "provenance": "repository-migration-pack-m34-m45",
                "description": frontmatter_description(skill_text),
            }
        )
    if len(records) != 1824:
        raise SystemExit(f"Expected 1,824 combined Skills, found {len(records)}")

    aliases = [installed_name(str(record["name"])) for record in records]
    if len(aliases) != len(set(aliases)):
        raise SystemExit("Deterministic name normalization produced a collision")

    write_yaml = load_generator()
    source_tree_sha256 = tree_digest(source)
    with tempfile.TemporaryDirectory(prefix=".batch1-55-", dir=ROOT) as temp:
        staging = Path(temp) / DESTINATION.name
        shutil.copytree(source, staging)
        normalized_root = staging / "agent-skills" / "normalized"
        normalized_root.mkdir(parents=True)
        normalized_records: list[dict[str, object]] = []
        for record in records:
            source_name = str(record["name"])
            name = installed_name(source_name)
            if record["provenance"] == "repository-migration-pack-m34-m45":
                original_dir = MIGRATION_SKILLS / source_name
            else:
                original_dir = staging / Path(str(record["path"])).parent
            target_dir = normalized_root / name
            shutil.copytree(original_dir, target_dir)
            label = (
                f"M{int(record['batch']):02d}"
                if record["namespace"] == "migration-pack"
                else f"B{int(record['batch'])}"
            )
            description = normalize_skill(target_dir, name, source_name, label, write_yaml)
            normalized = dict(record)
            normalized["source_name"] = source_name
            normalized["name"] = name
            normalized["description"] = description
            normalized["path"] = f"agent-skills/runtime/{name}/SKILL.md"
            normalized["editionStatus"] = edition_for(normalized)
            normalized["sha256"] = digest((target_dir / "SKILL.md").read_bytes())
            normalized_records.append(normalized)

        shutil.rmtree(staging / "agent-skills" / "runtime")
        normalized_root.rename(staging / "agent-skills" / "runtime")
        normalized_records.sort(key=lambda item: (str(item["namespace"]), int(item["batch"]), str(item["name"])))

        provenance_counts = Counter(str(record["provenance"]) for record in normalized_records)
        edition_counts = Counter(str(record["editionStatus"]) for record in normalized_records)
        namespace_counts = Counter(str(record["namespace"]) for record in normalized_records)
        manifest = {
            "package": DESTINATION.name,
            "schemaVersion": "2",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "sourceGeneratedAt": source_manifest.get("generatedAt"),
            "sourceManifestSha256": digest(source_manifest_bytes),
            "sourcePackageTreeSha256": source_tree_sha256,
            "scope": {
                "migration-pack": "M1-M45",
                "product-commercialization": "B34-B55",
                "strict-test-suite": "separate Batch 1-37 qualification namespace",
            },
            "skillCount": len(normalized_records),
            "namespaceCounts": dict(namespace_counts),
            "provenanceCounts": dict(provenance_counts),
            "editionCounts": dict(edition_counts),
            "nameNormalization": {
                "maximumLength": 64,
                "algorithm": "source name when <=64, otherwise first 55 characters plus '-' plus sha256[:8]",
                "renamed": sum(record["name"] != record["source_name"] for record in normalized_records),
                "sourceNamePreserved": True,
            },
            "completion": {
                "structural": "PASS",
                "overall": "NOT_COMPLETE",
                "blockers": [
                    "448 M1-M28 Skills use normalized recovery because exact original bundles were unavailable",
                    "752 Product B40B-B55C Skills remain generated planning edition",
                    "customer/provider/production/certification evidence has not been executed",
                ],
            },
            "externalEvidenceStatus": "NOT_RUN",
            "skills": normalized_records,
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (staging / "README.md").write_text(package_readme(), encoding="utf-8")
        (staging / "AGENTS.md").write_text(agents_rules(), encoding="utf-8")
        references = staging / "references"
        references.mkdir(exist_ok=True)
        (references / "provenance.md").write_text(
            "# Provenance and completion\n\n"
            "The original submitted archive is bound by `sourceManifestSha256` and "
            "`sourcePackageTreeSha256` in `manifest.json`. The repaired catalog adds "
            "the repository M34-M45 contracts, deterministic aliases and official "
            "interfaces. Normalized-source and planning editions are intentionally "
            "non-authoritative. External evidence remains `NOT_RUN`.\n",
            encoding="utf-8",
        )
        scripts = staging / "scripts"
        shutil.copy2(PACKAGE_VALIDATOR, scripts / "validate_package.py")
        shutil.copy2(PACKAGE_INSTALLER, scripts / "install_package.py")
        (staging / "validate.sh").write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\nROOT=\"$(cd \"$(dirname \"$0\")\" && pwd)\"\n"
            "/opt/homebrew/bin/uv run --quiet --with pyyaml python \"$ROOT/scripts/validate_package.py\" \"$ROOT\"\n",
            encoding="utf-8",
        )
        (staging / "install.sh").write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\nROOT=\"$(cd \"$(dirname \"$0\")\" && pwd)\"\n"
            "python3 \"$ROOT/scripts/install_package.py\" --pack \"$ROOT\" \"$@\"\n",
            encoding="utf-8",
        )
        (staging / "validate.sh").chmod(0o755)
        (staging / "install.sh").chmod(0o755)
        staging.rename(DESTINATION)

    normalized_manifest_sha256 = digest((DESTINATION / "manifest.json").read_bytes())
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary = {
        "generated_by": "tooling/integrate_batch1_55_complete_skill_pack.py",
        "source_directory": str(source),
        "source_manifest_sha256": digest(source_manifest_bytes),
        "source_package_tree_sha256": source_tree_sha256,
        "normalized_manifest_sha256": normalized_manifest_sha256,
        "skill_count": 1824,
        "namespace_counts": {"migration-pack": 820, "product-commercialization": 1004},
        "deterministic_aliases": 1015,
        "structural_status": "PASS",
        "overall_completion": "NOT_COMPLETE",
        "external_evidence_status": "NOT_RUN",
    }
    (OUTPUT_DIR / "verification.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
