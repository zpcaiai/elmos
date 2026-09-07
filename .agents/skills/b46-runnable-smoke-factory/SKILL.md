---
name: b46-runnable-smoke-factory
description: Produce a complete one-click runnable smoke pack for a converted or generated project: detect the stack, derive minimal data, synthesize disposable seeds, emit entries, run, and reclaim on lease expiry.
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

## Skill 4601: Runnable smoke pack factory

## Use this skill when

- A converter or generator has produced a project that a human is about to receive.
- A project changed stack, framework, datastore, contract or entry point.
- A recipient reports that they cannot get a generated project to start.

## Risks and invariants

- A pack that looks complete but has never been executed proves nothing; files are not evidence.
- Regenerating over a pack a user has edited can silently discard their fixture changes.
- A pack generated from stale detection produces entries that do not match the project.

## Workflow

1. Run the four stages through `scaffold_smoke_pack.py --write` and read the reported unknowns.
2. Resolve every unknown in `smoke/profile.json` — start command, listen port, datastore engine — before going further.
3. Execute the highest-fidelity available entry (`compose` > `script` > `zero-dep`) with a real run.
4. Run the structural validator, then the conservative gate.
5. Record the resulting status and its limitations where the recipient will see them.

## Required outputs

- `smoke/pack.json` with digests over profile, requirements, seed and runner manifests
- `run-smoke.sh`, `run-smoke.ps1`, `Makefile.smoke`, and `docker-compose.smoke.yml` where applicable
- `smoke/README.md` addressed to the recipient, in their language
- `smoke/runtime/result.json` and `gate-result.json` from a real run

## Verification

- `python3 scripts/batch46/validate_smoke_pack.py <project>` returns clean.
- `python3 scripts/batch46/run_smoke_gate.py <project>` reports `runnable` or a `limited` status whose limitations are all understood.
- Re-running the scaffold produces identical digests for an unchanged project.

## Stop and escalate when

- The project cannot start without source edits.
- No entry can be made available honestly.
- Detection disagrees with the generator's own manifest about the stack.
