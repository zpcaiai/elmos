# Runtime and Evidence Boundaries

## Local authority

The autonomous QA engine may perform deterministic, bounded local operations:

- validate requests, policies, manifests, hashes, paths, and state transitions;
- read an explicitly scoped project tree without following symlinks or executing
  repository content;
- normalize structured requirements and create plans, DSL objects, traceability,
  reports, and lifecycle decisions;
- write only below an explicitly supplied output/worktree root through the
  artifact publisher, and only for a locally verified non-plan-only result;
- create deterministic archives and revalidate their complete payloads;
- persist run metadata, idempotent outcomes, evidence receipts, event/audit
  chains, and local chain heads in its tenant-scoped SQLite store.

The configured `TrustedDeliveryService` adds a narrower local mutation
authority for Skills 37-39. Its filesystem roots and tenant/project bindings
are administrator supplied at construction and cannot be selected in Skill
JSON. The authenticated API requires `qa:write`, `qa:publish`, or
`qa:lifecycle` as applicable plus the exact project grant. It then persists the
transport-bound actor/request/trace authorization digest with the materialized
plan, then persists a distinct Skill 38 publisher authorization digest with the
published envelope. Direct service invocation is allowed only for
trusted in-process callers; it is not an authentication mechanism.

The authenticated Skill 37 binder authorizes sidecar output only. Embedded or
combined worktree materialization needs a separately authorized adapter because
it is a per-file mutation, not one atomic commit across roots. Controlled
low-level integrations that use those modes receive `atomic_publish: false`,
and replay revalidates the embedded bytes instead of assuming they survived.

Skill 37's in-memory emitter result is treated as another untrusted boundary:
the service rechecks the complete envelope, canonical DSL identity, artifact
bytes and hashes, lineage, scans, diffs, replay plans, manifest, path collision
policy, and execution boundary before descriptor-safe staging. Skills 38 and 39
use a per-project process and filesystem fence, an exact durable state schema,
immutable output identifiers (including collected tombstones), and physical
revalidation before lifecycle registration. A crash or ambiguous commit is
reported as unknown and is never silently retried as success. Unknown lifecycle
mutation outcomes do not receive terminal receipts; a caller must reconcile the
durable state before treating a retry as successful.

Atomic namespace commit and durable commit are separate states. If publication
renames the verified tree but either parent-directory sync fails, the output is
preserved as `COMMITTED_DURABILITY_UNKNOWN`; it is not eligible for lifecycle
registration or a higher evidence state until explicitly reconciled.

The SQLite chain heads detect local row mutation, reordering, and tail
truncation. They are not an independent transparency log or external anchor;
that evidence remains `NOT_RUN`.

## Adapter authority required

The following are never inferred from a Skill document or caller-supplied
command string:

- executing customer build or test code;
- provisioning an environment or reaching a network;
- applying a patch, modifying a branch, or writing a CI/SCM status;
- running database DDL, load, security, fuzz, chaos, or recovery operations;
- uploading or deleting object-store artifacts;
- signing manifests or release certificates.

Local, no-replace publication under the administrator-owned publication root
is distinct from object-store upload, SCM publication, signing, or release.
Those external effects remain outside the trusted local delivery service.

Local lifecycle collection deletes only the exact managed publication copy.
Private staging remains retained for local provenance/replay, and embedded
worktree files remain outside the collector's managed namespace. Results label
those embedded copies `UNMANAGED_NOT_VERIFIED`; they do not assert that the
files still exist, and never equate publication-copy GC with full project,
evidence, or object-store erasure.

Each requires a typed, allowlisted adapter, exact tenant/project binding,
idempotency, explicit authorization, and fresh raw evidence. A missing adapter or
attestation yields `BLOCKED` or `NOT_RUN`.

The local CLI derives its local actor identity from the operating-system
principal, refuses mutating Skill dispatch without a trusted tenant/project
scope binder, and does not expose approval or evidence-receipt mutation. The
authenticated API requires trusted tenant, actor, role, and project-grant
bindings; caller JSON cannot manufacture them. Caller-declared tool versions or
detected capabilities are rejected; only a trusted probe receipt bound to the
exact project snapshot and adapter profile can qualify an execution plan.

## Certification boundary

A locally green suite establishes engineering readiness only. Certification
requires an immutable artifact and environment, signed content-addressed raw
evidence, non-revoked trust, separate executor and verifier identities, complete
required corpora, and the applicable independent gate. Unknown, partial,
blocked, flaky, skipped, or not-run evidence never passes.
