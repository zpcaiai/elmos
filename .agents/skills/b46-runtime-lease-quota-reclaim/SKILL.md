---
name: b46-runtime-lease-quota-reclaim
description: Enforce the ten-minute free runtime quota: an independent watchdog, process-group termination, container and volume removal, explicit-only attributable extension, and a result written on every path.
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

## Skill 4607: Runtime lease, free quota and reclamation

## Use this skill when

- Any smoke run is executed.
- A recipient asks to keep a smoke environment alive.
- A run left a process or container behind.

## Risks and invariants

- A smoke environment that quietly becomes permanent is how fixture data reaches something that matters.
- Signalling a PID instead of a process group leaves wrapper children listening.
- Treating a kill after the grace period as successful cleanup hides an unresponsive shutdown path.

## Workflow

1. Open a lease at run start with the free quota; allow shortening, never silent lengthening.
2. Run the watchdog independently of the application under test.
3. On expiry send SIGTERM to each managed process group, wait the grace period, then SIGKILL and record it as a shutdown failure.
4. Run `docker compose down -v --remove-orphans` for every tracked compose file and delete every tracked ephemeral path.
5. Require `--seconds`, `--reason` and `--actor` for extension; accumulate `billable_seconds` beyond the free quota.
6. Write `lease-result.json` on expiry, early release, interrupt and crash; keep teardown idempotent.

## Required outputs

- `smoke/runtime/lease.json` and `lease-result.json`
- a teardown report listing processes, compose results and removed paths
- `billable_seconds` for the Batch 44 metering boundary

## Verification

- After teardown: no live process, no undeleted path, no compose failure, the port no longer accepts connections.
- An extension without a reason or actor is rejected.
- Calling teardown twice returns the same report and changes nothing.

## Stop and escalate when

- The application detaches processes outside its process group.
- Teardown cannot remove a volume or path.
