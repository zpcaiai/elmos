---
name: b46-ephemeral-data-isolation-teardown
description: Keep smoke data confined to a throwaway topology: loopback-only binds, ephemeral volumes, reserved-range keys, and deletion at lease end — never a write to a shared or production store.
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

## Skill 4608: Ephemeral data isolation and teardown

## Use this skill when

- A pack is being wired to a datastore, queue or cache.
- A recipient runs a smoke test on a machine that also has real services.
- Seed data is suspected to have escaped its lease.

## Risks and invariants

- A connection string inherited from a template can point at a shared database.
- Port collisions can attach the run to a service the operator already had running.
- Fixture keys drawn from the application's own range collide with real rows.

## Workflow

1. Bind every smoke service to loopback and allocate a free port when the default is busy.
2. Override connection-shaped variables per entry; leave `script` unoverridden and state that it uses whatever the operator already has.
3. Keep compose datastores on ephemeral volumes and remove them with `down -v`.
4. Keep seed keys in the reserved range so a fixture row can never be mistaken for, or collide with, a real one.
5. Delete every tracked ephemeral path at lease end and verify the deletion.
6. Tell the recipient plainly, in `smoke/README.md`, never to load the seed into a shared or production database.

## Required outputs

- `smoke/seed/runtime-overrides.json` with per-entry connection values
- ephemeral volume and path tracking in the lease
- a verified teardown report

## Verification

- No smoke service binds to a non-loopback interface.
- The zero-dependency datastore file is gone after the run.
- No override resolves to a host or database the operator did not create for this run.

## Stop and escalate when

- A project hard-codes a connection target that cannot be overridden.
- A datastore cannot be run ephemerally and no substitute is approved.
