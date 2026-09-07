# Batch 10 performance, security and production hardening

`modules/production-hardening` implements the fail-closed Batch 10 control plane from ADR-0040.
It consumes an immutable target artifact admitted by Batch 9 and assigns the highest P-A through P-F
gate independently to every deployable service.

## Implemented control plane

- Immutable Java records cover artifact binding, service risk tiers, sanitized production workload
  models, bounded scenarios, open risks, calibration and the six readiness dimensions.
- Seven injected authority ports isolate environment calibration, load/performance, security,
  reliability/recovery, observability/operability, release and cost evidence from the control plane.
- Admission rejects missing Batch 8/9 evidence, mutable artifacts, duplicate service models, high-risk
  downgrades, unsafe traffic, production-connected scenarios and chaos/stress without abort and kill controls.
- The evaluator refuses repository averaging. Missing, duplicate, empty or wrong-artifact authority
  evidence fails closed for the affected service and is also preserved in the conformance report.
- The writer creates the specified performance, security, reliability, observability, SLO, release,
  cost, evidence and report tree. Files are atomic, append-only, Zstandard-compressed where appropriate,
  and protected from repository-root or symbolic-link writes.

## Gate contract

| Gate | Required evidence |
| --- | --- |
| P-A | calibrated normal/peak/stress and required soak; p95/p99/error SLO; controlled saturation, recovery and headroom |
| P-B | P-A plus zero blocking supply-chain, SAST, DAST, secret, authentication, authorization, tenant, crypto and configuration findings |
| P-C | P-B plus bounded retry/queue behavior, no corruption, crash/dependency recovery and required restore/PITR/RPO/RTO/failback |
| P-D | P-C plus calculable SLI/SLO, trace correlation, bounded/redacted telemetry, tested alerts and validated runbooks |
| P-E | P-D plus immutable signed artifact, verified provenance/SBOM, reproducibility, safe cost model, canary and rollback controls |
| P-F | P-E plus high-confidence performance/trace coverage, full critical security/chaos evidence, risk headroom and zero open risks |

P-E/P-F set only `eligible_for_progressive_delivery=true`. Every model and generated report fixes
`production_ready=false` and `eligible_for_cutover=false`. Batch 10 does not deploy production,
perform destructive production chaos, approve risk waivers or authorize 100% cutover.

## Contracts and Skills

The 12 Draft 2020-12 schemas under `contracts/production-hardening-schema` cover the manifest,
risk/workload/scenario inputs, calibrated domain evidence, release identity, evidence pack and final report.
The 39 Skills under `agent-skills/production-hardening` provide the complete workload, performance,
security, chaos/recovery, observability/SLO and release-safety workflow. All Skills share the same
artifact, external-authority and production-safety rules.

## Verification

```bash
mvn -pl modules/production-hardening -am test
python3 /Users/stephen/.codex/skills/.system/skill-creator/scripts/quick_validate.py agent-skills/production-hardening/<skill>
jq empty contracts/production-hardening-schema/*.json
mvn test
```

The local suite validates admission, per-service non-compensation, all gate blockers, external-authority
failure handling, append-only compressed evidence and the no-cutover invariant. It does not run customer
traffic, scanners, DAST, penetration, chaos, restore/PITR/DR, telemetry backends, signing systems or a
canary. Those external results remain `NOT_RUN` until approved environments and authorities provide them.

## Required field evidence before a real claim

1. Immutable artifact digest, target Snapshot, SBOM, signature and provenance from the release system.
2. Sanitized traffic-baseline provenance and a calibrated environment comparable in resource and data volume.
3. Raw normal, peak, burst, stress and required soak results including p95/p99, errors, saturation and recovery.
4. Scanner and security-test outputs for supply chain, code, API, identity, tenant boundaries and data protection.
5. Bounded chaos, crash, backup/restore and risk-required PITR/DR evidence with RPO/RTO measurements.
6. Queryable SLI/SLOs, correlated traces, tested alerts and operator-validated runbooks.
7. Isolated canary/rollback drills, schema compatibility, forward-fix plan, cost assumptions and named risk owners.

Without these, the repository can prove only that the Batch 10 policy engine is executable and fails closed.
