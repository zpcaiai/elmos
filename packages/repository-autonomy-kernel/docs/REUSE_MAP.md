# 31 capabilities × what ELMOS already had

Measured on 2026-09-01 against the working tree, before any of this package was
written. The point of the table is to say which capabilities are *new code* and
which are a second implementation of something the repository already owns —
because the expensive mistake here is not a missing module, it is two modules.

## How the columns were measured

- **Existing implementation** — found by reading the module's public signatures
  (`grep -nE '^(class |def )'`), not by directory-name matching. A name match is
  not evidence; several obvious-looking matches (`modules/security`, 36 lines)
  turned out to be near-empty.
- **State** — `covered` means real code exists that does substantially this job;
  `partial` means the mechanism exists but the specific invariant this
  capability is named for does not; `gap` means nothing in the repository
  implements it under any name (verified by symbol search across 1,490 source
  files in `modules/`, `packages/`, `engines/`, `services/`, `tooling/`).
- This table asserts **existence**, never sufficiency. "Covered" does not mean
  the existing code satisfies this package's contract — only that writing a
  fresh implementation would be building a second one.

## P0

| # | Capability | Existing implementation | State | What this package adds |
|---|---|---|---|---|
| 1 | task-spec-delta-compiler | `repository-refactoring/{intent,request,plan}.py` | partial | the spec/delta split, blocking open questions, `invalidates_steps` |
| 2 | durable-run-orchestrator | `repository-refactoring/journal.py` (JournalEvent, Checkpoint, SideEffect, Lease), `repository-orchestrator/journal.py` | partial | 19-state machine, unresolved-intent reconciliation, requirement-update rerun set |
| 3 | execution-authority-kernel | `modules/continuous-authorization` (145 L Java) | gap in Python | the minted, narrowable authority token |
| 4 | typed-tool-runtime | — | **gap** | schema validation, unknown-tool deny, result validation |
| 5 | policy-hook-kernel | `repository-refactoring/policy.py` (503 L) | partial | hook points, deny-precedence, obligations that survive aggregation |
| 6 | two-phase-secretless-sandbox | `repository-refactoring/sandbox.py` (548 L) | partial | the two-phase secret binding and the scrub proof |
| 7 | workspace-lease-fencing | `journal.py::Lease`, `modules/snapshot` (Java) | partial | monotonic tokens across release, the stale-writer proof |
| 8 | artifact-evidence-protocol | `repository-refactoring/evidence.py` (547 L, sign/verify) | covered | input-digest binding; `NOT_RUN ≠ PASS` |
| 9 | repository-census | `repository-refactoring/workspace.py`, `engines/project-intelligence-engine` | partial | defined counters, `unmeasured` list |
| 10 | incremental-semantic-index | `repository-refactoring/index.py` (822 L, `incremental_update`) | covered | incremental-equals-full as an executable assertion |
| 11 | semantic-ir-compiler | `engines/polyglot-route-engine`, `modules/uir`, `modules/lowering` | covered | a much smaller subset with a measured admission rate |
| 12 | changegraph-vcs | — | **gap** | change DAG, region+entity conflicts, idempotent apply |
| 13 | validation-dag | `repository-refactoring/verification.py` (623 L) | partial | SKIPPED as a first-class status |
| 14 | independent-verification-mesh | `modules/advanced-verification` (790 L Java), `verification-packs/` | partial | independence enforcement, preserved dissent |
| 15 | evidence-release-gate | `repository-orchestrator/gates.py`, `modules/delivery` | partial | NOT_RUN blocks; expiring waivers |
| 16 | contract-compatibility-engine | `repository-refactoring/apicompat.py` (807 L) | covered | variance reasoning, wire tag reuse |

## P1

| # | Capability | Existing implementation | State | What this package adds |
|---|---|---|---|---|
| 17 | prefix-stable-context-planner | `build-cache-engine/prompt_cache.py` (1,105 L), `context_runtime.py` | covered | prefix stability as a byte-level assertion |
| 18 | lazy-tool-loader | — | **gap** | deferred-not-callable, minimal covering set |
| 19 | model-state-continuity | `build-cache-engine/context_ledger.py`, `context_compaction.py` (1,153 L) | covered | "lossless for decisions" as a checkable claim |
| 20 | multi-agent-worktree-coordinator | `repository-orchestrator/planning.py` (path overlap), `modules/workspace` | partial | component-wise overlap, all-or-nothing wave acquisition |
| 21 | phase-aware-model-router | `repository-orchestrator/{routing,models}.py` (889 L) | covered | phase×risk policy, unprojectable cost reported as such |
| 22 | layered-cache-fabric | `modules/cas` (21,687 L Java), `build-cache-engine` (51,159 L) | covered | the nine-part complete key and the no-false-hit proof |
| 23 | cost-eta-observability | `packages/execution-intelligence` (10,107 L) | covered | three unmixable time types, no silent zero |
| 24 | tiered-security-assurance | `repository-refactoring/security.py` (772 L), `sarif.py` | partial | monotonic tiers enforced structurally |
| 25 | session-time-travel | — | **gap** | fork without mutating the parent timeline |
| 26 | capability-package-registry | `repository-refactoring/registry.py` (631 L), `modules/extension-marketplace` | partial | immutable versions, propagating revocation |

## P2

| # | Capability | Existing implementation | State | What this package adds |
|---|---|---|---|---|
| 27 | demonstration-to-skill | — | **gap** | generalisation with mandatory counterexamples |
| 28 | auto-improvement-inbox-and-skill-curator | — | **gap** | order-independent merge, duplicate-of-shipped detection |
| 29 | agent-arena | — | **gap** | structural contestant/grader isolation, anti-cheat |
| 30 | repository-model-elo | — | **gap** | integer Elo, provisional ratings, declared order tolerance |
| 31 | repository-gym-golden-routes | `engines/spring-golden-route-engine`, `routes/` (179 dirs) | partial | acceptance frozen at registration |

## Totals

```text
gap      (nothing existed)       9
partial  (mechanism, not invariant) 13
covered  (adjacent real code)    9
```

## The consequence for integration

Nine capabilities are genuinely new. Thirteen add a specific invariant to
machinery that already exists. **Nine overlap real, substantial code** — and
those nine are exactly where this package must be wired to what is already
there rather than shipped alongside it. Concretely:

- `layered-cache-fabric` should delegate to `modules/cas` + `build-cache-engine`
  rather than keep its own L3.
- `cost-eta-observability` should read `packages/execution-intelligence`'s
  calibrated token/price model rather than a second price table.
- `prefix-stable-context-planner` and `model-state-continuity` should sit on
  `build-cache-engine`'s `ContextLedger`, not beside it.
- `contract-compatibility-engine` and `incremental-semantic-index` should call
  `repository-refactoring`'s `apicompat`/`index` for the languages those already
  parse.

**That wiring is not written yet.** The kernel's ports make it a bounded piece of
work — an adapter per port — but until it exists this package is a second
implementation of those nine, and should be described that way.
