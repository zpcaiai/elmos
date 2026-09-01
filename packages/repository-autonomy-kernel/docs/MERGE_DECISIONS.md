# Two implementations, one package: what won where, and on what evidence

Two sessions built the v2.0.0 31-skill contract independently. This package is
the merge. Nothing was decided from line counts — every row below comes from
reading both implementations and, where it mattered, running them.

## The shape of the merge

```text
src/elmos_repository_autonomy/   the platform:  store, external adapters,
                                 certification, deployment, HTTP, 32-table schema
src/elmos_repository_autonomy/kernel_bridge.py        the routing table
src/elmos_repository_autonomy/kernel_store_adapter.py the kernel's ports over DurableStore
src/elmos_autonomy_kernel/       the capability core: 31 modules, the algorithms
```

The dispatcher stays the single entry point. Per skill it consults the routing
table, and every result says which engine answered it (`ENGINE:kernel` /
`ENGINE:legacy`). `elmos-autonomy engines` prints the table with its reasons.

## Verdict by layer

| Layer | Winner | The evidence, not the impression |
|---|---|---|
| Capability algorithms | **core** | see the per-skill findings below |
| Capability tests | **core** | 1,420 vs 55 |
| Error taxonomy | **core** | 248 codes each with one category, checked at import, vs `ContractError(code, message)` |
| Canonical encoding | **core** | floats rejected outright, so a cache key cannot differ between two machines |
| Durable store | **platform** | SQLite store with transactional outbox/inbox + reconcile, backup/restore, tenant scoping |
| External world | **platform** | git and canonical SCM, S3 + presign, ephemeral secrets broker, durable event publisher, idempotent consumer, provider adapters — the core had ports and no adapters |
| PostgreSQL | **split** | platform: migration runner, disaster recovery, wave store, 32 tables. core: chain-verified log, fencing high-water mark, and a recorded crash-recovery run |
| HTTP surface | **platform** | server with identity verification + 4 OpenAPI contracts |
| Deployment | **platform** | Dockerfile, Helm, K8s, CI gates, and a Kubernetes *failure-injection* adapter |
| Certification E1–E5 | **platform** | trust anchors, evidence expiry, P05 evaluation — the core has none |
| Conformance harness | **platform** | the core has none |
| Repo gate wiring | **platform** | `make repository-autonomy-kernel` already exists and now covers both halves |

## Why each bridged skill routes to the core

These are the findings that decided it. Each one is a property of the legacy
implementation that reading it revealed:

- **repository-model-elo** — legacy computes `1000 + (win_rate - 0.5) * 400` in
  floating point. That is a win-rate rescale, not a rating system: no pairwise
  update, no K factor, so two contestants who never met get ranked against each
  other. The root cause is upstream — the legacy *input shape* is a flat list of
  per-candidate PASS/FAIL rows with no opponents in it, so Elo is not expressible
  there. The bridge promotes a payload that carries real matches; a flat payload
  still goes to the legacy path, which now labels its own output
  `method: win-rate-rescale, is_elo: false`.
- **agent-arena** — legacy scores each contestant by reading that contestant's
  own declared `quality` field. Nothing is executed, nothing is graded, and the
  contestant is not separated from the grader.
- **changegraph-vcs** — legacy hardcodes `"acyclic": True`; there is no cycle
  detection and no conflict detection. The core reports a real cycle as a
  strongly connected component with a witness path, naming only the changes
  actually in the cycle rather than everything the cycle blocks, and returns
  overlapping regions as a conflict instead of merging them.
- **incremental-semantic-index** — legacy accepts `previous_index` and never
  reads it; the index is regex-only across all languages and derives call edges
  from "this name appears followed by `(` anywhere in the file".
- **session-time-travel** — legacy `forked_run` is `{"status": "PLANNED"}` with a
  fresh uuid4: nothing forks, and two identical calls disagree. The core copies
  the prefix, records a FORK event naming parent and sequence, and leaves the
  parent timeline byte-identical.
- **repository-gym-golden-routes** — every legacy run is `NOT_RUN`
  ("native runner not supplied"), and acceptance is never frozen.
- **cost-eta-observability** — the core keeps machine wall-clock, human-equivalent
  effort and HITL wait in three types that cannot be summed, and reports an
  unmeasured component as unmeasured rather than as `0`.
- **layered-cache-fabric** — the one row where legacy is a *working* implementation
  rather than a stub, so the case had to be made narrowly. It reads and writes the
  tenant-scoped cache table; what is wrong is the key and the read. Its key is the
  seven parts v2 declares, omitting the prompt prefix digest and the environment
  fingerprint, so two computations differing only in prompt prefix collide on one
  entry and each serves the other's result. And a read returns whatever sits at
  the digest — nothing re-checks that the stored entry was produced under the
  parts being requested, so a collision or a drifted index is indistinguishable
  from a hit. The core keys on nine parts and re-verifies the entry before serving
  it. Promotion is deliberately narrow: a caller stating only seven parts, or
  storing through v2's `value` field, keeps the legacy cache untouched, because
  the honest translation of `value` (an admission refused for
  `COMPUTE_COST_UNMEASURED`) would still turn a working write into a non-write,
  and an explained downgrade is a downgrade.
- **contract-compatibility-engine**, **validation-dag**,
  **evidence-release-gate**, **artifact-evidence-protocol**,
  **independent-verification-mesh**, **policy-hook-kernel**,
  **workspace-lease-fencing**, **execution-authority-kernel**,
  **durable-run-orchestrator** — see the rationale strings in
  `kernel_bridge.py`, which are the authoritative version of this list.

## Where the legacy engine won, and kept the job

Merging honestly means recording these too. Each was found by an agent reading
both sides, and each changed the outcome:

1. **P05 attestation stays with `CertificationEngine`.** The core's release gate
   is better at *blocking* — NOT_RUN and SKIPPED are non-verdicts, the rollback
   plan must be complete, waivers expire — but its own attestation rests on an
   HMAC seal whose key is process-local, so anything able to reach the process
   could mint a bundle that verifies. The legacy gate structurally cannot issue
   P05 at all. The bridge takes the core's reasoning and keeps the legacy
   ceiling: `deployment_complete_attestation` is capped with a recorded
   `withheldReason`, and a test asserts no payload shape reaches an attested P05
   through the dispatcher on either engine.
2. **Durable, tenant-scoped artifact storage.** The core's binding of evidence to
   its input digests is far stronger; its *storage* defaulted to a process-local,
   un-tenanted dictionary. The bridge binds `DurableStoreArtifactStore` around
   the call, so the merge keeps both halves. Four tests pin it, including that the
   binding is restored on the exception path.
3. **`DurableStore.replay_state` is a real cross-check** — it folds the log and
   raises if the materialised row disagrees. The core's `replay()` has no stored
   row to compare against, so it structurally cannot make that check. It is now
   the last step of the orchestrator's persistence path.
4. **`gym()` answers a question the core refuses.** With no recorded runs the core
   raises; legacy enumerates the repository × spec cross product as `NOT_RUN`,
   which is the *plan* of what must be executed. That is what you want before
   anything has run, so that payload shape still routes to legacy.
5. **`demonstration()` scrubs secrets; the core only blocks.** `security.redact()`
   recursively replaces any key matching `secret|token|password|private.?key|
   authorization`. The core checks tool names and value prefixes, so a field
   literally named `authorization` passes unless its value starts with a declared
   prefix. Refusing rather than auto-redacting is defensible, but for a caller
   with one credential-shaped field, legacy produces a usable redacted draft.
6. **The lease-monotonicity claim about legacy was wrong.** `acquire_lease` mints
   `MAX(fencing_token)+1` over released rows too, so it *is* monotonic today. The
   rationale was corrected in place. It is monotonic but unenforced — a retention
   job pruning released leases would silently reintroduce the bug — so the store
   adapter keeps its own high-water mark and raises if the table ever hands back a
   non-increasing token.
7. **The curator order-independence claim was wrong.** Legacy groups on an exact
   code/category key, which cannot depend on ingest order either. A test now pins
   that, and the rationale was narrowed to the core's real advantage: similarity
   clustering and shipped-skill overlap detection.

## A pattern in the three blocked rows

All three are the same shape, and it is worth naming because it recurs: **the
legacy engine performs an action, the capability core adjudicates one that
already happened.** The core is right to be built that way — a kernel that
decides and attests is testable and pure, and the execution belongs behind a
port. But it means those rows are not "shallow vs deep implementations of one
thing" at all, and a bridge that treats them as such replaces a real effect with
a confident record of an effect. The core's depth there is genuine and belongs
in-process driving a live `ToolInvoker` or `ProcessRunner`; it does not belong
behind a JSON dispatcher whose callers expect the tool to run.

## Defects fixed during the merge

- `costeta` filtered `run_events.requiredPhases` against the known phase set, so
  an unrecognised required phase was **silently dropped** and coverage then looked
  complete by deleting the requirement it had failed. It is now a rejection.
- The kernel path was dropping the `steps` rows and the `policy_decisions` audit
  row that the legacy handlers write. Both restored, both tested.
- `compile_ir` reported `status: COMPILED` whenever the index it was handed
  merely *lacked* a `partial` flag. It wraps index symbols in
  `{"preserve": True}` and lowers nothing, so it can never be COMPILED; it now
  fails closed and requires an index to positively assert completeness. Found by
  routing a different skill to the core — the core's index has no `partial`
  flag, and the legacy IR immediately started claiming it had compiled.
- Renaming the core's tables to `autonomy_kernel_*` (so `autonomy_event` no
  longer sits beside the control plane's `autonomy_events`) missed a TRUNCATE in
  a test helper and a DELETE in the evidence script. All 1,543 in-memory tests
  passed; only a real server objected. `tests/test_schema_adapter_agreement.py`
  now asserts statically that every table named in SQL is created by some
  migration, that `001_autonomy_kernel.sql` is exactly the union of the
  migrations, and that no core table differs from a control-plane table by the
  prefix alone.
- The repository gate `tooling/validate_repository_autonomy_kernel.py` pins asset
  counts and migration digests. V007 tripped it. Fixed by teaching the gate the
  new migration and the five new tables, and by pinning V005/V006 — which had
  shipped unpinned, a gap in exactly the mechanism that exists to catch drift.
- **Two configuration bugs in the cache bridge that each looked like strictness.**
  The bound fabric was first pinned to a placeholder snapshot, so every key was
  refused as `STALE_SNAPSHOT`; then it was bound with the core's fail-closed empty
  `AdmissionPolicy`, so every class was refused as `CLASS_NOT_CACHEABLE`. Each
  guard was individually correct and each produced a cache that never hits — a
  zero hit rate reads as a property of the workload, not as a misconfiguration,
  which is why neither would have surfaced as a bug report. The fix was a fabric
  built against the snapshot and policy the request states, and an admission
  policy the bridge names and owns. `test_a_stored_entry_is_served_back_to_an_identical_key`
  is the test that dies under either mutation.
- **The model router ranks an unpriced model first.** `score = quality / (cost +
  latency/100000)` with `cost_per_call` defaulting to `0`, so a profile that
  declares no price is scored as free and outranks every priced model — measured
  at 50000 vs 31 for a *better* priced model, which then loses. The float
  arithmetic also means two hosts can order the same two models differently. The
  defaults are kept because callers depend on this handler answering, but the
  output now carries `unpriced_models`, `reproducible: false` and a
  `scoring_note` saying both things, and `policy_hash` is documented as covering
  the provider policy only — not the registry the decision was made against.
- **A wrong claim about the legacy cache, in the routing rationale itself.** It
  said legacy had "no layer, no lookup and no admission decision — a key, not a
  cache". Legacy reads and writes the tenant-scoped cache table; it is a working
  cache. Its two real defects are narrower and worse: a seven-part key that
  collides across prompt prefixes and environments, and a read that never
  re-verifies the entry it returns. Corrected in the routing table. This is the
  third time in this merge a legacy capability was under-described in its own
  replacement's justification.

## The cross-engine status downgrade

This is the defect class that cost the most to find, so it gets its own section.

The legacy handlers fold a *verdict* into the dispatch status: a policy DENY is
`BLOCKED`, a validation plan that dropped a required check is `BLOCKED`, a
breaking contract change is `BLOCKED`, a spec with a HIGH ambiguity is `BLOCKED`.
The kernel does not. It reports the verdict in its outputs and returns
`SUCCEEDED` for the *computation* — which is correct for the kernel: it was asked
to evaluate a policy and it evaluated one.

Routing such a skill to the kernel therefore converted `BLOCKED` into
`LOCAL_ENGINEERING_VALIDATED` for callers who never asked for a different engine
and cannot see that they got one. A safety signal changed meaning because of an
implementation swap.

`compile_ir` was the first instance and was caught by an unrelated test. Four
more were found by auditing every legacy handler that returns a non-validated
status and driving each bridged row down its failing path:

| skill | what reported as validated |
| --- | --- |
| `policy-hook-kernel` | an action policy **denied** |
| `validation-dag` | a plan that trimmed **four required checks** for budget |
| `contract-compatibility-engine` | a **breaking** change the caller's own policy called blocking |
| `task-spec-delta-compiler` | a spec with a **blocking ambiguity** |

`evidence-release-gate` and `independent-verification-mesh` were checked and are
safe: the kernel *raises* (`ACCEPTANCE_REJECTED`, `EVIDENCE_UNVERIFIABLE`) rather
than returning a softer status, so those failures were never silent.

The fix is `BridgeSpec.blocked_when`: a predicate over the kernel's outputs that
restores the verdict. It can only move a status **towards** `BLOCKED` — a hook
that could clear a block would be a way for the bridge to overrule a verdict,
which is exactly what rule 1 below forbids, in the direction that ships the
break. Each of the five has a regression test; the validation-dag one also
asserts that trimming an *optional* check is not a block, because a rule that
blocks on every trim makes the budget unusable.

## How the bridge stays safe

Four rules, enforced in `kernel_bridge.serve`:

1. A core **domain** rejection is never downgraded to a legacy success. Letting
   the shallower engine overturn a correct rejection is worse than having no core.
2. A core **decode-level** refusal (`MALFORMED_INPUT`, `MISSING_REQUIRED_INPUT`,
   `UNKNOWN_FIELD`, `INPUT_TOO_LARGE`) is a gap in *this bridge's translation*,
   not a verdict about the caller. It falls through to legacy and the gap is
   recorded as `KERNEL_INPUT_UNMAPPED:<code>` — countable, never silent.
3. A verdict the legacy handler expressed as a **status** is restored from the
   kernel's outputs by `blocked_when`, in the blocking direction only. See the
   section above.
4. An adapter may **derive** a field implied by what the caller sent. It may never
   **invent** one. Deriving an environment fingerprint from the submissions it is
   meant to police, or a policy hash from the layers it is meant to pin, turns the
   check into a tautology — so those adapters refuse and route to legacy instead.

## Consolidation debt, stated plainly

- ~~**Two event logs.**~~ **Corrected — the premise was wrong, and the real
  finding is larger.** This was recorded as "V001–V006 is the control plane's log,
  V007 is the core's; unify them". Measuring it says there is no second live log
  to unify with. Nothing in the package writes to `autonomy_events` — or to
  `autonomy_runs`, the root table it and twenty others foreign-key to. **22 of
  the 37 tables `postgres-migrate` applies have no writer anywhere.**

  What exists is a persistence *split*, not a schema conflict:

  | | tables | who writes them |
  | --- | --- | --- |
  | SQLite `DurableStore` | 27, bare names (`runs`, `events`, `leases`) | every skill handler — `AutonomyRuntime.store` is always this |
  | PostgreSQL `autonomy_*` | 37 | only `PostgresWaveStore` (10) and the core's adapters (5) |

  Measured directly: a dispatch sequence exercising the lease and cache paths
  writes three SQLite tables and **zero** PostgreSQL rows, with the migrations
  fully applied to a live server. An operator who runs `postgres-migrate` gets a
  schema describing a run history that is in a SQLite file under different
  names — and a schema that advertises a control plane which is not there gets
  read, believed, backed up and audited.

  Not silently redesigned here, because implementing 22 tables against
  PostgreSQL or withdrawing them is an architecture decision, not a cleanup.
  What is done: `tests/test_persistence_split.py` pins both lists by name so
  neither can move without the other, `V001`'s header says plainly that these
  tables stay empty, and the README says where data actually goes.
- **10 of 31 skills answer from the legacy engine, and every one now has a
  written reason.** `elmos-autonomy engines` prints both tables:
  `rationales` for the 21 routed rows, `legacyRationales` for the 10 that are
  not. Three of the ten are marked `blocked: true` — promoting them would make
  the package *worse*, and that only counts if it is recorded where an operator
  reads it:

  | skill | why promotion is refused |
  | --- | --- |
  | `typed-tool-runtime` | the legacy handler **runs the tool**; the core wires a `_StaticInvoker` over the caller's own `tool_output` and never invokes. A v2 caller would get a SUCCEEDED tool-call record, idempotency key and all, for a tool that never ran. |
  | `two-phase-secretless-sandbox` | the core requires a `runner_result` from a transport that already executed — it decides and attests, never spawns. v2 *plans* an execution. Promoting means attesting a sandboxed run that never occurred. |
  | `tiered-security-assurance` | the core grades `control_reports` and expiring `waivers` and raises on any non-PASS; v2 supplies neither, so every call would fail closed on "controls not run". A gate that refuses everything trains operators to route around it. |

  The other seven are translation gaps with the specific missing field named —
  the router cannot be promoted without fabricating per-Mtok prices and a
  reliability prior; the context planner cannot without fabricating a token
  count. Two tests pin this: every legacy row has a rationale, and the blocked
  set is pinned by name so promoting one is a deliberate edit.
- **The cache fabric's freshness pin is request-derived.** A long-lived server
  builds the fabric once against the tree it serves, so `STALE_SNAPSHOT` catches
  a caller asking about a tree that has moved on. Here the fabric is built and
  discarded inside one dispatch and `DispatchContext` carries no snapshot
  identity, so there is no independent live-tree fact to pin against; the pin
  comes from the request's own key parts and that guard cannot fire. What
  survives intact is the guarantee the skill exists for — snapshot and policy
  are two of the nine key parts, so an entry from another snapshot is never a
  hit candidate. The response says so in `provenance.freshnessPin` rather than
  reporting a pin that reads as verification. Giving `DispatchContext` a
  snapshot identity would restore the guard, and is the follow-up.
- **The cache metrics are per-call.** The fabric does not outlive one dispatch,
  so `hitRatePerMille` is 0 or 1000 and nothing else. Disclosed as
  `cache_metrics.scope`; a deployment hit rate needs aggregation the bridge does
  not do.
- **This package re-implements capabilities elmos already has, and two routing
  rationales were written without looking.** Every rationale in
  `kernel_bridge.py` compares the capability core against the *v2 legacy handler
  in this package* and nothing else. For two rows that reached the right verdict
  for the wrong reason — the core does beat the legacy handler, and both lose to
  an implementation sitting in the same repository:

  - `layered-cache-fabric` vs `engines/build-cache-engine` (86k lines, 74 test
    files): 17 key dimensions against this row's nine, and the two dimensions
    this merge argued were the whole justification for promoting the row — a
    prompt-prefix digest and an environment fingerprint — are already in it. It
    also audits undeclared environment reads as a hermeticity bug, refuses
    secret-looking values into a key, and prices admission against restore cost
    and tenant quota.
  - `contract-compatibility-engine` vs `packages/repository-refactoring/apicompat.py`:
    separates source-break / binary-break / wire-break / behavior-risk against
    this row's BREAKING/RISKY, and knows wire tags — which the rationale claimed
    as the core's advantage.

  Both rationales now carry a `SCOPE OF THIS CLAIM` paragraph saying what they
  were and were not compared against. The full survey, with the per-capability
  verdict, is `docs/EXISTING_CAPABILITY_OVERLAP.md` — and it does **not** say
  "wire everything": `phase-aware-model-router` measures the other way (the
  existing implementation ranks on binary floats; the kernel uses `Decimal` with
  a hashed decision), and `cost-eta-observability` is complementary rather than
  duplicate. The wiring itself stays open: each row is a cross-package change
  into a package this one neither depends on nor tests, and `build-cache-engine`
  is not gated by the root Makefile on its own.
- **The core's incremental index is not reachable over this JSON dispatcher.**
  `incremental()` requires the prior index as a live object, because the core
  cannot verify that a hand-assembled index is one it produced and an
  incremental update against a forged prior is worse than a full rebuild. So the
  property holds in-process and the adapter does a full build over the wire
  rather than pretending. Narrower than the v2 contract implies; recorded here
  rather than hidden behind a silent downgrade.
- **The core's seal key is a process default.** Before any deployment it must be
  an out-of-band secret, not a constant.
- **`ctx.authority` is not set on the core's authority path**, because the legacy
  `ExecutionAuthority` has no expiry field and translating a TTL-bounded authority
  into it would silently drop the bound. Nothing chains those two skills today; a
  caller who builds that chain gets a loud error rather than an unbounded
  authority. Worth a decision if that chain is ever built.
