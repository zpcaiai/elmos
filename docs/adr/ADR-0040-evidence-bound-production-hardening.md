# ADR-0040: Evidence-bound production hardening

## Status

Accepted

## Context

A behaviorally equivalent migration is not automatically safe under production load, hostile input,
dependency failure or operator intervention. Average latency can hide tail collapse; an SBOM can be
unrelated to the deployed image; retry policy can amplify an outage; a backup can exist but fail to
restore; telemetry can omit the exact signal needed for rollback. A passing local test suite cannot
prove any of these external properties.

Production-hardening tools also carry unusual authority and blast radius. Load, DAST, chaos, restore,
DR and progressive-delivery exercises must not reach production merely because an Agent assembled a
plan. Production deployment and 100% cutover are separate human-controlled lifecycle decisions.

## Decision

Add `modules/production-hardening` as the Batch 10 evidence and gate control plane. It:

- admits only one immutable artifact that passed Batch 8 and Batch 9;
- assigns one approved service risk profile and one sanitized, provenance-bearing workload model;
- rejects high-risk service downgrades below Tier 3;
- requires isolated scenarios with timeouts, abort conditions and kill switches;
- delegates calibration, performance, security, reliability, observability, release and cost work to
  injected external authorities and never executes host processes or production operations;
- evaluates Performance, Security, Reliability, Observability, Operability and Release Safety per
  service, never by repository average;
- requires calibrated normal, peak, stress and risk-selected soak evidence for P-A;
- requires SBOM/supply-chain, static/dynamic application security, identity, tenant and data controls for P-B;
- requires bounded failure behavior, crash consistency and risk-selected restore/PITR/DR for P-C;
- requires calculable SLI/SLOs, correlated telemetry, tested alerts and validated runbooks for P-D;
- requires immutable signed artifacts, provenance, reproducibility, cost, canary and rollback evidence for P-E;
- reserves P-F for high-confidence coverage, full critical scenarios, headroom and zero open risks;
- preserves tool failure, missing evidence, open risks and unsafe access as explicit blockers;
- writes append-only, symlink-safe YAML/JSON/Zstandard evidence outside the target repository.

P-E and P-F authorize only consideration of progressive delivery. The Batch 10 model makes
`production_ready=false` and `eligible_for_cutover=false` invariants. It cannot execute a production
deployment, approve a waiver, perform destructive production chaos or declare full production completion.

## Consequences

The decision core and evidence writer are deterministically testable without customer code, credentials
or infrastructure. Real traffic baselines, calibrated load labs, security scanners, penetration exercises,
chaos, backup/restore, DR, telemetry backends, signing services and canary/rollback drills remain approved
Runner capabilities. Missing or failed external evidence remains `NOT_RUN`, blocked or inconclusive.

This deliberately raises the cost of a readiness claim: each service must supply attributable raw evidence
for the exact artifact. It also keeps the release decision honest. A local Batch 10 test proves gate logic,
not production readiness, deployment success or cutover safety.
