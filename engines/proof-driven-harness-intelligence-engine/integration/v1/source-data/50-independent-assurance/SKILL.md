---
name: elmos-independent-assurance
description: Independent advisor/watchdog mesh for architecture, migration, security, correctness, performance, and release verification.
priority: P0
---

# K5 — Independent Assurance Plane

## Skills

- independent-advisor-runtime
- advisor-context-delta
- advisor-private-context
- advisor-tool-session
- advisor-tool-grant-policy
- advisor-severity-router
- advisor-nit
- advisor-concern
- advisor-blocker
- advisor-dedup
- advisor-rate-limit
- advisor-backlog
- advisor-backpressure
- advisor-quarantine
- advisor-failure-isolation
- architecture-watchdog
- migration-watchdog
- security-watchdog
- transaction-watchdog
- concurrency-watchdog
- database-watchdog
- api-contract-watchdog
- performance-watchdog
- proof-watchdog
- reviewer-consensus
- reviewer-disagreement-resolver
- evidence-first-review
- release-verdict-reviewer

## Independence requirements

Release-affecting reviewer MUST NOT rely solely on executor self-assessment.

Reviewer inputs SHOULD prioritize:

- diffs;
- semantic graph changes;
- compiler/LSP evidence;
- tests;
- runtime traces;
- policy violations;
- unresolved uncertainty.

## Finding contract

Every material finding includes:

- severity P0–P3;
- confidence;
- exact artifact/symbol/range;
- violated invariant;
- evidence ids;
- reproduction or reasoning path;
- certification impact;
- recommended remediation.

## Acceptance

- blocker delivery can stop wasteful execution;
- duplicate advisory noise is bounded;
- advisor failure cannot deadlock executor indefinitely;
- unsafe advisor output is quarantined;
- unresolved reviewer disagreement is surfaced to certification rather than averaged away.
