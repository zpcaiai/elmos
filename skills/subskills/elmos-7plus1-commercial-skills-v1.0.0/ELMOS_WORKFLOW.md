---
workflow_version: "1.0"
tracker:
  kind: github|linear|jira|gitlab|elmos
  project: "CHANGE_ME"
  active_states: [todo, in_progress, rework, merging]
  terminal_states: [done, cancelled, duplicate]
polling:
  interval_ms: 10000
workspace:
  root: "${ELMOS_WORKSPACE_ROOT}"
  isolation: worktree
  preserve_on_failure: true
hooks:
  after_create:
    timeout_seconds: 600
    sandbox: workspace-write
    command: "./scripts/bootstrap-workspace.sh"
  before_remove:
    timeout_seconds: 120
    sandbox: workspace-write
    command: "./scripts/archive-run-state.sh"
concurrency:
  global: 20
  per_tenant: 5
  per_project: 3
  per_state:
    verifying: 5
    repairing: 3
runtime:
  adapter: native
  max_turns: 40
  max_wall_clock_seconds: 21600
  approval_policy: ask
  sandbox: workspace-write
routing:
  policy: "examples/model-routing-policy.example.yaml"
completion:
  gate: "examples/completion-gate.example.yaml"
recovery:
  max_attempts: 3
  backoff: exponential-jitter
  no_progress_rounds: 3
---

# Elmos Workflow Contract

## Default posture

- Repository and durable ledgers are the source of truth.
- Reproduce or establish a baseline before changing implementation.
- Keep one authoritative Workpad with Plan, Acceptance, Validation, Risks and Evidence.
- Use isolated workspaces and do not touch paths outside the lease.
- Separate Generator, Reviewer and Verifier responsibilities and permissions.
- Run required validation before every publish/push/cutover action.
- Do not stop while an active task is incomplete unless a true external blocker exists.

## Task lifecycle

`discovered → planned → ready → running → verifying → repairing? → review → merging/releasing → completed`

Alternative terminal states: `blocked`, `cancelled`, `failed`, `rolled_back`.

## Completion

The task may enter `completed` only after P05 emits a `GateDecision=pass` for the exact source, target, configuration, policy, environment and evidence revisions.

## Rework

Rework creates a new attempt and fresh plan from the current trusted base. It may reuse verified artifacts but must not inherit unverified conclusions or stale evidence.
