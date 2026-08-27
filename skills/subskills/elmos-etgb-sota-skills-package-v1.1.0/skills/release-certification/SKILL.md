---
name: release-certification
description: Evaluate ETGB release gates, evidence completeness, waivers, and promotion decisions for Elmos candidates.
---

# Release Certification

## Inputs

Complete run results, suite and case versions, coverage report, corpus approvals, model/Skill/toolchain/environment digests, security report, cost/wall-clock and owner attestations.

## Preconditions

- run is complete for selected release/golden scope;
- no mutable aliases;
- coverage model complete;
- hidden tests remained isolated;
- evidence bundle digests verify;
- no unclassified P0 result.

## Gate evaluation

Apply `matrices/release-gates.yaml`. Hard gates are conjunctive. Weighted score cannot override P0 SSER, data corruption, security, transaction or evidence failures.

## Failure triage

Classify failures as source baseline, environment/dependency, product transformation/generation, target build, Oracle defect, test data, security, performance or unsupported disclosure. Only proven test/environment defects may be excluded, with signed evidence and rerun.

## Waivers

A waiver needs scope, reason, customer impact, compensating control, owner, expiry and planned regression. No waiver is permitted for P0 silent semantic error, data corruption or privilege escalation.

## Decision

Return exactly one:

- `PROMOTE`: all gates pass;
- `REJECT`: product or hard-gate failure;
- `BLOCKED`: incomplete environment/evidence/license/Oracle;
- `PROMOTE_WITH_WAIVER`: only allowed non-P0 scoped waiver.

Do not return ambiguous prose instead of a state.

## Evidence bundle

Include plan, all case results, logs/diffs/traces, environment and corpus digests, model/Skill/prompt versions, costs, gate calculations, waivers and signatures. Retention and access follow tenant and compliance policy.

## Canary

Certification permits deployment to controlled canary; it does not replace production telemetry and rollback. Canary criteria must monitor the same business invariants used by ETGB.

## v1.1 hard gates

In addition to semantic gates, require zero Environment-authority violation, evidence-integrity failure, candidate/plan/Oracle drift, undisclosed unsupported behavior, P0 recovery failure, budget overrun and supply-chain failure. Missing seed coverage or required metrics is `BLOCKED`. Use `etgb gate`; do not hand-edit the decision after evidence is sealed.
