---
name: elmos-auto-skill-router
implementation_state: "VERIFIED"
external_evidence_status: "LOCAL_EXECUTED"
production_certification: "NOT_CERTIFIED"
description: Automatically discover, route, and compose all materially relevant Antigravity skills for engineering tasks in the current project. Use when selecting skills, continuing prior work, coordinating multiple skills, refreshing the skill index, or when the user expects skills to be selected automatically without explicitly naming them.
---

# Elmos Auto Skill Router

## Purpose

Make installed skills automatically usable without forcing the user to write `Use the X skill` every turn.

This skill implements **automatic discovery + routing + composition**, not unconditional full-context loading.

## Required routing behavior

1. Read `.agents/skills-index.json` if available.
2. If the index is missing/stale and command execution is permitted, run:

```bash
python3 .agents/skills/elmos-auto-skill-router/scripts/refresh_skill_index.py --root .
```

3. Identify all materially relevant skills for the task.
4. Load/use the relevant subset, with project-scoped skills preferred over global duplicates.
5. Apply mandatory routing rules from `.elmos/skill-router.json`.
6. Compose multiple skills when their scopes overlap.
7. Do not ask the user to name a skill when repository context is sufficient.
8. Preserve progressive disclosure; do not indiscriminately read every SKILL.md body.

## Continue protocol

For a request such as `continue`, `继续`, `next`, or `继续实现`:

1. Inspect `.elmos/`, work-package/progress files, git diff/status, TODOs, and current subsystem artifacts.
2. Infer the active workstream.
3. Route relevant skills for that workstream.
4. Continue the current incomplete work or next dependency-ready work package.
5. Execute real validation before claiming completion.

Use:

```bash
.agents/skills/elmos-auto-skill-router/scripts/continue-with-skills.sh .
```

for a generated prompt, or add `--run` when Antigravity CLI (`agy`) is available and the user wants direct execution.

## Mandatory trust rule

If the task involves authoritative tests, evidence, certification, verification gates, hidden tests, mutation/sabotage testing, attestation, or release/deployment authorization, use `elmos-proof-driven-certification` when installed.

Skill routing metadata and index files are never authoritative execution evidence.

## Useful scripts

- `scripts/refresh_skill_index.py`: scan project and global skill roots and write `.agents/skills-index.json`.
- `scripts/route_skills.py`: deterministic local task-to-skill ranking and mandatory-rule enforcement.
- `scripts/continue-with-skills.sh`: generate or run an Antigravity continuation prompt.
- `scripts/check_install.sh`: validate installation and run a routing smoke test.

See `references/routing-model.md` for details.
