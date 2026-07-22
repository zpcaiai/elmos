# Batch 12 enterprise platform protocol

## Read order

1. Bind the assessment to one immutable, signed platform version and its SBOM/provenance.
2. Load `modules/enterprise-platform` and the relevant schema under `contracts/enterprise-platform-schema`.
3. Preserve the existing `enterprise-governance`, `commercial-operations`, infrastructure and security domains as execution authorities; do not create a competing tenant or billing truth.
4. Return attributable external evidence or `NOT_RUN`; local policy tests are not field proof.

## Invariants

- Carry a server-established tenant, organization, actor, policy and correlation context through every request, job, model call, artifact, meter and audit event. Missing context denies access.
- Default-deny cross-tenant access. Client-supplied tenant filters, UI hiding, paths or cache keys never establish authorization.
- Bind approvals, policies, Runner attestations, model routes, licenses, evidence and reports to exact versions and immutable digests.
- Use short-lived workload identities and job-scoped credentials. Never emit secret values, source text, full Prompts or customer data into ordinary logs/evidence.
- Keep Control Plane and untrusted execution separate. Privileged IAM, Runner, KMS/HSM, billing, deployment, deletion, offline import and DR work requires an approved external authority.
- Treat all five deployment modes independently: SaaS shared, SaaS dedicated Runner, hybrid private Runner, self-hosted and air-gapped. Evidence for one cannot compensate another.
- Preserve append-only Meter, Ledger, Audit and Provenance chains; corrections are new entries.
- Legal Hold precedes deletion. Deletion covers primary stores, search, cache, analytics, telemetry, model context, Runner cache and backup lifecycle.
- Air-gapped means zero undeclared network access, complete signed dependency/model closure, local license enforcement and tested offline upgrade/rollback.
- `enterprise_delivery_ready=true` is legal only at T-G, with all modes ready, zero critical risks and a complete externally attributable evidence pack.
- The control plane always records `production_operation_executed=false`.

## Gates

- T-A: tenant ownership/isolation plus OIDC or SAML, required SCIM, MFA and session revocation.
- T-B: complete API/Policy/approval/audit coverage, separation of duties, bounded Break-glass and tamper detection.
- T-C: workload identity, Runner attestation, sandbox/egress/secret/lease and tenant job isolation.
- T-D: model-gateway-only access, data policy/provenance, quota/meter/Ledger/billing and fair scheduling.
- T-E: classification/residency/retention/Legal Hold/deletion/key/CMK and Artifact provenance.
- T-F: independently validated private and offline topology, signed closure, install, HA/backup and rollback.
- T-G: HA/DR, operator surfaces, four-dimension acceptance, contract alignment, complete traceability and zero critical risk.

## Evidence handling

- Keep authority IDs, observation time, platform version, raw evidence references and explicit status.
- Fail closed on missing, stale, future, wrong-version, duplicate or mismatched evidence.
- Write evidence only to the configured append-only workspace outside the platform repository.
- Never claim a real tenant deployment, SSO/SCIM integration, private Runner, charge, deletion, key operation, offline install or DR exercise from synthetic fixtures.
