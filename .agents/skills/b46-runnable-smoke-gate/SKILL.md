---
name: b46-runnable-smoke-gate
description: Decide runnable, limited or blocked from a real executed run only; never infer runnability from the presence of files, and never raise a status by editing JSON.
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

## Skill 4615: Conservative runnable-smoke gate

## Use this skill when

- A pack is about to be handed to a recipient, shipped, or described as runnable.
- A stack, entry, datastore or lease policy changed.
- A reviewer needs a deterministic answer rather than a manually edited status.

## Risks and invariants

- Certification can be falsified by trusting status fields instead of evidence.
- `NOT_RUN` averaged with passes looks like partial success; it is not success.
- A `limited` status quietly presented as `runnable` misleads the recipient about substitution and coverage.

## Workflow

1. Run the structural validator first and fail on any structural error.
2. Require an executed result; absence blocks.
3. Block on `NOT_RUN`, failed required assertions, incomplete teardown, digest mismatch, entry mismatch, unresolved unknowns, or production data.
4. Downgrade to `limited` for zero-dependency substitution, no functional endpoint, extension beyond the free quota, unsupported items, or recorded runner notes.
5. Write `gate-result.json` and a human-readable `gate-report.md` naming every failure and limitation.
6. Keep or lower the status; never raise it by editing evidence.

## Required outputs

- `smoke/runtime/gate-result.json` with deterministic failures and limitations
- `smoke/runtime/gate-report.md` stating the scope of the claim

## Verification

- A pack with no executed run is blocked.
- An edited result is blocked on digest mismatch.
- A zero-dependency run is `limited`, never `runnable`.
- A negative test that sets a passing status without evidence is rejected.

## Stop and escalate when

- Anyone asks for a `runnable` status without an executed run.
- A Batch 29-45 certification decision proposes to cite a smoke result as evidence.
