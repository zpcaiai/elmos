#!/usr/bin/env python3
"""Normalize all Skill contracts and generate their Codex UI interfaces.

This is intentionally deterministic and may be rerun after contract changes.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GENERATOR = Path.home() / ".codex" / "skills" / ".system" / "skill-creator" / "scripts" / "generate_openai_yaml.py"


def load_manifest() -> dict:
    return json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))


def description_from(frontmatter: str) -> str:
    match = re.search(r"^description:\s*(.*)$", frontmatter, re.M)
    if not match:
        raise ValueError("description missing")
    first = match.group(1).strip()
    if first in {">", ">-", "|", "|-"}:
        trailing = frontmatter[match.end():]
        lines = []
        for line in trailing.splitlines():
            if not line.strip():
                continue
            if not line.startswith((" ", "\t")):
                break
            lines.append(line.strip())
        return " ".join(lines)
    return first.strip('"\'')


def runtime_section(batch: int | None) -> str:
    if batch is None:
        return """## Executable Runtime

1. Resolve the shared runtime installed by `install.sh`, or use the package-local `scripts/migration_platform.py`.
2. Prepare all work units without claiming completion:

   ```bash
   python3 "$RMP_RUNTIME" prepare-all --source "$SOURCE_REPO" --workspace "$EVIDENCE_WORKSPACE" --target-objective "$TARGET_OBJECTIVE"
   ```

3. Fill each generated `execution-plan.json` with exact argv-only steps and run it with `execute-plan`; import separately produced subject bytes with `ingest-artifact` before recording typed Evidence.
4. Record and independently verify the exact output/test evidence requested by each Batch profile.
5. Evaluate every local gate in dependency order:

   ```bash
   python3 "$RMP_RUNTIME" gate-all --workspace "$EVIDENCE_WORKSPACE" --mode local
   ```

6. Treat `LOCAL_TOOLKIT_PASS` as the absolute local ceiling. The distributed trust policy disables certificate requests/imports; production or certification states remain `NOT_RUN` until an independently governed distribution supplies a pinned trust root.
"""
    return f"""## Executable Runtime

1. Resolve the shared runtime installed by `install.sh`, or use the package-local `scripts/migration_platform.py`.
2. Discover this Batch against an immutable Source fingerprint:

   ```bash
   python3 "$RMP_RUNTIME" prepare --batch {batch} --source "$SOURCE_REPO" --workspace "$EVIDENCE_WORKSPACE" --target-objective "$TARGET_OBJECTIVE"
   ```

3. Read `batches/batch-{batch:02d}/profile.json`, `implementation-plan.json`, and `execution-plan.json`; implement each required output and populate exact argv-only execution steps.
4. Run the source-bound plan with `execute-plan`. For evidence created outside the runner, first call `ingest-artifact`, then bind its returned digest/bytes in a typed Evidence envelope passed to `record`.
5. Have a different actor execute `verify`; one subject may not satisfy distinct claims.
6. Evaluate the fail-closed gate:

   ```bash
   python3 "$RMP_RUNTIME" gate --workspace "$EVIDENCE_WORKSPACE" --batch {batch} --mode local
   ```

7. Treat `LOCAL_TOOLKIT_PASS` as the local ceiling. The distributed package keeps certificate requests/imports disabled because it ships no independent trust root; never relabel local discovery as runtime, production, or certified evidence.
"""


def normalize_skill(entry: dict) -> Path:
    path = ROOT / entry["path"]
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not match:
        raise ValueError(f"invalid frontmatter: {path}")
    current_description = description_from(match.group(1))
    trigger = (
        "Use when orchestrating the complete Batch 1-38 repository migration lifecycle, "
        "executing all Batch work units, or evaluating final assurance."
        if entry["batch"] is None
        else f"Use when implementing, debugging, or evaluating Batch {entry['batch']} of an evidence-governed repository migration."
    )
    if "Use when" not in current_description:
        current_description = f"{current_description} {trigger}"
    frontmatter = f"---\nname: {entry['name']}\ndescription: >-\n  {current_description}\n---\n"
    body = text[match.end():]
    body = re.sub(r"\n## Use When\n.*?(?=\n## )", "", body, flags=re.S)
    body = body.replace(
        "status: PASS | FAIL | PARTIAL | BLOCKED",
        "status: NOT_RUN | PASS | FAIL | PARTIAL | INCONCLUSIVE | BLOCKED",
    )
    body = re.sub(r"(?m)^- Version: `[^`]+`$", "- Version: `2.0.0`", body)
    if "## Contract Metadata" not in body:
        first_heading_end = body.find("\n", body.find("# "))
        batch_value = "master" if entry["batch"] is None else str(entry["batch"])
        risk = "critical" if entry["batch"] is None or entry["batch"] >= 12 else "high"
        metadata = f"\n\n## Contract Metadata\n\n- Version: `2.0.0`\n- Batch: `{batch_value}`\n- Risk: `{risk}`\n- Gate: `{entry['gate']}`\n"
        body = body[:first_heading_end] + metadata + body[first_heading_end:]
    executable = runtime_section(entry["batch"])
    existing = re.search(r"\n## Executable Runtime\n.*?(?=\n## )", body, re.S)
    if existing:
        body = body[:existing.start()] + "\n" + executable.rstrip() + body[existing.end():]
    else:
        marker = "\n## Definition of Done"
        position = body.find(marker)
        if position < 0:
            position = len(body)
        body = body[:position] + "\n\n" + executable.rstrip() + "\n" + body[position:]
    path.write_text(frontmatter + body, encoding="utf-8")
    return path.parent


def generate_interface(skill_dir: Path, name: str, generator: Path) -> None:
    prompt = (
        f"Use ${name} to execute its evidence-governed repository migration workflow and report every unmet gate explicitly."
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(generator),
            str(skill_dir),
            "--name",
            name,
            "--interface",
            f"default_prompt={prompt}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"interface generation failed for {name}: {completed.stdout}{completed.stderr}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generator", type=Path, default=DEFAULT_GENERATOR)
    args = parser.parse_args()
    if not args.generator.is_file():
        raise SystemExit(f"Skill interface generator not found: {args.generator}")
    entries = load_manifest()["skills"]
    for entry in entries:
        skill_dir = normalize_skill(entry)
        generate_interface(skill_dir, entry["name"], args.generator)
    print(f"Synchronized {len(entries)} Skill contracts and interfaces")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
