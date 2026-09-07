---
name: enterprise-suite-engine-contract-and-worker
description: Implement and operate the ELMOS Enterprise Suite Worker contract for SAP, Oracle, Dynamics, Dataverse, Power Platform, Salesforce, ERP, CRM, HCM, SCM, and EPM modernization. Use for suite Engine APIs, Adapter registration, leased Runner execution, sandbox policy, idempotent jobs, cancellation, and fail-closed evidence handling.
---

# Enterprise Suite Engine Contract

## Execute

1. Pin tenant, immutable snapshot, suite instance, environment, product release, Adapter version, job lease, resource scope, and idempotency key.
2. Call only the standard `/engine/v1` capabilities, scan, plan, execute-step, validate, job, and cancel contracts.
3. Keep discovery read-only. Run metadata export, migration, process test, or cutover only in an approved isolated Runner.
4. Return `NOT_CONFIGURED`, `NOT_RUN`, `INCONCLUSIVE`, or a dedicated failure when an Adapter, license, permission, sandbox, business approval, or evidence input is missing.
5. Emit immutable evidence references and actual external status. Never invent suite access, execution, reconciliation, approval, or production mutation.

## Enforce

- Bind credentials to one environment and short-lived job lease; prohibit shared administrators.
- Deny production configuration changes, Transport publication, Solution or Salesforce production deployment, permission mutation, bulk data deletion, automatic difference acceptance, automatic Cutover, and automatic Decommission.
- Keep Worker execution separate from independent Cutover and Decommission decisions.
- Revoke leases and destroy temporary environments at job completion.

## Output

Return capability, job, error, result, and evidence objects compatible with `contracts/suite-api/enterprise-suite-engine-api.yaml`.
