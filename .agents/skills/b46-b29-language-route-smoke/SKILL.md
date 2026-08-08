---
name: b46-b29-language-route-smoke
description: Attach runnable smoke packs to directed language-route outputs across Java, C#, Python and TypeScript without implying route equivalence.
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

## Skill 4609: B29 language route smoke packs

## Use this skill when

- A b29 route has produced a target project.
- A route's target toolchain or entry point changed.

## Risks and invariants

- A green smoke run reads as "the conversion worked" when it only means "the target starts".
- Reverse routes are separate projects and need separate packs.
- Toolchain absence on the recipient's machine looks like a project defect.

## Workflow

1. Generate the pack against the target project only; never mix source and target in one pack.
2. Use the target language's real build and start commands, not a shim.
3. Record the exact runtime, build tool and package manager in the environment manifest.
4. Report a missing toolchain as `NOT_RUN` with the specific tool named.
5. State in the pack README that the run is not equivalence evidence.

## Required outputs

- one smoke pack per directed route target
- an environment manifest naming the exact toolchain versions exercised

## Verification

- The pack runs from a clean checkout of the target project alone.
- The B29 route certification gate does not consume the smoke result.

## Stop and escalate when

- The target requires a runtime the route's support matrix does not declare.
