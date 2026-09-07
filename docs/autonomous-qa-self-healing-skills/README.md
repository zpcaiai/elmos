# Autonomous QA and Self-Healing Skills

This integration turns the supplied `elmos-autonomous-qa-self-healing-skills-v1.1.0.zip`
reference package into a collision-safe Codex Skill distribution and a
repository-owned, fail-closed local runtime.

## Source identity

- Archive: `skills/subskills/elmos-autonomous-qa-self-healing-skills-v1.1.0.zip`
- SHA-256: `07928b59925c80b1b158cce42e729ee97510172676989badf7dd656971a56ae2`
- Inventory: 125 files, 298,308 uncompressed bytes, 40 Skills, 67 dependency edges,
  11 JSON Schemas, and 6 workflows
- Immutable extraction: `skills/elmos-autonomous-qa-self-healing-skills-v1.1.0/`
- The archive contains no repository-trusted license, signature, SBOM, or
  provenance attestation. Its pinned digest establishes byte identity only.

Archive documents, prompts, workflows, Python tools, replay scripts, and SQL are
untrusted specification input. The importer validates and preserves their bytes
but never executes them. Each source Skill is compiled to the deterministic
alias `$autonomous-qa-<source-id>` under both `.agents/skills/` and
`agent-skills/runtime/`. Installed `SKILL.md` files are repository-owned
wrappers: they do not embed or activate source prose, descriptions, workflow
steps, or prompts. The immutable extraction remains the only place where those
untrusted bytes are preserved for review.

## Executable implementation

`engines/autonomous-qa-engine/` provides the reviewed local implementation:

- exact typed dispatch for all 40 Skills, with an independent source/phase/
  mutation/operation binding contract and runtime-module digest;
- bounded project snapshot discovery and normalized requirements;
- traceability, risk planning, test DSL, and domain-specific test plans;
- durable tenant-scoped run state, audit events, command idempotency, pause,
  resume, cancel, retry, and approval controls backed by digest-chained events,
  audit heads, and tenant/run/scope-bound independently verified receipts;
- native-layout adapter contracts for the declared language ecosystems;
- fail-closed evidence, flaky-test, defect, repair, impact, gate, reporting,
  checkpoint, ETA, governance, and lifecycle decisions;
- immutable descriptor-read artifact snapshots, atomic no-replace publication,
  deterministic bundles, extraction revalidation,
  secret/path/symlink/collision checks, partial failure outputs, and reference-safe
  quarantine/recovery retention.
- a trusted Skills 37-39 service binder with exact revalidation of the complete
  Skill 37 emitter contract, an emission/authorization provenance artifact,
  administrator-owned roots, a private exact-schema SQLite state store,
  per-project process/file fencing, crash-explicit publication reconciliation,
  and non-reusable collected output identities.

Callers may request only `verified` publication; caller-declared `partial` or
`failed` status is rejected before materialization. Those non-success states are
engine-derived only from a captured publication failure and carry its exact
type-and-message envelope. Plan-only publication never materializes a project
tree. Every published artifact must be retained by an exact sidecar, embedded
destination, or required bundle, and lifecycle verification checks the complete
output inventory rather than trusting a manifest alone.

Local handlers do not turn source workflow action strings into commands. Test
execution, code patching, SCM updates, CI status publication, object-storage
publication, signing, and external verification require explicit typed adapters
and their own authorization. Unsupported or unavailable capabilities remain
`NOT_RUN` or `BLOCKED`.

The generic Skill dispatcher keeps Skills 38 and 39 blocked behind pure
contracts. Actual local staging, publishing, and lifecycle mutation is available
only when `QaApi` is explicitly configured with `TrustedDeliveryService`. The
transport must derive `TrustedIdentity`, roles, and exact project grants from an
authenticated resource binding. Caller JSON cannot select service roots or
manufacture the persisted authorization context; direct service access is a
trusted in-process integration boundary, not a public API.

The authenticated binder accepts sidecar materialization only. Embedded or
combined worktree writes require a separately authorized adapter because their
per-file effects cannot be represented as one cross-root atomic publication.
The lower-level trusted service reports those modes as non-atomic and verifies
their bytes on replay. Lifecycle collection is scoped to the managed
publication copy; it reports private staging as retained and embedded worktree
copies as `UNMANAGED_NOT_VERIFIED` rather than claiming either their retention
or their deletion.

Caller-supplied adapter detection and version fields are rejected rather than
treated as qualification evidence. The test DSL accepts no qualification field
and may return only a repository-template command proposal; it remains
`PARTIAL` with trusted toolchain probing `NOT_RUN`. The local CLI also refuses
mutating Skill dispatch because it has no trusted tenant/project scope binder.

Project snapshot limits may be tightened but never broadened beyond the
repository maxima. A skipped symlink, special file, or oversized file makes the
inventory explicitly incomplete and causes the CLI snapshot command to return
non-success.

## Validation

The repository target is:

```bash
make autonomous-qa-self-healing-skills
```

It checks the pinned archive, immutable extraction, source checksums, source DAG,
compiled contracts, dual-root Skill identity, the exact 40-handler registry,
and the autonomous QA engine tests. It never runs the archive's bundled tools or
replay script.

The deterministic implementation matrix, compiled manifest, and installed
manifest are importer-owned files under `generated/`. The surrounding Markdown
documents are reviewer-owned and are intentionally outside the importer's
replacement boundary.

Package integrity, local implementation, external runtime evidence, and
certification are independent states:

| Dimension | Meaning | Current maximum |
|---|---|---|
| Source integrity | Pinned ZIP and internal inventories match | `VERIFIED` |
| Installed Skills | Normalized aliases and provenance match | `INSTALLED` |
| Local runtime | Repository-owned contract tests execute | `LOCAL_EXECUTED` |
| External evidence | Real browsers/devices/load/security/chaos/SCM/signers | `NOT_RUN` |
| Certification | Independent trusted decision for an exact artifact | `NOT_CERTIFIED` |

The public JSON Skill gate rejects caller-supplied certification assertions and
therefore remains `BLOCKED` until a repository-trusted receipt adapter exists.
The lower-level typed evaluator may prepare `READY_FOR_EXTERNAL_GATE` only from
already validated internal evidence; neither surface can certify a product
release, approve a repair, merge a branch, deploy, or manufacture evidence.
Privileged evidence registration, revocation, and approval are deliberately not
CLI commands; they require a trusted authenticated API identity, an exact
project grant, and a one-use approval-request-bound receipt.
