---
name: b46-b31-database-seed-smoke
description: Seed database and data-platform migration outputs with minimal dependency-ordered rows in an ephemeral engine, without touching a shared store and without hiding dialect loss.
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

## Skill 4611: B31 database pack smoke seeding

## Use this skill when

- A b31 pack produced schema, routines or migration artifacts.
- A target schema changed.

## Risks and invariants

- A seed that succeeds on SQLite and fails on the declared engine creates false confidence.
- Direct row counts against a shared engine can read someone else's data.
- Unmapped types quietly become string literals.

## Workflow

1. Derive rows from the target DDL and load them in foreign-key order.
2. Prefer the compose entry with the declared engine; treat zero-dependency substitution as reduced coverage.
3. Read row counts only from the ephemeral store; assert through the service otherwise.
4. Record every unmapped type as `unsupported` so the gate downgrades the result.
5. Verify the ephemeral volume is removed at lease end.

## Required outputs

- dependency-ordered `seed.sql` with reserved-range keys
- an `unsupported` inventory of unmapped types and unparsed statements

## Verification

- Child rows reference parent rows that were actually inserted.
- A cycle in the foreign-key graph is flagged, not silently reordered.

## Stop and escalate when

- The declared engine cannot be run ephemerally and no substitute is approved.
- The DDL depends on engine features the seed cannot satisfy.
