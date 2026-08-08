---
name: b46-minimal-runtime-data-analyzer
description: Derive the smallest environment, dataset and stub set a generated project needs to reach readiness and serve one request, from its own DDL, API contract and environment templates.
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

## Skill 4602: Minimal runtime data analysis

## Use this skill when

- Building or refreshing a smoke pack for any project.
- A start attempt fails on a missing environment value or an empty table.
- A schema, migration or API contract changed.

## Risks and invariants

- Over-deriving turns a smoke pack into a test corpus and hides which data the project actually requires.
- Under-deriving produces a pack that fails on a constraint the recipient then has to debug.
- Silently defaulting an unresolvable value hides a real contract gap.

## Workflow

1. Parse DDL into typed columns: nullability, primary keys, uniqueness, defaults, identity, foreign keys.
2. Order tables by foreign-key dependency; keep declaration order for cycles and flag them.
3. Mark a column required only when the schema demands a value.
4. Extract environment variables from the project's own templates and configuration; flag credential-shaped names.
5. Select candidate functional endpoints from the API contract, excluding the readiness path.
6. Write every unmapped type, unparsed schema and unresolved variable to `unsupported` or `unknown`.

## Required outputs

- `smoke/minimal-data-requirements.json` with `environment`, `datasets`, `stub_upstreams`, `ports`, `candidate_smoke_endpoints`
- an explicit `unsupported` and `unknown` inventory
- a requirements digest bound to the profile digest it was derived from

## Verification

- Nullable unconstrained columns do not appear in `required_columns`.
- Child tables sort after their parents.
- A schema file that parses to zero tables is reported, not ignored.

## Stop and escalate when

- The DDL cannot be parsed and the datastore engine is unknown.
- A required environment value has no contract source and no safe synthetic form.
