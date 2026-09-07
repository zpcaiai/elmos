---
name: b46-seed-data-provenance-policy
description: Enforce the three permitted seed data sources, the authorization and scan requirements for desensitized samples, and the absolute prohibition on production data.
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

## Skill 4604: Seed data provenance and desensitization boundary

## Use this skill when

- Anyone proposes seeding a smoke pack from something other than the project's contracts.
- A sample file, export or dump is offered as fixture data.
- A corpus slice is proposed for reuse.

## Risks and invariants

- "Anonymized" exports routinely retain re-identifiable values.
- Reusing a holdout or representative corpus contaminates the independence other batches depend on, invisibly.
- A single permitted exception becomes the default path within a release cycle.

## Workflow

1. Default to `synthetic-from-contract`; require a stated reason for anything else.
2. For `desensitized-sample`, require an authorization reference and run the sensitive-value scan; refuse on findings unless the override is used and the findings are recorded.
3. For `corpus-trim`, confirm the source is a development corpus and record the independence note.
4. Refuse production data outright, regardless of volume, anonymization claim or provenance story.
5. Keep `production_data_used: false` accurate; it is a factual field, not a formality.

## Required outputs

- a `provenance` entry per data source in `smoke/seed-manifest.json`
- authorization references and scan findings recorded where a reviewer will see them

## Verification

- A sample without `--sample-authorization` is rejected.
- A sample containing email-, card-, national-ID-, token- or key-shaped values is refused by default.
- Smoke-shaped values do not trip the scan; real-shaped values do.

## Stop and escalate when

- Someone requests a production-derived seed for any reason.
- A holdout or representative corpus is proposed as a trim source.
