# Where this package re-implements something elmos already has

Recorded debt said: *"wire the 9 capabilities that overlap existing elmos code
(`modules/cas`, `build-cache-engine`, `execution-intelligence`,
`repository-refactoring`) instead of keeping a second implementation."*

That note assumed a direction — that the existing code is the one to keep. The
measurements below say the direction is **different per capability**, and in one
case the opposite. So this is a survey with a verdict per row, not a wiring
plan with nine identical steps.

It also records something uncomfortable. Every routing rationale in
`kernel_bridge.py` was written by comparing the capability core against the
**v2 legacy handler in this package** and nothing else. For two rows that
comparison reached the right verdict for the wrong reason: the core does beat
the legacy handler, and both lose to an implementation sitting in the same
repository that was never opened. Those two rationales have been corrected in
place.

## Measured

| capability | existing implementation | verdict |
| --- | --- | --- |
| `layered-cache-fabric` | `engines/build-cache-engine` (86k lines, 74 test files) | **existing is deeper** |
| `contract-compatibility-engine` | `packages/repository-refactoring/apicompat.py` (807 lines) | **existing is deeper** |
| `artifact-evidence-protocol` | `modules/cas` (45 Java classes) | **existing is deeper (storage half)** |
| `cost-eta-observability` | `packages/execution-intelligence/cost.py` | **complementary — keep both halves** |
| `phase-aware-model-router` | `packages/execution-intelligence/routing.py` | **the kernel is better** |

### `layered-cache-fabric` — the kernel is the shallower one

`build-cache-engine`'s fingerprint key carries **17 dimensions**, including
`prompt_template_digest`, `model_snapshot_digest`, `decoding_parameters`,
`tool_output_digests` and `declared_environment`. The kernel's carries nine.
The two dimensions this session argued were the whole justification for routing
this row to the core — a prompt-prefix digest and an environment fingerprint —
are both already there, and `declared_environment` goes further: it
audits observed environment reads against declared ones (an undeclared read is
reported as a hermeticity bug) and **refuses to let a secret-looking environment
value enter a key at all**.

Its admission model prices the decision: alongside policy refusals it has
`REJECTED_TENANT_QUOTA`, `ADMITTED_WITHIN_RESERVATION`, `ADMITTED_PROTECTED` and
`BYPASS_RESTORE_SLOWER_THAN_RECOMPUTE`. The kernel's `AdmissionPolicy` has a
flat minimum-compute-cost floor and no concept of restore cost at all.

Direction: the kernel should defer. What it holds that is worth keeping is the
hit-verification step — re-checking that a stored entry carries the requested
key parts before serving it — which should be checked against `action_cache.py`
before being called an addition.

### `contract-compatibility-engine` — the kernel is the shallower one

`repository-refactoring` distinguishes four break kinds —
`source-break`, `binary-break`, `wire-break`, `behavior-risk` — against the
kernel's `BREAKING` / `RISKY`. And it knows wire tags. The routing rationale in
`kernel_bridge.py` claimed wire-tag awareness as the core's advantage over the
legacy dict-diff; that was true of the legacy handler and false of the
repository.

### `artifact-evidence-protocol` — split the verdict

`modules/cas` is a real content-addressed store: `MerkleTree`, `CasHasher`,
`ActionCache` + `ActionCacheIndex`, `ActionKey`, `ResultSignature`,
`TenantEncryption`, `CasGarbageCollector`, `ResumableUploadService`. The
kernel's artifact storage is a key/value table behind a port.

The kernel's own contribution is different in kind and worth keeping: binding
evidence to the exact input digests it was produced from, so evidence for
snapshot A cannot justify a claim about snapshot B, and modelling `NOT_RUN` as
`UNSUPPORTED` rather than absence. That is a claims model, not a store. Wire
the storage half to `modules/cas`; keep the claims half.

### `cost-eta-observability` — complementary

`execution-intelligence/cost.py` has something the kernel does not: a versioned
rate registry where every rate must carry `effective_date`, `verified_at` and
`source_reference`, with anything flagged `not_for_billing` kept out of every
ranking — plus `mix_verification`, which states whether the category mix behind
a cost was ever measured (its docstring notes the categories are priced up to
fifty times apart, so an unexamined mix can be the largest error in a report
whose every other input is correct).

The kernel has something *it* does not: machine wall-clock, human-equivalent
effort and HITL wait as three types that cannot be summed, and unmeasured
reported as unmeasured rather than zero.

Neither subsumes the other. Wire both halves.

### `phase-aware-model-router` — the kernel wins

`execution-intelligence/routing.py` uses binary floats (four `float(` calls, no
`Decimal`). The kernel ranks on `Decimal` prices per million tokens with a
hashed decision, specifically so two hosts cannot order the same two models
differently.

This is the row that breaks the debt note's premise. Wiring the kernel to the
existing implementation here would *lose* a property. If anything the flow runs
the other way.

## Flagged, not concluded

Overlap is likely and unmeasured. Each needs the same treatment before a
verdict:

| capability | candidate | lines |
| --- | --- | --- |
| `incremental-semantic-index` | `repository-refactoring/index.py` | 822 |
| `changegraph-vcs` | `repository-refactoring/impact.py`, `buildgraph.py` | 660 + 906 |
| `agent-arena` (anti-cheat) | `repository-refactoring/anticheat.py` | 365 |
| `durable-run-orchestrator` | `repository-refactoring/orchestrator.py`, `journal.py` | — |

## Decision: do not wire now, and here is the trigger

Recommended, with the reasoning stated so it can be overruled on its merits.

**Do not wire any of these rows in this package's current shape.** Not because
the overlap is unreal — for the cache and the contract engine it is measured and
decisive — but because every wiring changes behaviour across a package boundary
that nothing currently guards. `engines/build-cache-engine` has 74 test files
and the root `Makefile` runs none of them as a target of their own; they are
reachable only as a `PYTHONPATH` entry for `unified-cli-gateway`. A rewiring
that regressed one of them would be caught by nothing.

**The trigger is a gate, not a schedule.** Wire a row when — and only when — the
package it wires into is gated by the root `Makefile` on its own, so a
regression in it fails a build somebody watches. That is one small change to
`Makefile` per engine, and it is the cheapest prerequisite on this list.

**Order, once gated.** `contract-compatibility-engine` first: the overlap is a
strict superset (four break kinds against two, and wire-tag awareness), the
surface is pure computation with no store or lease behind it, and the kernel row
has no property the existing implementation lacks. `layered-cache-fabric`
second: the overlap is larger but the kernel's hit re-verification needs
checking against `action_cache.py` before it is called an addition rather than a
duplicate. `artifact-evidence-protocol` third, and split: `modules/cas` takes the
storage, the kernel keeps the claims model (evidence bound to the input digests
it was produced from), because those are different things that happen to share
the word "artifact".

**Do not wire `phase-aware-model-router` in either direction without deciding
about floats first.** The existing implementation ranks on binary floats; the
kernel uses `Decimal` with a hashed decision. Wiring the kernel to it loses a
property. If anything the flow runs the other way, and that is a change to
`execution-intelligence`, not to this package.

**One verification is outstanding and would change the confidence, not the
decision.** I have not run `build-cache-engine`'s 74 test files. The
"existing is deeper" verdict rests on reading its `fingerprint.py`,
`cache_admission.py` and `cache_policy.py` — 17 key dimensions, a hermeticity
audit, secret refusal, restore-cost-aware admission — all of which are visible
in the source. Whether that code currently *passes its own tests* is a separate
question, and the answer bears on how much of it to trust when wiring. Run
those 74 files before acting on the order above.

## Why the wiring is not done here

Each row is a cross-package change touching a package this one does not depend
on, does not test, and — for `build-cache-engine` — that the root `Makefile`
does not gate on its own (its 74 test files are reachable only as a `PYTHONPATH`
entry for the `unified-cli-gateway` target). Rewiring a capability across that
boundary without a gate that would catch a regression is how the concurrency
accident this merge started from happens again.

The survey is the deliverable. The wiring is a decision about four other
packages.
