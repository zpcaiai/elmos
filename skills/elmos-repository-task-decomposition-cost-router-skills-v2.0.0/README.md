# Elmos Adaptive Repository Task Decomposition + Cost/Performance Routing Skills Package

Version: **2.0.0**

Purpose: turn a medium/large complex repository requirement into a **self-adaptive hierarchical plan**, recover implicit repository requirements, build evidence-backed architecture/behavior graphs, progressively refine work into safe executable leaves, route each leaf to the best-value model from an immutable 10-model allowlist, dynamically replan when runtime evidence changes assumptions, integrate through validated handoffs, and certify the complete repository change.

## What changed from v1.1

v1.1 used a strong static pipeline: impact map -> atomic tasks -> DAG. v2 changes the planner itself:

- **Coarse-to-fine planning:** `goal -> capability -> changeset -> atomic_task -> microstep`.
- **Lazy refinement:** refine only ready/high-risk branches instead of generating hundreds of leaves up front.
- **Implicit requirement recovery:** mine tests, APIs, schemas, sibling code, examples, build/CI rules before planning.
- **Behavior-first planning:** keep an end-to-end scenario graph separate from the file/task graph.
- **Repository Intelligence Graph:** typed evidence-backed build/test/runtime/data relationships.
- **Architecture invariant ledger:** transactions, compatibility, auth, concurrency, idempotency and other invariants survive decomposition.
- **Adaptive granularity:** split/merge based on cohesion, coupling, context, invariant density, verifier locality and uncertainty.
- **Plan graph verification:** deterministic cycle/coverage/contract/ownership checks before execution.
- **Validated handoffs:** downstream tasks unlock only after dependency-edge validators pass.
- **Uncertainty probes:** bounded exploration tasks resolve unknowns rather than embedding guesses.
- **Dynamic replanning:** local graph edits when runtime evidence invalidates the original plan.
- **Semantic conflict detection:** catches logically incompatible patches even when git merges cleanly.
- **Critical-path resource scheduling:** model/provider capacity and integration barriers are part of scheduling.
- **Baseline/golden snapshots:** distinguish regressions from pre-existing failures.
- **Plan revision journal:** every split/merge/replan is explainable and replayable.
- **Decomposition telemetry learning:** Elmos learns which task sizes and seams actually work in each repository.

## Hard model allowlist

No skill, policy, retry path, reviewer, fallback or replanner may invoke a model outside these aliases:

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

Provider IDs can be mapped in `config/model-registry.yaml`; logical aliases are immutable.

## User-selectable model execution

The existing UI contract remains:

- **Smart** — system selects the best-value eligible model per executable task.
- **Choose model** — user pins one of the ten models. Strict is default; optional smart fallback may switch only within the same allowlist.

The decomposition planner is independent from this choice. Manual model selection does not disable architecture/risk/proof gates.

## The new decomposition principle

**Do not optimize for smallest tasks. Optimize for the cheapest safe unit that preserves semantics and can be verified.**

A task may remain relatively large when it is highly cohesive and locally verifiable. Conversely, a small task may require a stronger model/reviewer when it touches high-risk invariants.

## Three planning graphs

1. **Behavioral Scenario Graph** — what end-to-end behavior must be true.
2. **Repository Intelligence Graph** — how code/build/test/data/runtime surfaces actually relate.
3. **Typed Execution DAG** — what executable leaves can run now and how validated handoffs connect them.

This prevents the common failure mode of decomposing a product behavior solely by directory/file boundaries.

## End-to-end lifecycle

`requirement -> explicit normalization -> repo intake -> architecture/RIG -> implicit requirements -> behavioral scenarios -> invariants -> impact/confidence -> exploration -> baseline -> semantic seams -> hierarchical plan -> adaptive split/merge -> contracts/proofs -> typed DAG -> graph verification -> routing/budget/ETA -> critical-path scheduling -> isolated execution -> validation -> integration/checkpoints -> semantic conflicts/regression -> dynamic replan as needed -> repository certification -> routing/decomposition learning`

## Package layout

- `skills/` — **54** implementation-ready skills
- `config/` — model allowlist, routing/budget/gates and adaptive decomposition policy
- `schemas/` — task/DAG plus hierarchical plan, scenario graph, RIG, invariants, proofs and plan revisions
- `reference_planner/` — dependency-free deterministic planning utilities
- `examples/` — adaptive hierarchical plan and full workflow
- `scripts/` — package validator, routing simulator and decomposition simulator
- `tests/` — allowlist/model-selection/adaptive-planner tests
- `docs/` — architecture, routing, rollout and adaptive decomposition design

## Quick start

1. Copy the package into Elmos, e.g. `.elmos/skills-package/`.
2. Map the ten logical models in `config/model-registry.yaml`.
3. Review `config/adaptive-decomposition-policy.yaml` for repository-specific thresholds.
4. Run `python scripts/validate_package.py`.
5. Run `python scripts/simulate_decomposition.py` to test deterministic graph/granularity logic.
6. Invoke `skills/00-repository-orchestrator/SKILL.md` as the entry skill.
7. Persist run artifacts under `.elmos/runs/<run_id>/`.

## Definition of done

A run is complete only when:

- explicit and evidence-backed implicit requirements are traceable to scenarios;
- all critical scenarios/invariants have proof obligations and evidence;
- every executed task references a valid plan revision;
- all nontrivial task edges have validated handoffs;
- no unresolved semantic integration conflict remains;
- clean build/lint/type-check/tests and repository-level acceptance pass as applicable;
- security/data/API/concurrency gates pass when triggered;
- no unexplained diff or invalidated evidence remains;
- cost, autonomous runtime, model usage, replans and decomposition quality metrics are reported.
