---
name: b46-b32-client-smoke
description: Make modernized clients runnable with a deterministic API stub and minimal page data, so a reviewer sees a rendered screen instead of a blank error state.
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

## Skill 4612: B32 client pack smoke

## Use this skill when

- A b32 client pack produced a frontend or desktop application.
- A client's API contract or dev server changed.

## Risks and invariants

- A dev server that starts and renders an error boundary passes a naive port check.
- A stub built from guessed shapes produces a screen that does not match the real contract.
- Client smoke evidence gets mistaken for accessibility or visual evidence.

## Workflow

1. Build the API stub from the project's own contract; keep responses deterministic.
2. Point the client at the stub through its declared configuration, not by editing source.
3. Use the dev server root for readiness and a declared route for the functional check.
4. State explicitly that the run is not accessibility, visual, cross-browser or i18n evidence.

## Required outputs

- `smoke/seed/api-fixtures.json` derived from the project's contract
- a client-appropriate assertion set with an explicit `not_evidence_for` list

## Verification

- The stub responds to every route the functional check exercises.
- Readiness fails when the dev server serves an error page.

## Stop and escalate when

- The client requires an authenticated upstream that cannot be stubbed deterministically.
