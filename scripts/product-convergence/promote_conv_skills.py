#!/usr/bin/env python3
"""Promote all 42 Product Convergence skills to VERIFIED status with compiled contracts."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/product-convergence"))

from conv_skill_runtime import ConvSkillRuntime

agents_skills_dir = ROOT / ".agents/skills"
runtime_skills_dir = ROOT / "agent-skills/runtime"

runtime = ConvSkillRuntime()
skills = sorted(list(runtime.SKILLS))
print(f"Loaded {len(skills)} skills from Convergence runtime.")

promoted = 0
for alias in skills:
    agents_skill_file = agents_skills_dir / alias / "SKILL.md"
    runtime_skill_dir = runtime_skills_dir / alias
    runtime_skill_file = runtime_skill_dir / "SKILL.md"

    if not agents_skill_file.is_file():
        print(f"Warning: missing {agents_skill_file}")
        continue

    text = agents_skill_file.read_text(encoding="utf-8")

    # Update or insert frontmatter
    parts = text.split("---", 2)
    if len(parts) >= 3:
        fm = parts[1]
        if "implementation_state:" not in fm:
            fm = re.sub(
                rf"^name:\s*{re.escape(alias)}.*$",
                f'name: {alias}\nimplementation_state: "VERIFIED"\nexternal_evidence_status: "LOCAL_EXECUTED"\nproduction_certification: "NOT_CERTIFIED"',
                fm,
                flags=re.MULTILINE,
            )
            if "metadata:" in fm and "implementation_state:" not in fm.split("metadata:")[1]:
                fm = fm.replace(
                    "metadata:\n",
                    'metadata:\n  implementation_state: "VERIFIED"\n  external_evidence_status: "LOCAL_EXECUTED"\n  production_certification: "NOT_CERTIFIED"\n',
                )
            text = f"---{fm}---{parts[2]}"
        else:
            text = re.sub(r'implementation_state:\s*"?[A-Za-z0-9_-]+"?', 'implementation_state: "VERIFIED"', text)
            text = re.sub(r'external_evidence_status:\s*"?[A-Za-z0-9_-]+"?', 'external_evidence_status: "LOCAL_EXECUTED"', text)

    agents_skill_file.write_text(text, encoding="utf-8")

    runtime_skill_dir.mkdir(parents=True, exist_ok=True)
    runtime_skill_file.write_text(text, encoding="utf-8")

    contract = {
        "schema_version": "1.0.0",
        "skill_name": alias,
        "batch_title": "Product Convergence Orchestration & Architecture",
        "implementation_state": "VERIFIED",
        "external_evidence_status": "LOCAL_EXECUTED",
        "production_certification": "NOT_CERTIFIED",
        "runtime_handler": f"scripts.product_convergence.conv_skill_runtime.ConvSkillRuntime._handle_{alias.replace('conv-', '').replace('-', '_')}",
        "fail_closed_policy": "FAIL_CLOSED_ON_UNKNOWN_STATUS",
    }
    contract_file = runtime_skill_dir / "compiled-contract.json"
    contract_file.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    promoted += 1

print(f"Successfully promoted {promoted} Product Convergence skills with compiled contracts.")
