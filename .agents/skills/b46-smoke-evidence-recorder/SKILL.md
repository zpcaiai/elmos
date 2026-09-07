---
name: b46-smoke-evidence-recorder
description: Record what actually happened during a run — uncut logs, environment manifest, per-check status, lease outcome, digest — so the result can be trusted and re-checked.
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

## Skill 4614: Smoke evidence recording

## Use this skill when

- Any smoke run executes.
- A result needs to be reviewed by someone who did not run it.

## Risks and invariants

- Trimmed logs remove exactly the failure a reviewer needs.
- A result without an environment manifest cannot be reproduced or discounted.
- An undigested result can be edited after the fact.

## Workflow

1. Persist uncut stdout and stderr, plus install and compose logs.
2. Record the environment manifest: platform, interpreter, and which toolchains were present.
3. Record every check with status, detail and observation time — including `NOT_RUN` with its reason.
4. Digest the result over its own content so post-hoc edits are detectable.
5. Write the result on every exit path, including failure and interrupt.

## Required outputs

- `smoke/runtime/result.json` with a content digest
- `smoke/runtime/logs/` with uncut output

## Verification

- Editing the result and re-running the gate produces a digest-mismatch failure.
- A failing run still produces a complete result file.

## Stop and escalate when

- Logs cannot be captured, for example because the start command detaches its own output.
