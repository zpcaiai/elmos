# Batch 46 — Quality gates

Two checks, in order. Only the second may state that a project is one-click
runnable.

## 1. `validate_smoke_pack.py` — structure

Static, cheap, runs on every pack. Rejects:

- missing pack files, missing `run-smoke.sh` or `Makefile.smoke`, missing vendored runner;
- digest mismatches between `pack.json`, `profile.json`,
  `minimal-data-requirements.json` and `runner-manifest.json` — a pack whose
  stages were generated from different revisions of each other;
- a seed manifest that does not record `production_data_used: false`, is not
  classified `ephemeral-disposable`, uses an unknown data-source class, carries a
  `desensitized-sample` without an authorization reference, or has unresolved
  sensitive-value findings;
- a declared seed artifact that is not on disk;
- a missing mandatory assertion (`process-started`, `http-readiness`,
  `graceful-shutdown`, `lease-teardown`);
- an entry with an invalid status, an `unavailable` entry with no stated reason,
  or a pack with no available entry at all;
- a lease policy that is not 600 free seconds, `auto_renew: false`,
  `extend_policy: explicit-only`;
- an available `zero-dep` entry that uses engine substitutes without carrying its
  semantic warning.

## 2. `run_smoke_gate.py` — the conservative gate

Requires a real executed run. It never infers runnability from the presence of
files.

| Status | Meaning |
| --- | --- |
| `runnable` | every required assertion passed in a real run; the lease expired or was released cleanly; teardown left no residue; nothing unknown remains |
| `limited` | the run passed, but coverage is reduced |
| `blocked` | anything else, including `NOT_RUN` |

Blocking conditions:

- no `smoke/runtime/result.json`;
- `overall` is `NOT_RUN` — a run that could not execute never passes;
- any required assertion failed;
- `teardown_complete` is not true, or the `lease-teardown` assertion did not pass;
- the result digest does not match the result content — evidence edited after the run;
- the result claims an entry the runner manifest does not mark `available`;
- any unresolved `unknown` item in the pack;
- `production_data_used` is true.

Downgrades to `limited`:

- executed through the `zero-dep` entry (an embedded substitute is not the declared engine);
- no contract-declared functional endpoint was exercised;
- the lease was extended beyond the free quota;
- unresolved `unsupported` items, such as an unmapped SQL type whose seed value
  fell back to a string literal;
- any note the runner recorded, including a zero-dep substitution that could not
  load the declared schema verbatim.

## What a green gate does not mean

`runnable` means the project starts from a clean checkout with one command,
serves at least one request against disposable seed data, and is fully reclaimed
when the lease expires.

It is not evidence of route equivalence, framework parity, SQL dialect
correctness, UI behaviour, performance, security, accessibility, or fitness for
any environment other than a throwaway one. The Batch 29-45 gates remain the only
authorities on those, and none of them may cite a Batch 46 result as an input to
a certification decision.

## Running them

```bash
python3 scripts/batch46/validate_smoke_pack.py <project>
python3 scripts/batch46/run_smoke_gate.py <project>
make -f Makefile.batch46 batch46-check
```
