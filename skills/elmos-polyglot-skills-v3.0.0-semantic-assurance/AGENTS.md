# AGENTS.md — ELMOS Polyglot Skills Execution Rules

## Mission

Implement or execute the selected ELMOS Skill against an authorized immutable snapshot. Produce code, tests, machine-readable artifacts, evidence, and a bounded completion report.

## Loading

1. Read the selected `SKILL.md`.
2. Read its hard dependencies from `manifest.json`.
3. Load only relevant technology adapters and route profile.
4. Read `policies/runner-policy.yaml`, `policies/agent-patch-policy.yaml`, and `policies/readiness-policy.yaml`.
5. Do not load all Skills or unrelated source into context.

## Non-negotiable rules

- Inspect before editing.
- Create or verify the immutable snapshot before analysis.
- Establish baseline build and tests before transformation.
- Use deterministic codemods before bounded AI patches.
- Work only in the authorized worktree and allowed paths.
- Never expose secret values or unrelated private source.
- Do not disable tests, weaken assertions, suppress scanner errors, or fake integrations.
- Do not mark `not-run` or `blocked` checks as passed.
- Do not claim production readiness from file generation.
- Stop on critical semantic loss, unauthorized scope, stale evidence, missing toolchain, or exhausted budget.
- Preserve a checkpoint and return the required Completion Report.

## Editing discipline

- Keep changes scoped to one DAG node.
- Avoid broad formatting and lockfile churn.
- Separate generated from maintained code.
- Record rule/task provenance for every changed file.
- Run focused tests first, then required regression gates.
- Revert candidate patches that violate policy or tests.

## Completion

A Skill is complete only when its Definition of Done and required executed gates are satisfied. Otherwise return `blocked`, `failed`, or `completed-with-approved-exceptions`.


## v3 Semantic Assurance Rule

Before claiming a conversion is equivalent, enumerate applicable semantic obligations and execute the required v3 frontend/type/runtime/behavior/corpus/native-lab/stress/formal gates. Compilation or static validation is insufficient. See `route-certification-registry.json` and `references/e0-e5-certification-standard-v3.md`.
