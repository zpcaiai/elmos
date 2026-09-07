# Agent Instructions

- Discover Skills under `agent-skills/runtime/*/SKILL.md`.
- Start with the Master Skill, then invoke Batch Skills in dependency order.
- Execute the shared `scripts/migration_platform.py`; do not satisfy a Skill with prose-only output.
- Record each required output/test with `record`, require another actor to run `verify`, and use the runtime gate as the only local Batch decision.
- Treat `LOCAL_TOOLKIT_PASS` as the local ceiling. This distribution ships no trust key and keeps certificate request/import disabled; `CERTIFIED` is unavailable.
- Do not claim runtime or production validation from static package validation.
- Preserve immutable Evidence and all failed attempts.
- Do not use an LLM as final Oracle, Proof Checker or Certificate Authority.
