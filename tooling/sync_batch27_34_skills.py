#!/usr/bin/env python3
"""Materialize the two independently named Batch 27-34 skill families.

The migration certification package uses M29-M34 to avoid colliding with the
ELMOS product roadmap's Batch 29-34.  Every new skill is initialized through
the repository-approved skill-creator scripts before the authoritative skill
body is installed.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "agent-skills" / "runtime"
PRODUCT_SOURCE = ROOT / "ChatGPT-Git项目商业化模式 (1).md"
MIGRATION_SOURCE = Path(
    "/Users/stephen/Downloads/migration-platform-batch20-b29-b30-b31-b32-b33-b34/.agents/skills"
)
SKILL_CREATOR = Path("/Users/stephen/.codex/skills/.system/skill-creator/scripts")
INIT_SKILL = SKILL_CREATOR / "init_skill.py"
GENERATE_YAML = SKILL_CREATOR / "generate_openai_yaml.py"

PRODUCT_RANGES = {
    27: (23070, 28199),
    28: (28200, 33763),
    29: (33764, 39472),
    30: (39473, 44752),
    31: (44753, 48346),
    33: (49989, 57136),
    34: (57137, 68775),
}


def run(*args: str) -> None:
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL)


def initialize(name: str, display_name: str, short_description: str, default_prompt: str) -> Path:
    skill_dir = RUNTIME / name
    if not skill_dir.exists():
        run(
            sys.executable,
            str(INIT_SKILL),
            name,
            "--path",
            str(RUNTIME),
            "--interface",
            f"display_name={display_name}",
            "--interface",
            f"short_description={short_description}",
            "--interface",
            f"default_prompt={default_prompt}",
        )
    return skill_dir


def regenerate_interface(skill_dir: Path, display_name: str, short_description: str, default_prompt: str) -> None:
    run(
        sys.executable,
        str(GENERATE_YAML),
        str(skill_dir),
        "--interface",
        f"display_name={display_name}",
        "--interface",
        f"short_description={short_description}",
        "--interface",
        f"default_prompt={default_prompt}",
    )


def normalize_frontmatter(content: str) -> str:
    match = re.match(r"^---\nname:\s*([^\n]+)\ndescription:\s*([^\n]+)\n---\n", content)
    if not match:
        raise SystemExit("Skill content must start with name and one-line description frontmatter")
    name = match.group(1).strip()
    description = match.group(2).strip()
    if len(description) >= 2 and description[0] == description[-1] and description[0] in "\"'":
        description = description[1:-1]
    header = f"---\nname: {name}\ndescription: {json.dumps(description, ensure_ascii=False)}\n---\n"
    return header + content[match.end() :]


def installed_name(original_name: str) -> str:
    if len(original_name) <= 64:
        return original_name
    digest = hashlib.sha256(original_name.encode()).hexdigest()[:8]
    return f"{original_name[:55].rstrip('-')}-{digest}"


def replace_frontmatter_name(content: str, name: str) -> str:
    return re.sub(r"\A---\nname:\s*[^\n]+\n", f"---\nname: {name}\n", content, count=1)


def install_migration_skills() -> list[dict[str, object]]:
    if not MIGRATION_SOURCE.is_dir():
        raise SystemExit(f"Migration skill source is missing: {MIGRATION_SOURCE}")
    records: list[dict[str, object]] = []
    for index, source in enumerate(sorted(MIGRATION_SOURCE.glob("b*/SKILL.md")), start=1):
        name = source.parent.name
        match = re.fullmatch(r"b(29|30|31|32|33|34)-.+", name)
        if not match:
            continue
        batch = int(match.group(1))
        display = f"Migration Pack M{batch} Skill {index:03d}"
        short = f"Run Migration Pack M{batch} certification safely"
        prompt = f"Use ${name} to apply the independent, fail-closed Migration Pack M{batch} contract."
        skill_dir = initialize(name, display, short, prompt)
        content = normalize_frontmatter(source.read_text(encoding="utf-8"))
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
        regenerate_interface(skill_dir, display, short, prompt)
        records.append(
            {
                "family": "migration-pack-certification",
                "batch": f"M{batch}",
                "name": name,
                "source": str(source),
                "sha256": hashlib.sha256(content.encode()).hexdigest(),
            }
        )
    if len(records) != 124:
        raise SystemExit(f"Expected 124 migration skills, materialized {len(records)}")
    return records


def markdown_blocks(lines: list[str], start: int, end: int) -> list[tuple[int, str, str]]:
    result: list[tuple[int, str, str]] = []
    index = start - 1
    while index < end:
        if lines[index].strip() != "```markdown":
            index += 1
            continue
        close = index + 1
        while close < end and lines[close].strip() != "```":
            close += 1
        if close >= end:
            raise SystemExit(f"Unclosed markdown block at line {index + 1}")
        body = "\n".join(lines[index + 1 : close]).rstrip() + "\n"
        match = re.match(r"^---\nname:\s*([^\n]+)\ndescription:", body)
        if match:
            result.append((index + 2, match.group(1).strip(), body))
        index = close + 1
    return result


def install_product_skills() -> list[dict[str, object]]:
    if not PRODUCT_SOURCE.is_file():
        raise SystemExit(f"Product roadmap source is missing: {PRODUCT_SOURCE}")
    lines = PRODUCT_SOURCE.read_text(encoding="utf-8").splitlines()
    selected: dict[str, tuple[int, int, str]] = {}
    for batch, (start, end) in PRODUCT_RANGES.items():
        for line, name, body in markdown_blocks(lines, start, end):
            # v3.2.1 intentionally replaces the earlier, less detailed duplicate.
            selected[name] = (batch, line, normalize_frontmatter(body))
    if len(selected) != 165:
        raise SystemExit(f"Expected 165 unique product skills, extracted {len(selected)}")
    records: list[dict[str, object]] = []
    counters: dict[int, int] = {}
    for original_name, (batch, line, body) in sorted(selected.items(), key=lambda item: item[1][1]):
        counters[batch] = counters.get(batch, 0) + 1
        name = installed_name(original_name)
        body = replace_frontmatter_name(body, name)
        display = f"ELMOS Product Batch {batch} Skill {counters[batch]:03d}"
        short = f"Run ELMOS Product Batch {batch} governance safely"
        prompt = f"Use ${name} to implement its evidence-bound ELMOS Product Batch {batch} contract."
        skill_dir = initialize(name, display, short, prompt)
        (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")
        regenerate_interface(skill_dir, display, short, prompt)
        records.append(
            {
                "family": "elmos-product-roadmap",
                "batch": batch,
                "name": name,
                "source_name": original_name,
                "source_line": line,
                "source": str(PRODUCT_SOURCE),
                "sha256": hashlib.sha256(body.encode()).hexdigest(),
            }
        )
    return records


def write_manifest(records: list[dict[str, object]]) -> None:
    target = ROOT / "docs" / "product-batches27-34" / "skill-source-manifest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "namespace_policy": {
            "migration_package": "M29-M34",
            "product_roadmap": "Batch 27-34",
        },
        "generated_by": "tooling/sync_batch27_34_skills.py",
        "external_execution_evidence": "NOT_RUN",
        "records": records,
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    records = install_migration_skills() + install_product_skills()
    write_manifest(records)
    print(json.dumps({"installed": len(records), "runtime_skill_total": len(list(RUNTIME.glob("*/SKILL.md")))}, indent=2))


if __name__ == "__main__":
    main()
