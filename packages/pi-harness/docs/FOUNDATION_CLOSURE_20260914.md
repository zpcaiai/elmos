# Harness foundation regression closure — 2026-09-14

Scope: the shared PI Harness execution boundary, including its existing coding
agent bridges, local-run CLI and repair loop. The implementation is based on
`origin/main` at `429bd5f4e`, preserving the newer bridge and CLI implementations
that were absent from the original local checkout. This report records local
engineering work; it is not an external qualification or certification receipt.

## Reproduced gaps and resulting behavior

| Boundary | Previous behavior | Implemented behavior |
| --- | --- | --- |
| DAG scheduling | Duplicate IDs silently replaced nodes; ready-node lookup could schedule a root despite a cyclic remainder | Both entry points validate identities, dependency collections, aliases, references and acyclicity; completed nodes must be known and dependency-closed |
| Fan-out | Duplicate agent IDs overwrote results; one task could be submitted more than once | Validate unique agent/task/workspace assignments before starting workers; snapshot the assignment sequence and preserve each branch outcome |
| Agent cancellation | Cancellation arriving during a model request could still dispatch a tool or report completion | Recheck after model and tool callbacks; retain completed tool observations and report cancellation even on the last budgeted turn |
| Durable cancellation | Reserved or newly requested tools could execute after a task was paused or cancelled | Check the durable task state at reservation and dispatch; queued retries also accept cancellation requests |
| Environment recovery | Owner/type substitution, malformed generations and modified authority snapshots were accepted; current overrides could widen saved restrictions | Verify owner, environment type, generation and authority digest; intersect saved authority restrictions and current overrides, rejecting incomparable conflicts |
| Workspace recovery | Expired leases could be revived by heartbeat or replayed acquisition; arbitrary owners could attach checkpoints | Reject expired leases and stale acquisition generations; bind workspace checkpoints to the current live owner; retain checkpoint-gated fenced takeover |
| Tool callbacks | A replacement executor could start or complete an old generation's call; completion could precede execution or conflict with a prior result | Bind both active and original executor identity/generation; enforce execution order and identical completion replay |
| Running-task quota | HTTP request bodies could raise the running-task limit | Use trusted server configuration (default 3); reject request-supplied quota overrides without changing task state |
| Verification | Repeated passes inflated the count; a later failure did not remove a pass; old passes survived another execution | Count latest distinct gates in the current execution, invalidate them on RUNNING, block any failed or absent gate, reject weakened requirements and terminal result mutation |
| Temporal replay | Only the first 1,000 task events were searched; non-hexadecimal evidence digests passed validation | Follow advancing event cursors with bounded pages and retain the exact persisted result without re-executing the backend; validate canonical SHA-256 syntax |
| Repair classification | Reused regex variables broke strict type checking in the newer remote implementation | Separate file matches from optional classification matches without weakening types or changing classification semantics |

Regression coverage lives in `tests/test_harness_closure.py` and the real HTTP
quota test in `tests/test_api.py`. Existing core, bridge, CLI, repair, identity,
provider-boundary and evidence tests remain in the suite.

## Replay

Observed validation on the final change:

- PI Harness suite: 97 selected, 93 passed, 4 external integration profiles
  skipped; Python 3.14.5 in the existing ELMOS-Test-Lab WSL distribution.
- Repository package integration: 4 tests passed; pinned archive/importer check
  passed without executing archive code.
- Strict mypy: no issues in all 45 runtime source files.
- Diff whitespace validation: passed.
- Supplementary unchanged Proof-Driven v3 baseline: all 11 selected migration
  and qualification-filesystem tests passed in a native Linux temporary tree.
  An initial run on the Windows mount had six failures/errors from CRLF digest
  conversion and filesystem semantics; exporting the original Git revision
  with `git -c core.autocrlf=false archive` and using the native filesystem
  resolved those cases without changing migration bytes, expected digests or
  safety checks. This focused replay is not a full v3 qualification run.

Run the package tests on a POSIX filesystem/runtime with Python >= 3.11:

```sh
PYTHONPATH=packages/pi-harness/src python3 -m unittest discover \
  -s packages/pi-harness/tests -p 'test_*.py'
python3 tooling/integrate_pi_harness.py --check
python3 -m unittest discover -s tests/pi-harness -p 'test_*.py'
mypy --platform linux --config-file packages/pi-harness/pyproject.toml \
  packages/pi-harness/src/elmos_pi_harness
git diff --check
```

Use the declared `production` and `dev` dependencies for strict type checking.
Windows-native execution of the package remains unsupported because its
immutable evidence ledger requires POSIX file locks. Do not bypass those locks.

The production PostgreSQL, Temporal, IdP and external verification integration
profiles remain opt-in. Skipped profiles are **NOT_RUN**, not successful tests.
Cloud operations, independent verification, customer acceptance, disaster
recovery and production deployment were not executed by this change.
Certification remains **NOT_CERTIFIED**.
