---
name: b46-polyglot-topology-smoke
description: Handle repositories containing several languages or services: one primary entry, declared secondary stacks, one shared lease, and explicit coverage reporting.
---

## Operating mode

Work in the repository. Read the shared Batch 46 contracts before editing:

- `../../../docs/batch46/IMPLEMENTATION_CONTRACT.md`
- `../../../docs/batch46/QUALITY_GATES.md`
- `../../../docs/batch46/MINIMAL_DATA_POLICY.md`
- `../../../docs/batch46/RUNTIME_LEASE_POLICY.md`
- `../../../docs/batch46/STACK_MATRIX.md`

Use the supplied helpers rather than reimplementing them:

- `python3 scripts/batch46/scaffold_smoke_pack.py <project> --write`
- `python3 scripts/batch46/detect_project_profile.py <project> --write`
- `python3 scripts/batch46/derive_minimal_data.py <project> --write`
- `python3 scripts/batch46/synthesize_seed_data.py <project> --write`
- `python3 scripts/batch46/emit_one_click_runner.py <project> --write`
- `python3 scripts/batch46/validate_smoke_pack.py <project>`
- `python3 scripts/batch46/run_smoke_gate.py <project>`

## Global constraints

- A smoke pack proves that a generated artifact starts, answers once, and stops
  cleanly. It is never evidence of route, framework, database, client,
  performance, security or accessibility quality, and no Batch 29-45 gate may
  cite it as an input.
- Minimal means minimal: one row per table unless a declared constraint demands
  more, and no value for a column the schema does not require.
- Production data is never a seed source. Synthetic-from-contract is the default;
  desensitized samples require an authorization reference and pass a
  sensitive-value scan; corpus trimming may touch development corpora only.
- Every entry, substitute, dataset and check is either honestly available or
  explicitly `unavailable` / `NOT_RUN` with a reason. `NOT_RUN` never passes.
- Every run is bounded by the runtime lease. Expiry stops every started service,
  removes containers and volumes, and deletes all ephemeral smoke data.
- If a project needs source edits to start, that is a generator defect. Report it;
  do not patch around it inside `smoke/`.

## Skill 4613: Polyglot repository smoke topology

## Use this skill when

- Detection reports more than one stack in a repository.
- A monorepo or multi-service project needs a single runnable entry.

## Risks and invariants

- Smoke-testing only the primary stack while reporting a whole-repository pass overstates coverage.
- Independent leases leave one service running after another has been reclaimed.
- Competing default ports collide across services.

## Workflow

1. Mark exactly one stack `primary` and declare the others `secondary`.
2. Run every service under one lease so reclamation is atomic.
3. Allocate ports dynamically when defaults collide.
4. Report which stacks were exercised and which were not; unexercised stacks are reduced coverage, not a pass.

## Required outputs

- a `polyglot: true` profile with explicit stack roles
- a coverage statement naming exercised and unexercised stacks

## Verification

- Teardown reclaims every service, not only the primary one.
- The gate reports limited coverage when a secondary stack was not exercised.

## Stop and escalate when

- Two stacks both require the same fixed port and neither can be reconfigured.
