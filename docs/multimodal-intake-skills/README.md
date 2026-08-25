# Multimodal Intake Skills integration

This integration treats `elmos-multimodal-intake-skills-v1.0.0.zip` as an
untrusted, immutable specification package. It does not treat the package's
Markdown instructions, shell/PowerShell installers, Python utilities, or eval
declarations as executable repository authority.

## Pinned source identity

| Property | Required value |
|---|---:|
| Archive | `skills/subskills/elmos-multimodal-intake-skills-v1.0.0.zip` |
| SHA-256 | `23f9f2cee63e2fb1a43f85df539942e92077db2c58ddd75a8a0854773eb1c90b` |
| Compressed bytes | 664,179 |
| ZIP entries | 346 |
| Total uncompressed bytes | 1,117,974 |
| Internal checksum rows | 345 |
| Canonical Skills | 50 |
| Acceptance criteria | 240 |
| Required deliverables | 170 |
| Global gates | 8 |
| Dependency edges | 95 |
| Cyclic dependency SCCs | 3 |

The package contains canonical `skills/` plus byte-identical
`.agents/skills/` and `.claude/skills/` mirrors. It contains specification,
policy, Schema, documentation, and packaging utilities; it does not contain the
runtime implementation of the 50 functions or executable acceptance evidence.

## Importer

The importer uses only the Python standard library:

```bash
make multimodal-intake-skills
# equivalent explicit stages:
python3 tooling/integrate_multimodal_intake_skills.py --write
python3 tooling/integrate_multimodal_intake_skills.py --check
```

`--write` performs these bounded operations:

1. Reads the entire ZIP into a pinned in-memory snapshot and verifies its exact
   SHA-256 before trusting the central directory.
2. Rejects duplicate, encrypted, absolute, traversal, backslash, control-name,
   case/Unicode-colliding, symlink, and special-file entries.
3. Verifies exact entry and byte counts, all 345 internal SHA-256 rows, all
   three Skill trees, all 50 contracts, the 240/170/8 acceptance counts, and
   the three known dependency SCCs.
4. Extracts each regular file through exclusive, no-follow creation into a
   staging directory. It never calls `extractall` and never imports or executes
   package content.
5. Publishes all generated targets as one locked, journaled transaction. The
   durable `journal-v1` records `INTENT`, `BACKED_UP`, `PUBLISHED`, and
   `VERIFIED`; directory `fsync` and strict physical-state validation allow a
   later `--write` to recover a crash without overwriting third-party drift.
   `--check` is read-only and fails closed while a stale transaction exists.
6. Publishes the immutable source tree at
   `skills/elmos-multimodal-intake-skills-v1.0.0`. An existing exact tree is an
   idempotent no-op; an existing drifted tree fails closed.
7. Installs canonical Skill directories byte-identically to `.agents/skills`
   and `agent-skills/runtime`. Existing mismatches are not overwritten. A
   managed runtime-digest upgrade is permitted only when both old roots and
   both old manifests can be reconstructed exactly; any user drift blocks it.
8. Statically parses, but does not import, the runtime engine and binds its
   exact file digest and 50 registry entries into generated manifests.

The runtime digest closure includes the SQLite knowledge migration, durable
knowledge/project-memory implementation, fail-closed archive publisher, all
engine security tests, and the browser/BFF verification surfaces. Adding a
runtime file without adding it to that explicit closure fails the importer.

`--check` performs the same identity and contract validation, then verifies
the immutable source, both installed roots, runtime registry, implementation
matrix, and generated manifests without writing.

The generated files are:

- `docs/multimodal-intake-skills/compiled-manifest.json`
- `docs/multimodal-intake-skills/installed-manifest.json`

They are derived outputs and bind the current engine file SHA-256. Any engine,
contract, Skill, installation, or manifest drift causes `--check` to fail.

## Runtime binding

The implementation entrypoint is:

```text
engines/multimodal-intake-engine/src/elmos_multimodal_intake/skill_runtime.py
```

The importer statically requires a literal `SKILL_REGISTRY` with exactly 50
entries. Each key is the complete Skill name and each value must be the
runtime's exact four-argument static `_entry(ordinal, skill, phase, handler)`
form. It also requires the exact frozen five-field `HandlerBinding` dataclass
and pins the helper implementation, ordinal, Skill identity, execution phase
and callable. Every handler is an undecorated synchronous function with one
required `request` argument. Rebinding or shadowing the helper, binding class,
builtins, registry, or handler names is rejected. The registry cannot escape
through an alias; writes, deletion, in-place union, special-method mutation,
and dynamic namespace operations are rejected. Its only permitted runtime
reads are `len`, `get`, `items`, and `values`. All 50 callables must be unique
and defined in the same file. Handler IDs are the callable names and are
deterministic:

```text
elmos-secure-resumable-upload -> execute_secure_resumable_upload
```

Skill 26 additionally owns the versioned 50-Skill/147-operation public
registry. Unknown operation pairs fail closed as `REQUIRES_ADAPTER`; the
OpenAPI request/result discriminator and Python, TypeScript, and Java SDK
mirrors are checked for drift. Generic execute methods remain low-level
transports and cannot bypass registry validation. Boundary errors always carry
a bounded `trace_id`.

Skills 38, 41-43 and 46-50 additionally share the migration-020 durable
project-package lifecycle. The server accepts bounded manifest chunks, persists
exact package versions with entry digests and a Merkle root, returns
scope/version/digest-bound page cursors, and computes incremental changes only
for an explicit old/new version pair. Workbench preview consumes those server
pages instead of truncating a client-side list. Each upload confirmation carries
canonical base64 bytes: the server recomputes part size and SHA-256, stores the
bytes in tenant CAS, then rereads every part in order and verifies the negotiated
whole-file byte count and digest. Status stays `PARTIAL` until the final CAS
object exists. Audited role/model-read override and undo cannot weaken security
isolation; all derived indexes bind a package version and preserve honest
`PARTIAL` states.

Every referenced function must be defined in that same source file. Static AST
inspection avoids import-time side effects from the runtime engine.

The exact Skill-to-handler-to-phase-to-acceptance mapping is
[`implementation-matrix.json`](implementation-matrix.json). The matrix is a
coverage contract, not evidence that a handler or acceptance criterion passed.

Skills 14-16 use an independent, permission-hardened
`content_projection.sqlite3` store in production composition. Requirement,
fusion and conflict projections bind a host-verified package version plus the
exact source content, provenance and version digests. Versions and outbox facts
are immutable and tenant/project scoped; idempotency replay rejects source or
output drift. Critical conflicts and low-confidence output remain
`NEEDS_REVIEW`, and caller-authored approval, verification or resolution fields
cannot manufacture authority. Source documents are not copied into the source
ledger or telemetry.

At execution time, Skills 20 and 37 use a tenant/project/actor/branch/package
scoped SQLite store with versioned records, ACL filtering, outbox events,
deletion propagation and local lexical rebuilds. Skill 44 publishes only after
the original archive obtains an exact byte-bound CLEAN receipt before parser
entry, and every extracted entry obtains its own CLEAN receipt. The complete
content/receipt set becomes readable through one tenant-scoped atomic CAS
generation; failed writes never expose a partial generation. Missing
vector infrastructure or malware-scan capability remains explicit as
`PARTIAL`/`NOT_RUN`; static integration metadata never upgrades it.

Skill 27 uses migration 018 and a runtime bridge. `delete` persists one exact
job plus one command for every trusted-inventory store/object/version tuple.
Legal holds and backup lag block dispatch. Inventory booleans and arbitrary
digest-shaped values are not deletion evidence: an unforgeable runtime worker
capability records a byte/digest-bound execution receipt, then a separate
verifier capability and verifier identity attest observed absence. Execution
alone becomes `UNKNOWN`; only all independently verified commands can produce
the immutable deletion proof and `deletion.completed` outbox event. The audit
ledger stores content-free event digests separately. Provider adapters and
external stores remain `NOT_RUN`, so this local workflow is not production
deletion certification.

Skills 22-23 use migration 021. Cost/ETA snapshots persist exact-decimal line
items by subject, stage, asset and provider, while estimates and actual charges
remain separate. Provider actuals become `RECONCILED` only from an exact-scope,
byte/digest-bound host verification receipt; otherwise they remain `PENDING`
or `UNKNOWN`. Telemetry stores only allowlisted, redacted attributes in an
immutable trace/event ledger. The Workbench exposes an explicit refresh action
for P50/P95 machine-wall-clock ETA, estimated cost and actuals state; missing
trusted calibration or prices fails closed and is never automatically retried.

Skill 28 uses migration 022 and a bridge-only downstream boundary. Contexts are
built solely from opaque host receipt IDs covering normalized content,
requirements and repository maps. Tool grants are tenant/project/context/input
digest bound, short-lived, revocable and single-use. The host-composed Tool
Gateway is the sole PEP and selects only allowlisted adapters; public input
cannot select a command, module, plugin, subprocess, raw asset or capability.
Execution outcomes remain reconciliation-required until an independent result
verifier produces an immutable receipt, after which an explicit result-link
operation records provenance and a durable outbox fact.

Skills 29-36 and 39-40 use migration 019 in production composition. Capability
snapshots retain provider/model version history and a scoped rollback head.
Usage rows do not conflate current-window input/output reservation, cumulative
provider input/output, or cumulative minor-unit cost. Pressure rows bind prior
state, hysteresis, forecasts, action, policy version and an outbox event.
Compaction preserves original history in tenant CAS and publishes a structured
checkpoint only after persisted integrity passes. Checkpoint list/diff/restore/
rollback use immutable, idempotent recovery attempts; retries cannot duplicate
effect or cost cursors. Rehydration reads real CAS bytes and validates tenant,
project, package version, hash, byte count, source anchor and token budget.
Failed or missing integrity evidence denies side-effect authorization, and
request-authored authority fields fail closed.

Skill 24 is also a runtime bridge rather than an in-memory report formatter.
Its independent `evaluation.sqlite3` schema and content-addressed evidence root
persist authorized dataset/rubric versions, exact subject tuples, runs, derived
case results, and independent verification receipts without colliding with the
core IntakeStore migration sequence. The runtime-owned evaluator allowlist has
no shell or dynamic-import path. Raw evidence is rehashed from bytes on both
execution and verification; caller-authored pass/fail, digest, byte-count, score,
or verifier metadata is rejected. The package's 240 exact acceptance IDs are an
explicit source-digest-bound catalog and all external obligations remain
`NOT_RUN`/`NOT_CERTIFIED` until real qualified evidence exists.

## Dependency cycles

The source contracts contain these exact strongly connected components:

```text
{elmos-context-budget-manager, elmos-multimodal-token-accounting}
{elmos-context-checkpoint-and-recovery,
 elmos-context-integrity-and-loss-detection,
 elmos-context-pressure-monitor,
 elmos-structured-context-compaction}
{elmos-downstream-agent-integration, elmos-prompt-injection-defense}
```

They are preserved as source facts. Runtime implementation should break
compile-time cycles through stable ports/events; the importer must not rewrite
the attached contracts to conceal them.

## Evidence boundary

Current integration metadata deliberately remains:

```text
external_evidence_status = NOT_RUN
certification_status     = NOT_CERTIFIED
```

Archive identity, static contracts, installed file equality, AST handler
binding, and local tests are engineering evidence only. They do not establish
real OCR/ASR/provider behavior, parser sandbox isolation, browser/device UI,
large-corpus performance, recovery, tenant isolation, archive attack-corpus
results, production operations, external review, or certification.

The implementation tests are defined in
`tests/multimodal-intake/test_integration.py`. The importer never executes an
archive payload, installer, or package script; repository qualification runs
separately and retains its observed evidence state.
