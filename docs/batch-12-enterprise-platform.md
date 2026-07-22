# Batch 12 enterprise multi-tenant migration platform

Repository scope was implemented and locally verified on 2026-07-21. This document separates deterministic policy and contract tests from real customer IAM, Runner, KMS/HSM, billing, deployment, deletion and disaster-recovery evidence. Those external operations remain `NOT_RUN` until an approved authority returns attributable evidence for the exact platform version.

## Outcome and reuse boundary

`modules/enterprise-platform` is the Batch 12 Enterprise Platform Control Model (EPCM) and independent conformance judge. It admits one immutable, signed platform artifact bound to the Batch 1–11 control planes; validates tenant, deployment and capability profiles; collects seven evidence envelopes; evaluates T-A through T-G; and writes an append-only evidence pack outside the repository.

It does not create a second source of truth. Tenant and identity primitives remain in `modules/enterprise-governance`; entitlement and commercial reconciliation remain in `modules/commercial-operations`; infrastructure, security and quality work remains in their independent execution domains. The new module only consumes versioned authority evidence and cannot provision tenants, execute customer code, read key material, charge customers, install infrastructure, delete customer data or perform production changes.

The seven mandatory ports are:

1. `TenancyIdentityAuthority`
2. `AuthorizationAuditAuthority`
3. `RunnerSecurityAuthority`
4. `ModelCostAuthority`
5. `DataGovernanceAuthority`
6. `DeploymentAuthority`
7. `EnterpriseAcceptanceAuthority`

Missing, failed, future-dated, wrong-run, wrong-version or non-passing evidence fails closed. Authority exception messages are not copied into evidence, so provider errors cannot disclose secrets.

## Independently gated deployment modes

| Mode | Required boundary |
| --- | --- |
| `SAAS_SHARED` | Shared platform with explicit tenant ownership, data/key isolation, quotas and no cross-tenant cache/artifact path |
| `SAAS_DEDICATED_RUNNER` | Shared control plane with tenant-dedicated, attested and isolated execution capacity |
| `HYBRID_PRIVATE_RUNNER` | Cloud control plane plus customer-network Runner; source-locality, scoped egress and short-lived credentials are evidenced |
| `SELF_HOSTED` | Customer-operated installation with declared responsibility/data-flow matrix, signed dependency closure, backup and rollback |
| `AIR_GAPPED` | Fully local signed bundle, zero unexpected network request, local model/license/update path and tested rollback |

All five modes must be declared and produce independent T-F evidence. A passing SaaS mode cannot compensate for a failing self-hosted or air-gapped mode. `ModeConformance` records the highest gate, blockers and evidence references per mode.

## Non-compensating gates

| Gate | Required evidence |
| --- | --- |
| T-A | Unique resource ownership, tenant/key/Runner/model/audit/Legal Hold boundaries, OIDC or SAML, required SCIM idempotency, MFA, revocation and no wrong-tenant identity |
| T-B | API and policy coverage, decision audit, named high-risk approval, separation of duties, bounded Break-glass and tamper-evident audit |
| T-C | Workload identity, full Runner attestation, tenant/job isolation, sandbox, egress, secret lifetime, source locality, transfer integrity and idempotent lease recovery |
| T-D | Model-Gateway-only access, prompt/data/cache policy, provenance, quota, fair scheduling, immutable meter/usage ledger, billing reconciliation and no duplicate charge |
| T-E | Classification, residency, retention, Legal Hold, deletion certificate, residual-copy accounting, per-tenant/CMK rotation and artifact provenance |
| T-F | All five installation topologies independently pass responsibility, signed closure, dependency/license, HA/restore, upgrade and rollback requirements |
| T-G | HA/DR and queue recovery, audit/ledger restore, Runner reconnect safety, operator/API/SCM surfaces, engineering/security/operations/business acceptance, contract alignment, complete traceability and zero Critical risk |

`enterprise_delivery_ready=true` is structurally legal only at T-G, with complete external evidence, zero blockers and all five modes at T-G. The control-plane invariant is always `production_operation_executed=false`.

## Deliverables

The artifact writer creates the specified `enterprise-platform/` hierarchy: `control-plane`, `execution-plane`, `model-plane`, `artifact-plane`, `trust-plane`, `integrations`, `deployments`, `offline`, `observability`, `tests` and `reports`, including every specified subdirectory. Writes are atomic, append-only and reject symbolic-link traversal. Tenant, deployment and capability streams use Zstandard JSONL.

The exact report set is:

1. `tenant-isolation-report.json`
2. `identity-security-report.json`
3. `authorization-report.json`
4. `private-runner-report.json`
5. `model-governance-report.json`
6. `quota-metering-report.json`
7. `billing-reconciliation-report.json`
8. `audit-integrity-report.json`
9. `data-governance-report.json`
10. `self-hosted-report.json`
11. `air-gapped-report.json`
12. `batch-12-conformance-report.json`

The writer also records the platform manifest, EPCM declaration, gate result, seven authority envelopes and the combined enterprise evidence pack. The 16 Draft 2020-12 contracts are under `contracts/enterprise-platform-schema`; they cover platform/tenant/deployment/capability input, all seven gate evidence domains, final evidence/conformance, immutable meter events and signed offline bundles.

Skills 281–330 are implemented as 50 focused packages under `agent-skills/enterprise-platform`. Each package has a validated `SKILL.md` and `agents/openai.yaml`; all share the evidence-bound protocol in `agent-skills/enterprise-platform/references/batch-12-enterprise-platform.md`.

## Repository verification

```bash
JAVA_HOME=/opt/homebrew/Cellar/openjdk@21/21.0.11/libexec/openjdk.jdk/Contents/Home \
  /opt/homebrew/Cellar/maven/3.9.10/bin/mvn -pl modules/enterprise-platform test

for schema in contracts/enterprise-platform-schema/*.schema.json; do jq empty "$schema"; done

for skill in agent-skills/enterprise-platform/*/SKILL.md; do
  /Users/stephen/.codex/skills/.system/skill-creator/scripts/quick_validate.py "$(dirname "$skill")"
done
```

The module suite covers the T-G success path, admission, every critical blocker class, per-mode non-compensation, sanitized provider failure, append-only output, compression and symlink rejection. Repository tests prove policy behavior and artifact shape only.

Recorded result: the Batch 12 module ran 31 tests with zero failures/errors/skips. The complete 48-module Maven reactor baseline plus this final path-hardening test represents 549 tests with zero failures and zero errors; one pre-existing Testcontainers/Flyway database test was skipped because its external container runtime was unavailable. All 50 Skills passed `quick_validate.py`, and all 16 schemas parsed with every local reference resolved.

## External acceptance boundary

The following are deliberately `NOT_RUN` in repository verification: real OIDC/SAML/SCIM and revocation; customer private Runner registration/attestation/egress; production KMS/HSM/CMK rotation; external model routing and data residency; financial billing/credit reconciliation; tenant deletion across backups/caches/model context; self-hosted and air-gapped installation; offline licensing/feed/update; production HA, restore and DR; and four-party customer acceptance. Until these are run by approved authorities against one signed platform artifact, Batch 12 must not be described as commercially ready or field-proven.
