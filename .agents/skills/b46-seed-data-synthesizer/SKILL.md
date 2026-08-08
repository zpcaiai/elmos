---
name: b46-seed-data-synthesizer
description: Generate deterministic, obviously-fake, constraint-satisfying seed data from a project's own contracts, with reserved-range keys and a per-artifact provenance record.
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

## Skill 4603: Disposable seed data synthesis

## Use this skill when

- Minimal data requirements exist and a pack needs its fixtures.
- A schema change invalidated existing seeds.
- A recipient needs a functional endpoint to return something.

## Risks and invariants

- Fixture data that looks real gets mistaken for real, and then gets kept.
- Keys drawn from the application's own range collide with rows the app creates at run time.
- Non-portable literals pass on one engine and fail on another.

## Workflow

1. Seed deterministically from the requirements digest unless an explicit seed is supplied.
2. Emit one row per table in dependency order, resolving foreign keys to the parent row actually emitted.
3. Allocate primary keys from the reserved range at or above 900,000,000 and emit them explicitly where a child references them.
4. Use portable literals that PostgreSQL, MySQL, SQL Server, SQLite and H2 all accept.
5. Generate throwaway values for credential-shaped variables; never reuse a contract placeholder.
6. Record each artifact's data-source class, classification and digest in the seed manifest.

## Required outputs

- `smoke/seed/seed.sql`, `api-fixtures.json`, `env.smoke`, `runtime-overrides.json`
- `smoke/seed-manifest.json` with `production_data_used: false` and per-artifact provenance

## Verification

- Every generated string carries a `SMOKE-`, `smoke-` or `smoke.invalid` marker.
- Foreign key values match an emitted parent key, not a random integer.
- Re-running with the same seed produces byte-identical files.

## Stop and escalate when

- A constraint cannot be satisfied synthetically, for example a check constraint over an opaque encoding.
- A required column has a type the mapper cannot represent.
