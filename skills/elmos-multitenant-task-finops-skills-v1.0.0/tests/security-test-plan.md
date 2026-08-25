# Multi-Tenant Security Test Plan

## Identity and authorization

- Reject unauthenticated requests and expired/incorrect-audience tokens.
- Derive `account_id` from the verified subject mapping and `tenant_id` from an active membership.
- Ignore or reject a caller-supplied tenant/account identity that conflicts with the verified context.
- Test role changes, membership revocation, service identities, support impersonation, and break-glass audit.

## PostgreSQL isolation

- Use a non-owner, non-superuser application role.
- Enable and force RLS on task, run, node, attempt, event, progress, checkpoint, input, artifact, logs, outbox, usage, revenue, allocation, summary, and audit tables.
- Test direct reads, joins, subqueries, functions, views, COPY, prepared statements, background jobs, and connection-pool context reset.
- Prove one request cannot inherit the prior request's tenant context from a pooled connection.

## Object and event isolation

- Object keys contain opaque tenant/task identifiers and are accessed through short-lived scoped credentials.
- Bucket policy denies cross-tenant prefixes even when a URI is guessed.
- Event messages carry tenant identity from server state; consumers enforce tenant-aware projection keys.
- SSE/WebSocket subscriptions re-authorize before replay and on membership revocation.

## Sensitive data

- Do not persist raw secrets, provider keys, repository credentials, or unredacted authorization headers in task input, logs, events, or financial raw usage.
- Encrypt confidential/restricted objects and maintain key references, not plaintext keys.
- Apply retention, export, deletion, and legal-hold policies with audit records.

## Abuse and denial of service

- Rate-limit submissions independently from the three-active-task rule.
- Bound queued and paused tasks, input size, node count, log rate, event payload, retries, and total budget.
- Test hot-account lock contention, queue flooding, very large manifests, event amplification, and expensive model loops.
