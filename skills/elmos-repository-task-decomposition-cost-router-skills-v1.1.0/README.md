# Elmos Repository Task Decomposition + Cost/Performance Model Routing Skills Package

Version: **1.1.0**  
Purpose: turn a medium/large complex repository-level requirement into a dependency-aware DAG of lower-complexity atomic tasks, route each task to the most cost-effective model from an immutable 10-model allowlist, execute in isolated worktrees, validate incrementally, integrate safely, and certify the complete repository change.

## Hard model allowlist

No skill, policy, retry path, reviewer, or fallback may invoke a model outside these aliases:

1. `gpt-5.6-sol-max`
2. `claude-opus-5-max`
3. `claude-fable-5`
4. `grok-4.6`
5. `kimi-k3-max`
6. `glm-5.3-max`
7. `qwen3.8-max`
8. `deepseek-v4-pro-0813`
9. `gemini-3.7-flash-high`
10. `claude-sonnet-5`

Provider model IDs can be mapped in `config/model-registry.yaml`, but the logical aliases above are immutable. `scripts/validate_package.py` fails if an unknown alias is introduced.


## User-selectable execution model

Before a run starts, the Elmos page MUST offer two top-level choices:

- **Smart — Best value per task (recommended):** Elmos independently routes every atomic task to the best-value eligible model from the ten-model allowlist.
- **Choose model:** the user selects one of the same ten models for primary implementation calls. Manual mode defaults to strict (no silent model switching), with an explicit optional `Allow intelligent fallback if this model fails` toggle that may switch only inside the ten-model allowlist.

Mandatory security/budget/deterministic gates remain active in both modes. By default, mandatory independent verification may use a different allowlisted verifier even when implementation is manually pinned. The full contract is in `skills/36-model-selection-controller/SKILL.md`, `config/model-selection-policy.yaml`, `schemas/model-selection.schema.json`, and `docs/model-selection-ui.md`.

## Design principles

- **Decompose before routing.** Expensive models should solve architecture, high-risk semantics, difficult failures and final certification—not routine leaf tasks.
- **Atomic does not mean low risk.** Small tasks touching auth, transactions, concurrency, migrations, public contracts or security are automatically promoted.
- **Optimize expected completed-task cost, not token sticker price.** Routing considers predicted success probability, retries, escalation cost, integration risk, context size and wall-clock latency.
- **Compiler/tests are cheaper than model review.** Deterministic validators run before a second model is called.
- **One owner per write path per wave.** Atomic tasks declare `owned_paths`; conflicting writes cannot execute concurrently.
- **Patch isolation first.** Every task executes in a branch/worktree; no worker commits directly to the integration branch.
- **Fail upward, not sideways forever.** A bounded retry policy escalates models according to failure type.
- **Repository-level completion is a separate gate.** Passing leaf tests does not imply the whole requirement is done.
- **State is durable.** Plans, prompts, patches, test evidence, model telemetry and run state are persisted under `.elmos/runs/<run_id>/` so an interrupted run can resume.

## Default routing strategy

The policy intentionally avoids hard-coding vendor marketing benchmarks or permanent prices. Live price/latency data can be populated in the registry, while capability priors are continuously recalibrated from Elmos telemetry.

- **Tier L0 — deterministic/simple:** `gemini-3.7-flash-high`, `glm-5.3-max`, `qwen3.8-max`
- **Tier L1 — standard implementation:** `kimi-k3-max`, `grok-4.6`, `deepseek-v4-pro-0813`, `claude-sonnet-5`
- **Tier L2 — complex/debug/integration:** `grok-4.6`, `kimi-k3-max`, `claude-sonnet-5`, `gpt-5.6-sol-max`
- **Tier L3 — architect/critical verifier:** `gpt-5.6-sol-max`, `claude-opus-5-max`
- **Tier L4 — long-horizon migration:** `claude-fable-5`, with `claude-opus-5-max` / `gpt-5.6-sol-max` as verifier

The router searches the cheapest eligible tier first, but only after risk gates are applied.

## End-to-end lifecycle

`requirement -> repo intake -> architecture index -> impact map -> decomposition -> atomicity check -> DAG -> contracts -> complexity/risk -> context slicing -> model routing -> budget/ETA -> worktree execution -> deterministic validation -> retry/escalation -> review -> integration -> full regression -> repository certification -> telemetry learning`

## Package layout

- `skills/` — 37 implementation-ready skills
- `config/` — fixed allowlist, routing policy, gates and budgets
- `schemas/` — task, DAG, execution and evidence contracts
- `examples/` — example repository-level workflow and task plan
- `scripts/` — allowlist/policy validator and routing simulator
- `tests/` — package integrity tests
- `docs/` — architecture, routing formula and rollout guidance
- `AGENTS.md` — Codex integration instructions
- `CLAUDE.md` — Claude Code integration instructions

## Quick start

1. Copy this package into the Elmos repository (recommended under `.elmos/skills-package/`).
2. Map each logical model alias to the provider/CLI model ID you actually use in `config/model-registry.yaml`.
3. Populate live prices/quotas if available; otherwise use subscription/credit normalized cost units.
4. Implement the page/API model selector using `skills/36-model-selection-controller/SKILL.md`; default new runs to Smart mode.
5. Run `python scripts/validate_package.py`.
6. Invoke `skills/00-repository-orchestrator/SKILL.md` as the entry skill.
7. Persist all run artifacts under `.elmos/runs/<run_id>/`.

## Definition of done

A run is complete only when:

- every required task is `passed` or explicitly waived with evidence;
- dependency and path-ownership rules were respected;
- build/lint/type-check/unit/integration/contract tests pass as applicable;
- repository-level acceptance scenarios pass;
- security/data-migration/API compatibility gates pass when triggered;
- final repository certification records the requirement-to-evidence traceability matrix;
- budget, autonomous wall-clock runtime and model usage are reported.
