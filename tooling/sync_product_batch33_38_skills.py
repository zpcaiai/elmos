#!/usr/bin/env python3
"""Materialize the ELMOS Product Batch 33-38 runtime Skill family.

The repository also contains Migration Pack M35-M45 skills under `.agents`.
This importer deliberately uses the product Skill names from the commercial
roadmap and records the separate namespace in a generated manifest.
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
SOURCE = Path("/Users/stephen/Downloads/ChatGPT-Git项目商业化模式 (2).md")
SKILL_CREATOR = Path("/Users/stephen/.codex/skills/.system/skill-creator/scripts")
INIT_SKILL = SKILL_CREATOR / "init_skill.py"
GENERATE_YAML = SKILL_CREATOR / "generate_openai_yaml.py"

PRODUCT_RANGES = {
    "33-core": (1, 2582),
    "33-mature": (2583, 7163),
    "34": (7164, 18802),
    "35": (18803, 33011),
    "36": (33012, 50999),
    "37A": (51000, 56069),
    "37B": (56070, 60204),
    "37C": (60205, 64415),
    "38A": (64416, 68760),
}


def run(*args: str) -> None:
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL)


def installed_name(original_name: str) -> str:
    if len(original_name) <= 64:
        return original_name
    digest = hashlib.sha256(original_name.encode()).hexdigest()[:8]
    return f"{original_name[:55].rstrip('-')}-{digest}"


def normalize_frontmatter(content: str, name: str) -> str:
    match = re.match(
        r"^---\nname:\s*([^\n]+)\ndescription:\s*([^\n]+)\n---\n",
        content,
    )
    if not match:
        raise SystemExit(f"Invalid Skill frontmatter for {name}")
    description = match.group(2).strip()
    if len(description) >= 2 and description[0] == description[-1] and description[0] in "\"'":
        description = description[1:-1]
    header = f"---\nname: {name}\ndescription: {json.dumps(description, ensure_ascii=False)}\n---\n"
    return header + content[match.end() :]


def markdown_blocks(
    lines: list[str], start: int, end: int
) -> list[tuple[int, str, str]]:
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


def initialize(
    name: str, display_name: str, short_description: str, default_prompt: str
) -> Path:
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


def regenerate_interface(
    skill_dir: Path,
    display_name: str,
    short_description: str,
    default_prompt: str,
) -> None:
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


def main() -> None:
    if not SOURCE.is_file():
        raise SystemExit(f"Product roadmap source is missing: {SOURCE}")
    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    selected: dict[str, tuple[str, int, str]] = {}
    for batch, (start, end) in PRODUCT_RANGES.items():
        for line, original_name, body in markdown_blocks(lines, start, end):
            # The later mature Batch 33 definition intentionally supersedes a
            # duplicate lease/reconciliation Skill from the initial slice.
            selected[original_name] = (batch, line, body)
    if len(selected) != 208:
        raise SystemExit(f"Expected 208 unique Skills, extracted {len(selected)}")

    counters: dict[str, int] = {}
    records: list[dict[str, object]] = []
    for original_name, (batch, line, raw_body) in sorted(
        selected.items(), key=lambda item: item[1][1]
    ):
        counters[batch] = counters.get(batch, 0) + 1
        name = installed_name(original_name)
        body = normalize_frontmatter(raw_body, name)
        display = f"ELMOS Product Batch {batch} Skill {counters[batch]:03d}"
        short = f"Run Product Batch {batch} evidence contract safely"
        prompt = f"Use ${name} to implement its fail-closed ELMOS Product Batch {batch} contract."
        skill_dir = initialize(name, display, short, prompt)
        (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")
        regenerate_interface(skill_dir, display, short, prompt)
        records.append(
            {
                "family": "elmos-product-commercialization",
                "batch": batch,
                "name": name,
                "source_name": original_name,
                "source_line": line,
                "sha256": hashlib.sha256(body.encode()).hexdigest(),
            }
        )

    manifest = ROOT / "docs" / "product-batches33-38" / "skill-source-manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "namespace_policy": {
            "product_commercialization": "Product Batch 33-38",
            "migration_pack": "M35-M45",
        },
        "source": str(SOURCE),
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "generated_by": "tooling/sync_product_batch33_38_skills.py",
        "external_execution_evidence": "NOT_RUN",
        "records": records,
    }
    manifest.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "installed_or_updated": len(records),
                "runtime_skill_total": len(list(RUNTIME.glob("*/SKILL.md"))),
                "by_batch": counters,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    complete_overlay = ROOT / "tooling" / "integrate_product_batch34_38_complete_skill_packs.py"
    if complete_overlay.is_file():
        # The submitted complete B34-B38 packs are the authoritative definitions
        # for overlapping names. Reapply them so rerunning this legacy extractor
        # cannot silently restore superseded Skill contracts.
        subprocess.run([sys.executable, str(complete_overlay)], check=True)
    batch39_overlay = ROOT / "tooling" / "integrate_product_batch39_complete_skill_pack.py"
    if batch39_overlay.is_file():
        # Product B39 is a separate finance namespace layered after the legacy
        # B33-B38 extractor; reapply it so a full sync remains reproducible.
        subprocess.run([sys.executable, str(batch39_overlay)], check=True)


if __name__ == "__main__":
    main()
