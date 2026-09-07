---
name: b46-one-click-entry-emitter
description: Emit the script, compose, make and zero-dependency entries into a project with honest per-entry availability, a vendored stdlib-only runner, and no silent engine substitution.
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

## Skill 4605: One-click entry emission

## Use this skill when

- A pack has requirements and seeds and needs runnable entries.
- A project gained or lost a Dockerfile, datastore or start script.
- An entry that was available stops working.

## Risks and invariants

- An entry that appears available but cannot run wastes the recipient's first five minutes and their trust.
- A vendored runner that imports from the ELMOS repository breaks the moment the project is handed over.
- A zero-dependency entry built on an undeclared engine swap silently changes semantics.

## Workflow

1. Determine availability per entry from evidence: start command, Dockerfile, containerisable datastore, approved substitute.
2. Emit unavailable entries with a specific reason rather than omitting them.
3. Vendor `run_smoke.py`, `smoke_lease.py` and `smoke_common.py` into `smoke/tools/`; keep them standard-library only.
4. Attach the semantic warning to any zero-dependency entry that substitutes an engine.
5. Bind the lease policy — 600 free seconds, no auto-renew, explicit-only extension — into the runner manifest.
6. Make `run-smoke.sh` executable and provide the PowerShell equivalent.

## Required outputs

- `run-smoke.sh`, `run-smoke.ps1`, `Makefile.smoke`, `docker-compose.smoke.yml` where applicable
- `smoke/runner-manifest.json` with per-entry status, reason and lease policy
- `smoke/tools/` containing the vendored runner

## Verification

- Every entry has status `available` or `unavailable`, and every `unavailable` has a reason.
- At least one entry is available, or the pack is reported as not runnable.
- The vendored runner executes from a copy of the project with no ELMOS checkout present.

## Stop and escalate when

- No entry can be made available honestly.
- The project's start command requires interactive input or an operator-owned secret.
