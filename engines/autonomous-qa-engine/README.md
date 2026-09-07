# Elmos Autonomous QA Engine Core

This package is the dependency-free Python core for durable autonomous-QA run
control and safe artifact publication. It implements repository-local
engineering behavior; it is not a production runner, signer, deployment
service, or certification authority.

## Safety boundary

- SQLite run commands are tenant-scoped and idempotent, including denied
  transition replay. Stored run payloads and idempotency responses are
  digest-revalidated.
- Illegal run transitions fail closed and are audited. Event/audit chains have
  persistent local heads; independent external anchoring remains `NOT_RUN`.
- Approval consumes a non-revoked, unexpired receipt bound to the exact tenant,
  project, run, approval-request audit digest, expected run version, scope,
  subject, artifact, authorization, executor, and independent verifier
  identities. A receipt is one-use and consumed atomically with approval.
- Artifact paths are normalized relative paths. Symlinks, path traversal,
  Unicode/case collisions, unmanifested files, secrets, placeholder tests,
  disabled tests, and assertion-only tests are rejected.
- Bundles contain only registered files, use normalized metadata, and are
  extracted into a clean temporary directory for byte-level verification
  before atomic publication.
- Shell commands, source scripts, SQL, package-manager hooks, and generated
  project code are always inert data in this core and are never executed.
- Snapshot resource limits can only be tightened. Skipped symlinks, special
  files, or oversized files make inventory completeness false, and caller
  tool-version/detection assertions cannot qualify adapter command proposals.
- Callers may request only `verified` publication. `partial` or `failed` status
  is engine-derived from a captured publication failure and is bound to that
  failure's exact type-and-message envelope; caller-declared non-success status
  is rejected before materialization. `certified`, signatures, releases, and
  deployments require a separately authorized external gate with independently
  verified evidence and are deliberately rejected here.
- Garbage collection is tenant-scoped, legal-hold-aware, reference-safe,
  quarantine-first, crash-recoverable, and dry-run by default.
- A completed no-replace rename whose parent-directory sync fails is returned
  as `COMMITTED_DURABILITY_UNKNOWN`; the committed tree is preserved, but it
  cannot enter lifecycle management until durability is independently
  reconciled.
- Skills 37-39 cross a separate trusted-delivery boundary. The pure Skill 37
  emitter is fully revalidated and digest-bound before staging; a generated
  provenance artifact binds its exact emission and trusted runtime identity.
  Skills 38 and 39 remain blocked unless the authenticated API is configured
  with administrator-owned staging, publication, lifecycle, state, and
  tenant/project embedded roots.
- Trusted delivery uses an exact SQLite schema plus a per-project process/file
  fence. Active publication cannot be mistaken for a crashed publication,
  lifecycle side effects are serialized with their receipts, collected output
  identifiers remain reserved, and uncertain commit outcomes stay explicit.
  An unknown lifecycle mutation does not receive a terminal idempotency receipt;
  it remains blocked with reconciliation required.

## Public API

`elmos_autonomous_qa.control_plane` exports `QaControlPlane`, `QaRun`,
`QaEvent`, `AuditRecord`, `VerifiedEvidenceReceipt`, and `RunStatus`.

`elmos_autonomous_qa.artifacts` exports `OutputPlan`, `OutputMode`,
`ArtifactPublisher`, `ArtifactRecord`, `PublishedOutput`, and
`ArtifactLifecycleStore`.

`elmos_autonomous_qa.canonical` exports strict JSON parsing/canonicalization,
SHA-256 helpers, and relative-path validation helpers used by both layers.

`elmos_autonomous_qa.skill_runtime` binds every installed
`$autonomous-qa-*` Skill to one exact repository-owned callable.
`elmos_autonomous_qa.api` exposes an authenticated in-process API whose tenant
and actor identity plus exact project grants must come from a trusted transport.
`elmos_autonomous_qa.delivery_service` exports `TrustedDeliveryService` and its
exact pure contracts for Skills 38 and 39. Direct service calls are a trusted
in-process boundary; an untrusted transport must call through `QaApi` with a
transport-derived `TrustedIdentity`, never construct authorization context from
request JSON.
`elmos_autonomous_qa.release_boundary` exports the local-only
`prepare_external_execution`, `prepare_independent_verification`, and
`prepare_certification_review` contracts. They bind tenant/project, immutable
digests, authorization references, idempotency keys, and executor/verifier
fences, but never invoke a provider, runner, verifier, signer, network, or
subprocess. A trusted service may consume their plans and attach independently
verified receipts out of process.
The authenticated Skill 37 binder permits sidecar output only. Embedded or
combined worktree mutation requires a separately authorized adapter. The
lower-level trusted service can model those modes for controlled integrations,
but reports their per-file materialization as non-atomic and revalidates the
embedded bytes on replay.
`elmos_autonomous_qa.cli` provides structured-JSON dispatch for non-mutating
Skills, project snapshots, and local durable run operations through the
`elmos-autonomous-qa` entry point. It rejects mutating Skill dispatch because a
local OS identity is not a trusted tenant/project authorization binder. It also
intentionally does not expose evidence registration, receipt revocation, or
approval.

Examples:

```bash
elmos-autonomous-qa skills
elmos-autonomous-qa execute autonomous-qa-02-spec-normalization --request request.json
elmos-autonomous-qa snapshot /explicit/project/root --required requirements.json
```

All Skill results keep external evidence at `NOT_RUN` and certification at
`NOT_CERTIFIED`. Commands that require a real runner, SCM, CI, signer, or
external verifier return a typed external-adapter requirement instead of
executing caller-supplied commands.

The release-boundary plans expose `READY_FOR_EXTERNAL_GATE` only after local
structural validation. They include required evidence roles and replay/fence
digests; they do not manufacture durable receipts, signatures, independent
verification, production effects, or certification.

Lifecycle collection owns only the immutable managed publication copy. Its
result names that exact deletion scope, reports private staging as retained,
and labels any embedded worktree copy `UNMANAGED_NOT_VERIFIED`; it never
represents managed-copy GC as a full worktree or evidence erasure.

The test suite uses only `unittest` and temporary directories. Runtime code
has no third-party dependencies.
