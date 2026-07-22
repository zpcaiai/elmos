# Batch 10 production-hardening protocol

This reference is normative for every Batch 10 Skill. The machine authority is
`modules/production-hardening`; schemas live in `contracts/production-hardening-schema`.

## Admission contract

- Admit only an immutable artifact that passed Batch 8 and Batch 9. Bind every workload,
  scenario and evidence object to the same `artifact_id` and target Snapshot.
- Run only in an isolated, non-production environment. Sanitized traffic must have credentials
  removed. Production dependencies, production secrets and production control-plane access are prohibited.
- Every service has exactly one approved risk profile and workload model. Payment,
  authorization, tenant-aware, transaction-critical or regulated services are at least Tier 3.
- Load, security, chaos, recovery and release tools are external evidence authorities. Skills
  may prepare and interpret their plans and evidence but may not fabricate a tool result.
- Destructive, stress and chaos scenarios require timeouts, abort conditions and a tested kill switch.

## Production-readiness model

Evaluate each deployable service independently across Performance, Security, Reliability,
Observability, Operability and Release Safety. Repository averages never hide one failing service.

| Gate | Minimum meaning |
| --- | --- |
| P-A | calibrated normal, peak, stress and required soak evidence; p95/p99/error SLOs and headroom pass |
| P-B | P-A plus SBOM, supply-chain, SAST, DAST, authentication, authorization, tenant and data controls pass |
| P-C | P-B plus bounded failure behavior, crash consistency, recovery and required restore/PITR/DR pass |
| P-D | P-C plus calculable SLI/SLOs, correlated telemetry, tested alerts and validated runbooks pass |
| P-E | P-D plus immutable signed artifact, provenance, cost, canary and rollback plans/drills pass |
| P-F | P-E with high-confidence coverage, full critical scenarios, headroom and no open risks |

P-E and P-F mean only `eligible_for_progressive_delivery=true`. Batch 10 always emits
`production_ready=false` and `eligible_for_cutover=false`. It does not execute a production
deployment, approve a 100% cutover or claim production completion.

## Blocking evidence

Fail closed on missing, duplicate, stale or mismatched evidence; unknown services or artifacts;
unapproved/expired waivers; open critical or release-blocking risks; p99/SLO regression; critical
or exploitable-high vulnerabilities; secret, authentication, authorization or tenant regressions;
data corruption; unbounded retry, queue or metric cardinality; failed restore/RPO/RTO; missing
critical SLI/alert/runbook coverage; unsigned/unprovenanced artifacts; or any production access.

An external tool failure is an explicit blocked result. Record only the authority and exception
class; never persist secret-bearing exception messages. Agent judgment is not execution evidence.

## Evidence rules

- Record authority ID, tool/config version, immutable input hashes, timestamps, abort reason,
  raw evidence references and any environmental noise.
- Separate `FAILED`, `NOT_RUN`, `BLOCKED`, `INCONCLUSIVE` and `NOT_APPLICABLE`; none is `PASSED`.
- Store append-only artifacts outside the target repository under the Batch 10 delivery tree.
- Redact secrets and personal data. Never weaken a threshold to obtain a pass.
- Preserve open risks with owner, mitigation, fallback, approval, expiry and release-blocking flag.

## Handoff

The evidence pack must answer which immutable artifact was tested, the risk profile and workload
source per service, normal/peak/burst load, tail latency and headroom, critical security and chaos
results, restore/RPO/RTO results, SLI/SLO/alert/runbook coverage, release safeguards, open risks,
and the exact highest gate. Human release owners decide whether and how to begin progressive delivery.
