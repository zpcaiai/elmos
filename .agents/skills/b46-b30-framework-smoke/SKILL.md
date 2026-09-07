---
name: b46-b30-framework-smoke
description: Give framework migration and upgrade outputs a one-click run using the framework's own readiness contract, dependency install and configuration seeding.
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

## Skill 4610: B30 framework pack smoke

## Use this skill when

- A b30 framework pack produced a target application.
- A framework or framework version changed.

## Risks and invariants

- Guessing a readiness path produces a check that passes on a 404 handler.
- Skipping dependency install makes the pack unrunnable on a clean machine.
- Framework configuration seeded from the wrong profile starts a different application than intended.

## Workflow

1. Take the readiness path from the framework's contract: actuator, `q/health/ready`, or the declared endpoint.
2. Run the framework's real install and start commands; allow the recipient to skip install explicitly.
3. Seed framework configuration from the project's own profile files, not from a template.
4. Keep the readiness accept-status list tight; a 404 is not readiness.

## Required outputs

- a framework-aware assertion set and readiness path
- an install step the recipient can skip but not silently lose

## Verification

- The readiness check fails when the application is up but the health endpoint is not.
- Install failure is reported as a failure, not skipped.

## Stop and escalate when

- The framework's readiness contract is ambiguous in the target version.
