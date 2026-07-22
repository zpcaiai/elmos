# ADR-0038: Evidence-bound behavioral equivalence

## Status

Accepted

## Context

A migrated repository can compile, pass its translated tests and converge under Batch 8 while
still changing observable business behavior. Equal HTTP bodies can hide duplicated rows, partial
commits, missing messages, insecure cookies, wrong cache tenant keys, absent audit events or
changed cancellation semantics. Dynamic fields and runtime implementation differences also create
false diffs if comparison has no reviewed normalization model.

Golden snapshots alone are insufficient: the source may contain a bug, initial state may differ,
external services may respond differently, a collector may perturb execution, and a tolerance can
silently erase a real regression. Production-derived traffic and state add credential, privacy and
real-side-effect risks.

## Decision

Add `modules/behavior-equivalence` as the Batch 9 control plane. It:

- admits only Batch 8 R-D modules bound to immutable source and target Snapshots;
- requires independent mutable resources and evidence-bearing source/target runtime profiles;
- delegates provisioning, execution, comparison and Batch 8 feedback to injected authorities;
- aligns configuration, flags, locale, timezone, state, external recordings, virtual time and random sources;
- models required HTTP, database, transaction, message, file, object, cache, external, failure,
  audit, metric, resource and concurrency observations through OBM;
- binds blocking obligations to versioned scenarios and critical scenarios to reviewed source Goldens;
- preserves raw and canonical observations and accepts normalization only under scoped,
  semantic-impact-free, versioned rules;
- combines explicit required Oracles and refuses to average away a required failure;
- forbids tolerance for security, money, status/count, transaction, audit and tenant behavior;
- refuses Agent adjudication, unreviewed Golden output, unknown/absent evidence and retry-then-pass;
- detects repeated-run instability and excludes flaky differences from stable equivalence;
- routes evidenced target regressions back to Batch 8 without treating source bugs or collector
  failures as migration repair candidates;
- evaluates E-A through E-E per module and business capability, never by repository average;
- writes append-only, symlink-safe YAML/JSON/Zstandard evidence outside both repositories.

E-D and E-E admit a module only to Batch 10 production hardening. Batch 9 always reports
`eligible_for_cutover=false`.

## Consequences

The policy and decision core can be tested offline without running customer code or accessing
production. Real containers/processes, databases, brokers, object stores, traffic capture,
collectors, fault injection, native time/random adapters and domain Oracles remain approved Runner
capabilities. Missing or failed external evidence remains `NOT_COMPARABLE`, `UNKNOWN` or blocked.

Approved behavior changes remain separate from strict equivalence and carry reviewer, version,
compatibility and rollback evidence. A real customer claim requires fixed source/target artifacts,
sanitized data, isolated resources and matching clean runs; this repository's unit tests prove the
control-plane rules only.
