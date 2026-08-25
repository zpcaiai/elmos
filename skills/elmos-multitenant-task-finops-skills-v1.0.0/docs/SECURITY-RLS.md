# Security, Tenant Isolation, and Audit

## 1. Threat model

Primary threats:

- forged tenant/account identifiers;
- horizontal cross-tenant access;
- application role bypassing RLS;
- duplicate or replayed control/finance requests;
- stale runner mutating a newer attempt;
- prompt/source/log leakage between tenants;
- object-store key guessing;
- provider credential exposure;
- untrusted repository content causing tool misuse;
- manual cost/revenue manipulation;
- deletion/export crossing tenant boundaries;
- audit tampering.

## 2. Identity context

The server validates:

- issuer, audience, signature, expiry, nonce/session rules;
- account subject;
- tenant membership and status;
- role/permission;
- step-up authentication for sensitive finance/admin actions.

After authorization, each database transaction sets:

```sql
SET LOCAL app.tenant_id = '...';
SET LOCAL app.account_id = '...';
SET LOCAL app.actor_id = '...';
SET LOCAL app.request_id = '...';
SET LOCAL app.trace_id = '...';
```

Application SQL and RLS use these settings. A client-controlled `X-Tenant-Id` may be accepted only as a tenant-selection hint and must be resolved against membership.

## 3. RLS

Tenant-scoped policy pattern:

```sql
USING (tenant_id = elmos.current_tenant_id())
WITH CHECK (tenant_id = elmos.current_tenant_id())
```

Apply `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`.

Tables include:

- task/run/node/attempt/event/progress/checkpoint;
- task input/artifact/log;
- usage/cost;
- revenue/allocation/financial projections;
- tenant quota and audit;
- outbox payloads containing tenant data.

Global account slot access is exposed through constrained functions or policies based on `current_account_id()` and authorized control/workflow roles.

## 4. Database roles

- Schema owner/migrator is isolated and never used by the application.
- Runtime roles are not superuser, table owner, or `BYPASSRLS`.
- Workflow/outbox/analytics roles receive only needed operations.
- Finance admin actions use step-up auth and dedicated audited endpoints.
- Break-glass credentials are short-lived, separately stored, and alert on use.

## 5. API authorization

Permission examples:

```text
task:create
task:read:self
task:read:tenant
task:control:self
task:control:tenant
artifact:read
cost:read:self
finance:read:tenant
finance:adjust
tenant:quota:read
tenant:quota:update
platform:finance:read
recovery:approve
retention:manage
```

Object ownership and project permissions are checked in addition to tenant membership.

## 6. Runner and sandbox

- Enrollment token is one-time and not reused as runtime identity.
- Each runner has a unique mTLS/workload identity.
- Identity binds tenant/site, approved capabilities, version, and signed artifact.
- Each task executes in an isolated, unprivileged sandbox.
- Base image is read-only and pinned by digest.
- Network is deny-by-default with task-specific egress allowlist.
- Secrets are short-lived references injected to memory/tmpfs.
- Runner callbacks require attempt and lease generation.
- Drain, quarantine, revoke, and upgrade operations are audited.

## 7. Model/tool security

- Treat repository files, documents, images, audio transcripts, and generated text as untrusted.
- Enforce tool allowlists and parameter-level policies.
- Separate model planning from privileged execution.
- Require explicit approval for high-impact tools/actions.
- Sanitize prompts and logs before telemetry.
- Do not expose secrets in model context.
- Meter and budget every provider/model invocation.
- Bind provider response to request ID and usage receipt.

## 8. Object storage

Object keys are non-guessable and tenant-scoped. Access uses short-lived signed requests or service identity with policy conditions.

Manifest verification:

- tenant/task/run ownership;
- object URI prefix;
- media type;
- size;
- SHA-256;
- encryption key reference;
- retention/legal hold;
- malware/content policy where applicable.

Object storage logs feed audit/SIEM.

## 9. Encryption and redaction

- TLS/mTLS in transit.
- Storage/provider-managed encryption at rest plus tenant/key policy where required.
- Sensitive raw input may be retained encrypted; searchable projection is redacted.
- Logs exclude access tokens, private keys, cookies, secrets, full payment identifiers, and reusable repository credentials.
- Hash or tokenize identifiers where full value is unnecessary.
- Field-level visibility applies to finance/provider receipts.

## 10. Financial integrity

- Usage and revenue entries are immutable.
- Corrections reference prior entries.
- Manual adjustments require role, step-up auth, reason, supporting evidence, and approval policy.
- Price-book changes are effective-dated and audited.
- FX source/version is recorded.
- Revenue allocations cannot exceed source amount.
- Financial exports are watermarked and audited.
- Reconciliation exceptions cannot be hidden by editing summaries.

## 11. Audit events

Audit at minimum:

- login/session and membership changes;
- tenant selection and authorization denial;
- task create/pause/resume/cancel/retry;
- slot/quota/budget override;
- runner enroll/revoke/quarantine;
- manual recovery decision;
- input/output access and export;
- retention/legal hold/delete;
- price-book change;
- usage correction;
- charge/credit/refund/recognition/collection;
- revenue allocation/manual adjustment;
- finance dashboard/export access;
- break-glass use.

Audit events are append-only and exported to an independent security backend where required.

## 12. Security tests

- forged tenant/account headers;
- direct object reference across tenant;
- RLS raw SQL with runtime role;
- runtime role attempts `SET ROLE`, ownership, or bypass;
- account slot claim/release across account;
- stale lease/generation replay;
- duplicate provider receipt;
- prompt injection requesting cross-tenant tools/data;
- object key traversal/guessing;
- signed URL scope/expiry;
- log secret scanning;
- malicious archive/path/symlink;
- finance adjustment without role/step-up;
- over-allocation and negative amount edge cases;
- export/delete cross-tenant;
- backup restore with RLS preserved.
