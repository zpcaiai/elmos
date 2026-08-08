---
name: b46-smoke-assertion-design
description: Define what passing means for a specific project: process, port, readiness, one contract-declared functional call against seeded data, graceful shutdown and lease teardown.
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

## Skill 4606: Functional smoke assertion design

## Use this skill when

- A pack needs its assertion set.
- A project gained an API contract or a readiness endpoint.
- A run passes but nobody can say what it proved.

## Risks and invariants

- A functional check pointed at the readiness endpoint proves only readiness.
- Accepting any non-5xx status turns a smoke test into a liveness ping.
- Marking an inapplicable check as passing rather than `NOT_RUN` manufactures coverage.

## Workflow

1. Always require process, readiness, graceful shutdown and lease teardown.
2. Require the port check where the stack declares a listen port.
3. Select a functional endpoint that is not the readiness path; if none is declared, record `NOT_RUN` and say why.
4. Constrain accepted status codes to what the contract declares; widen only with a recorded reason.
5. Assert seeded rows through the running service where the datastore is shared; read rows directly only from the ephemeral zero-dependency store.
6. State in the assertion set what the run is not evidence for.

## Required outputs

- `smoke/assertions.json` with per-check kind, requirement, expectation and absent-status
- an explicit `not_evidence_for` list

## Verification

- The functional check does not target the readiness path.
- Inapplicable checks are `NOT_RUN`, never `PASS`.
- Every mandatory check is present.

## Stop and escalate when

- The project exposes no endpoint that can be exercised without operator-owned credentials.
- Readiness cannot be distinguished from liveness in the project's own contract.
