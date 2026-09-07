# perf/analyzer-build-cache-and-batching -> main: verification of the in-progress merge

Merge in progress in the main working tree. `HEAD` = `c03782bfe`,
`MERGE_HEAD` = `a54938b26`, merge base `5543624b4`.
Measured 2026-08-25 in a Linux container with Python 3.11, jsonschema, z3.
**No exact toolchains and no `engines/polyglot-route-engine/native/`**, so every
test that needs a real analyzer fails for environmental reasons on both trees.
The only meaningful number is therefore the *difference* between two runs of the
same suite in the same container.

## Method

* baseline = `git archive HEAD` (main alone, merge not applied)
* candidate = the merged working tree
* full suite both ways, `FAILED` name sets compared with `comm`

## Result

| | failed | errors |
|---|---|---|
| main alone (`c03782bfe`) | 1182 | 25 |
| merged tree | **1176** | 25 |

* 2154 tests collected, **0 collection errors** — every one of the 60 test
  modules imports cleanly against the merged source.
* **10 tests fixed** by the merge (8 x `test_arithmetic_proof`,
  `test_pipeline_insights::...share_fail_closed_behavior_insights`,
  `test_repository_pipeline_language_matrix::...pending_languages_are_refused...`)
* **0 regressions** among main's own tests.
* 4 residual failures, all from perf's newly-added tests — see below.

## Defects found and fixed during verification

Every one of these was a *silent* auto-merge result: no conflict marker, clean
syntax, and a `NameError` / wrong error code / dead assertion at call time.

1. `cli.py` — `REPOSITORY_SURFACE_LANGUAGES` used, never imported (`NameError`
   on `repository-preflight --source-language`). Fixed on the other side by
   dropping the two usages.
2. `tests/test_repository_pipeline_language_matrix.py` — same missing name.
3. `tests/test_repository_pipeline.py` — `test_proposed_candidates_never_decide_eligibility`
   defined twice; the second shadowed the first, so one copy never ran.
4. `batch.py` — `_UNIT_ID_PATTERN` came across as `^WU-[0-9]{5}$`, which rejects
   main's partitioned ids `WU-00001-F002`. `_recorded_artifact_intact` would
   then treat every resumed multi-function unit as not-intact.
5. `batch.py` — `_checkpoint_identity` lost `identifier_unit_namespace`,
   `identifier_unit_namespace_sha256`, `repository_scale`, `repository_limits`,
   while `run_batch` still passed `identifier_unit_namespace=` to `migrate`
   (undefined name).
6. `batch.py` — `BATCH_UNITS_DIRECTORY_UNSAFE` and `DISCOVERY_RESULT_ID_DUPLICATED`
   were collapsed into `WORK_UNIT_OUTPUT_UNSAFE` / `DISCOVERY_RESULT_ID_INVALID`,
   losing the malformed-vs-duplicated distinction.
   (4-6 are moot as of the revert of `batch.py` to main's version.)
7. `pipeline.py` — **`PIPELINE_NO_VERIFIED_UNITS` was dropped** when perf's
   `passed > 0` soft path was adopted. A run with an empty behavior-case corpus
   packaged a report instead of refusing. Restored, guarded on
   `discovery_incident is None` so perf's diagnostic path still works.
   Caught by `test_pipeline.py::test_repository_pipeline_refuses_to_package_without_behavior_evidence`.
8. `conversion_reporting.py` — `_UNIT_ID = ^WU-[0-9]{5}$` and the obligation-id
   regex reject main's partitioned ids, so any repository with a multi-function
   file raised `FUNCTION_REPORT_BATCH_UNIT_ID_INVALID`. Both widened.
9. `tests/test_preflight.py`, `tests/test_repository_pipeline.py` — 7 sites
   monkeypatch `discovery_module.analyze`. That attribute has never existed on
   either branch (`discovery` binds `analyze_many` / `inventory_module`, from
   `source_analyzer` on main and from `native` on perf), so these tests were
   already failing on `a54938b26`. Rebound through a `_as_analyze_many` adapter.
10. `test_python_inventory_...` asserted `len(propose_candidates(41 funcs)) == 41`;
    both branches cap `propose_candidates` at `MAX_CANDIDATES_PER_FILE == 40`.
    Also already failing on `a54938b26`. Retargeted onto `_candidate_inventory`,
    which is the path that actually carries the no-truncation obligation.

## Two perf tests asserted semantics main deliberately replaced

Adapted to assert the same *property* against main's mechanism, with the reason
recorded in the test body:

* methods: perf asserted `propose_candidates` proposes `Hidden.method`. Main's
  `python_coverage_subjects` makes a nested symbol an explicit **blocker**
  (`candidate=False` + `blocking_reasons`) so it cannot vanish from a
  file-level READY result. The test now asserts the blocker.
* multi-function files: perf refused the file with
  `MULTIPLE_ELIGIBLE_FUNCTIONS_REQUIRE_EXPLICIT_PARTITION`; main partitions into
  `WU-00001-F001` / `-F002`, which satisfies "never silently selects the first"
  more strongly. Directly contradicted main's own
  `test_discovery_partitions_multiple_functions_into_explicit_work_units`.

## Open: 3 perf batch tests have no implementation behind them

`batch.py` was reverted to main's version, so perf's incident-tolerant
checkpoint is not in the tree — but its tests are:

* `test_batch_records_exact_toolchain_incident_without_aborting_the_report`
* `test_batch_resumes_from_its_checkpoint_without_redoing_work`
* `test_batch_does_not_resume_legacy_pass_without_source_validation_evidence`

They need `reason_code`, `source_validation_status` and `_partial_target`, of
which main's `batch.py` has **0 occurrences**. These will still fail on a fully
provisioned machine; they are not environmental. Either port perf's batch-layer
work onto main's `batch.py`, or mark the three `xfail` against that follow-up so
the obligation stays visible. Do not delete them.

The 4th residual failure,
`test_discovery_never_silently_selects_the_first_of_multiple_functions`, now
fails only for the same environmental reason as its main-side twin.

## Still unverified

* the other auto-merged both-sides files outside the engine: `Makefile`,
  `Makefile.batch29`, `docs/BUSINESS_LINE_CLOSURE_MATRIX.md`,
  `apps/web-console/app/lib/contracts.ts`,
  `apps/web-console/app/lib/server/translationRunner.ts`
* `pnpm check` in `apps/web-console` (the 11-script union)
* the three remaining branches: `fix/l0-arithmetic-equivalence`,
  `feat/batch38-45-certification-toolchain`,
  `feat/execution-intelligence-forecasting`

---

# Round 2 of bug-fixing (same merge, after the pipeline union was rebuilt)

## 7 of main's own test bodies had been silently replaced by perf's

No test was lost outright, but the union took perf's body for 7 tests that
exist on both sides. 4 were whitespace-only or my own `_as_analyze_many`
rebinding. The other 3 asserted perf's shape against main's implementation:

| test | perf's body asserted | merged implementation actually does |
|---|---|---|
| `test_batch_records_a_unit_failure_without_stopping_the_queue` | `reason_code` / `failure_stage` | `batch.py` has 0 occurrences of either; the coded reason lives in `reason` |
| `test_batch_runs_ready_units_and_never_rounds_up` | evidence `status == "PASSED"` | `engine.py` emits `PASSED_LOCAL_UNCERTIFIED` in repository execution mode |
| `test_discovery_classifies_every_unit_with_a_precise_verdict` | `constants.py` -> `NO_CANDIDATE_DECLARATION`, `rejected_candidates[]` | probed the merged `discover_repository` directly: `UNSUPPORTED`, `blocker_code="PYTHON_TOP_LEVEL_EFFECT_CONVERSION_UNCOVERED"`, no `rejected_candidates` key; `coverage_subject_count` / `coverage_blocker_count` do exist |

All three restored to main's bodies.

## The 3 perf batch tests: do NOT port perf's resume, adapt the tests

Porting perf's incident-tolerant checkpoint would undo a deliberate, documented
decision in main's `_recorded_artifact_intact`:

> A local JSONL checkpoint is interruption state, not an authentication
> boundary.  A caller that can edit it can also forge matching target and
> evidence digests, so PASSED (and transient FAILED) outcomes must execute
> again.  Only non-success skips are safe to resume without runtime replay.

perf's `test_batch_resumes_from_its_checkpoint_without_redoing_work` asserts
`resumed_count == len(results)` — i.e. that the PASSED unit *is* resumed. Main
refuses to, on purpose, and main's own
`test_batch_reexecutes_a_forged_pass_checkpoint_and_restores_evidence` already
covers the case perf's "legacy pass" test was protecting. All three adapted to
main's rule with the reason recorded in the test body; the `reason_code` /
`failure_stage` assertions became `reason.startswith(...)`.

Net: 4 residual failures vs main alone, every one of them now failing at the
same environmental wall (`StopIteration` on `next(... verdict == READY)`) as its
main-side twin. No semantic contradiction is left in the suite.

## The hybrid pipeline is sound

`_shared_claim` is built once and spread into both the report and the manifest,
and it carries *both* vocabularies: `project_graph` / `conversion_coverage` /
`behavior_coverage` / `repository_complete` / `repository_execution_status` from
main, and `functional_conversion` / `artifact_packaging` from perf. Report and
manifest cannot drift apart. This is better than the "take ours whole" fallback
proposed in round 1 and supersedes it.

## Structural audit of the 6 non-engine both-sides files: clean

`Makefile` (107 targets = union of 105 + 100), `Makefile.batch29` (the two
apparently-missing `b29-nodejs-*` targets are aliased on one multi-target rule
`b29-nodejs-prepare b29-nodejs-replay: b29-nodejs-verify`),
`docs/BUSINESS_LINE_CLOSURE_MATRIX.md`, `engines/polyglot-route-engine/README.md`,
`contracts.ts`, `translationRunner.ts`: **no symbol, target or heading lost from
either side, and none invented.** Body-level check on the two TS files: of the
23 symbols the two sides disagree on, the merge took one side's body cleanly
every time -- 0 spliced hybrids.

## Web console: one hard syntax error, found by running the gate

`apps/web-console/app/lib/server/translationRunner.ts` was **missing one
closing brace**. `validateTranslationPipelineEvidence` (opens line 1143) never
closed, so lines 1146-3243 -- the entire rest of the file, ~60 declarations --
were nested inside it. `ts.transpileModule` reported `'}' expected` at EOF and
Node failed with `SyntaxError: Unexpected token 'export'` at the first nested
`export`. The same imbalance is present in `a54938b26`, so it came across with
the graft rather than being created by the auto-merge.

Fixed by closing the function after its `return { ... };`. TypeScript syntax
diagnostics now 0.

`pnpm check` script status after the fix (11 scripts):

| script | result |
|---|---|
| chinadb-sql-policy, upstream-policy, operations-jobs-policy, billing-reconciliation-policy, admin-mutation-policy, runner-fleet-policy, durable-lease, repository-translation | PASS |
| translation-cancellation | now loads and runs; fails on the inventory contract below |
| translation-report | 23/24; the one failure is the device bridge -- `uv` cannot `rm` `.venv/.lock` ("Operation not permitted") |
| multimodal-intake-runner | `MULTIMODAL_ENGINE_UNAVAILABLE` -- needs a running engine |

## Pre-existing main-side breakage this merge did not cause (do not fix blind)

`c03782bfe` added a required `exact_versions` field to
`apps/web-console/app/lib/server/translationRoutes.ts` (6 references) **and** to
`scripts/operations/validate_translation_route_matrix.py` (`detail.get("exact_versions") == list(VERSIONS[language])`),
but never added it to `routes/inventory.json`, where every language entry still
carries only `engine_path` and `version` -- unchanged since the merge base.
Consequences on main, with or without this merge:

* the console cannot parse its own route inventory
  (`languages.cpp.exact_versions 必须是不含重复项的非空精确版本数组。`)
* `make business-line-contracts` is red, though it fails earlier still, on
  `V3_REPOSITORY_STATUS_DRIFT`

The data belongs to whoever made that change -- `VERSIONS` is the authoritative
table and filling `inventory.json` from it is mechanical, but the
`V3_REPOSITORY_STATUS_DRIFT` failure ahead of it is a separate unfinished edit.
Left alone deliberately.

## Still not done

* `tsc --noEmit` and `next build` over the whole console (only the 11 scripts were run)
* the three remaining branches: `fix/l0-arithmetic-equivalence`,
  `feat/batch38-45-certification-toolchain`, `feat/execution-intelligence-forecasting`

---

# Round 3: `tsc --noEmit` on the web console, from 3 hard errors to 0

The console's type gate had never been run on this merge. It found two syntax
errors and one live schema incompatibility.

## Two dropped terminators (both present in `a54938b26`, inherited by the merge)

1. `app/lib/server/translationRunner.ts` — `validateTranslationPipelineEvidence`
   (opens 1143) was missing its closing `}`, nesting lines 1146-3243 inside it.
2. `app/lib/contracts.ts` — `export type TranslationBehaviorCoverage` (opens
   725) was missing its closing `};`, so `TS1131: Property or signature expected`
   at the next declaration.

Both fixed. TypeScript syntax diagnostics: 0.

## `build_verification`: the console was reading a shape the engine never writes

With the syntax errors gone, the real defect surfaced. The engine writes

```
"build_verification": {"status", "commands": [{command, stdout, stderr}],
                       "toolchain": {"language", "version"}, "reason"}
```

and `contracts.ts` declares exactly that. But `translationRunner.ts` validated
and read a singular `command: string[]` plus a **string** `toolchain` — perf's
older shape. Because the guard rejected a non-string `toolchain`, **every real
pipeline report would have been refused with
`TRANSLATION_PIPELINE_EVIDENCE_INVALID`.** The console could not have accepted
a single repository translation.

The file already contained `validBuildVerification` (line 358), main's reader
for the correct shape — it was simply unused. Fixes:

* the guard now checks `commands` / `toolchain` as written, and defers to
  `validBuildVerification` when the status is PASSED;
* `buildVerification` is attached only when a build actually verified — the
  field is optional on `TranslationJob`, so NOT_RUN and FAILED say so by
  omission instead of by a half-populated record;
* `buildVerification.status` in `contracts.ts` widened from the literal
  `"PASSED"` to `"PASSED" | "FAILED" | "NOT_RUN"`, the set the engine emits and
  the runner already validated at runtime;
* `buildStatus` narrowed at its source, one line above its own membership check;
* `e2e/project-evidence-charts.spec.ts` fixture given the `reportReady` field
  that perf added to `TranslationJob`.

**`node_modules/.bin/tsc --noEmit`: 0 errors.**

## `pnpm check` scripts, final

8/11 PASS (chinadb-sql, upstream, operations-jobs, billing-reconciliation,
admin-mutation, runner-fleet, durable-lease, repository-translation).

The 3 that do not pass are not merge defects:

* `translation-cancellation` — blocked by the `exact_versions` gap in
  `routes/inventory.json` described above (main-side, pre-existing)
* `translation-report` — 23/24; the one failure is the device bridge refusing
  `rm .venv/.lock` ("Operation not permitted")
* `multimodal-intake-runner` — `MULTIMODAL_ENGINE_UNAVAILABLE`, needs a running engine

`next build` still not run.

---

# Round 4: `next build`, and the other three branches

## `next build`: green

Cannot run on the device — Next.js shells out to `pnpm config get registry` to
fetch `@next/swc-linux-arm64-gnu`, and the Cowork VM has neither `pnpm` on PATH
nor network. Run in the cloud container instead: `pnpm install --frozen-lockfile`
then `next build`.

```
✓ Compiled successfully in 22.0s
  Finished TypeScript in 18.4s
✓ Generating static pages (22/22)
EXIT=0
```

Two warnings, both pre-existing and unrelated to the merge: "Dynamic filesystem
access causes tracing of the whole project" at
`app/lib/server/multimodalIntakeRunner.ts:374` and one more of the same kind.

`pnpm check` = `tsc --noEmit` (0 errors) + 11 scripts (8 pass, 3 blocked by
causes outside this merge) + `next build` (exit 0).

## Two of the three branches are already in

| branch | tip | status |
|---|---|---|
| `fix/l0-arithmetic-equivalence` | `2c9c668fd` (2026-08-06) | `merge-base --is-ancestor origin/<b> HEAD` -> **already merged**, 0 commits ahead. Also an ancestor of `a54938b26`. |
| `feat/batch38-45-certification-toolchain` | `7d61cf134` (2026-08-14) | **already merged**, 0 commits ahead. Also an ancestor of `a54938b26`. |
| `feat/execution-intelligence-forecasting` | `5ebe5fddf` (2026-08-20) | 7 commits ahead — see below |

The MERGE_NOTES' "3 conflict hunks, near-free" for `fix/l0-arithmetic-equivalence`
is stale; `c03782bfe` absorbed it.

## `feat/execution-intelligence-forecasting` is superseded, not unmerged

171 files on its side, 99 also touched by HEAD, of which **77 are byte-identical**
and 22 genuinely diverge. All 22 conflict, because at the merge base
`packages/execution-intelligence/` **did not exist**: both sides added the whole
package independently. It is one add/add conflict, not 22 disagreements.

HEAD's copy is version **1.1.0**; the branch's is **1.0.0**. HEAD is a near
superset — same 12 modules, `certifier.py` at 19 symbols vs 11, plus Ed25519
evidence certification. Symbols on the branch and missing from HEAD: **7**, of
which 6 are module-level path constants (`PACKAGE_ROOT`, `SCHEMA_DIR`,
`CONFIG_DIR`, `TEMPLATE_DIR`) and a private `_load` helper, all refactored away
in 1.1.0.

The 7th is a test, and it is the decisive one:

* branch: `test_full_evidence_reaches_release` -> `assert report["decision"] == "release"`
* HEAD:   `test_unsigned_full_evidence_is_blocked` -> `assert report["decision"] == "block"`,
  `evidence-provenance` gate FAIL, `"evidence-provenance.json is required"`

**The evidence fixture in the two tests is byte-identical.** 1.1.0 deliberately
tightened the gate: complete evidence is no longer sufficient for release, it
must also be signed. The branch's one unique test asserts exactly what HEAD now
forbids.

`.github/workflows/execution-intelligence.yml` tells the same story — HEAD adds
`permissions: contents: read`, `persist-credentials: false`, the `cryptography`
dependency, and a negative-control step that requires `make certify` to reject
synthetic evidence with a persisted BLOCK.

**Nothing to port.** Taking the branch's content would regress the certification
gate. Record it as merged without taking content, after the perf merge is
committed:

```
git merge -s ours origin/feat/execution-intelligence-forecasting \
  -m "Record feat/execution-intelligence-forecasting as merged: superseded by execution-intelligence 1.1.0

The branch adds packages/execution-intelligence 1.0.0, which c03782bfe already
supersedes with 1.1.0 (Ed25519 evidence certification). Its only unique test,
test_full_evidence_reaches_release, asserts decision == release on the same
evidence fixture that 1.1.0 blocks for lacking evidence-provenance.json."
```

## Correction: the topology is not what the notes (or I) said

`git symbolic-ref --short HEAD` -> **`perf/analyzer-build-cache-and-batching`**.
All of this work has been happening on the perf branch, not on main. Concretely:

* `HEAD` = `c03782bfe`, a commit on the local perf branch.
* `origin/perf/analyzer-build-cache-and-batching` = `f4fb9157d` (2026-08-25) and
  **is already an ancestor of HEAD** — the local branch is ahead of its remote.
* `origin/main` = `467e25551` (2026-08-18). HEAD is **not** an ancestor of it;
  the two have diverged: 47 commits on main that HEAD lacks, 86 the other way.
* `origin/main` **already contains** `conversion_reporting.py`, and `1bd15ddca`
  ("feat(translation): add functional conversion evidence reports", 2026-08-14)
  is a **main** commit, not a perf one.

So the earlier attribution in this file — "perf removed the project-graph
pipeline on 08-14 in `1bd15ddca`" — has the branch labels backwards. The
*content* findings are unaffected: every resolution was decided from the code
and from test dependencies, not from which branch a hunk came from. Read
"theirs / perf side" throughout this document as "the `a54938b26` side of this
merge".

Landing on main is still ahead and is a separate, third merge:
merge-base `609aa2414` (2026-08-06), **87 files changed by both sides**
(HEAD-side 40905 files, main-side 218). `origin/main` has no
`packages/execution-intelligence` at all.

Order of operations from here:

1. commit the in-progress merge on the perf branch (conflicts resolved, engine
   suite has no regressions, `tsc --noEmit` and `next build` both clean)
2. `git merge -s ours origin/feat/execution-intelligence-forecasting` (above)
3. then the real perf -> main merge, 87 both-changed files

---

# Round 5: `make business-line-contracts` — from red to green

Merge landed: `main` = `origin/main` = `3768d0a78`.

This gate was red on main independently of the merge. Both failures traced to
`routes/inventory.json` never being updated after `c03782bfe` expanded the
matrix from 30 routes to 156 and added `exact_versions` as a requirement in
`translationRoutes.ts` and `validate_translation_route_matrix.py`.

Every value written below comes from an authoritative table
(`scripts/batch29/route_runtime_metadata.py` and `route_sets.py`) or from a
generator the validator itself compares against. Nothing was invented, and no
route's evidence status was promoted.

## Five stale facts, found by running the validator to a fixed point

| # | reason code | what was stale | authority used |
|---|---|---|---|
| 1 | `V3_REPOSITORY_STATUS_DRIFT` | `route_sets["kotlin-react-flutter-completion-66"].repository_status` was `PENDING_REPOSITORY_SURFACE`; `pending_repository_languages` absent | `models.PENDING_REPOSITORY_LANGUAGES == ()` and kotlin/react/flutter all in `REPOSITORY_SURFACE_LANGUAGES`, with `test_{kotlin,react,flutter}_repository_pipeline.py` present |
| 2 | `LANGUAGE_EXACT_VERSION_DRIFT` | **all 13** languages had no `exact_versions` | `VERSIONS[language]` |
| 3 | (same block) | kotlin/react/flutter carried the *status string* `"LOCAL_SINGLE_UNIT_READY"` in their `version` field and had no `engine_path` | `SHORT_VERSIONS`, `ENGINE_PATHS` |
| 4 | `ROUTE_VERSION_DRIFT` | 66 V3 route entries carried `target_version: "PENDING_ANALYZER"`; 72 version fields disagreed with `languages[*].version` | `languages[*].version` |
| 5 | `V3_ROUTE_EVIDENCE_OVERCLAIM` | all 66 V3 routes had `local_execution_reason: "LOCAL_EXECUTION_NOT_RUN"` | the validator's own required literal `V3_ROUTE_CAMPAIGN_NOT_RUN` |
| 6 | `ROUTE_SOURCE_VERSION_DRIFT` | the 66 V3 route packs had `versions: []` and placeholder `engine_path: "engines/java-engine"` (the other 90 packs were already correct) | `VERSIONS`, `ENGINE_PATHS`, `TARGET_EMITTER_RELATIVE_PATH` |
| 7 | `V3_ROUTE_CERTIFICATION_OVERCLAIM` | 66 `certification.json` + 66 `evidence.json` did not match their generators | `v3_research_certification_document()` / `v3_research_evidence_document()` |

**199 files changed**: `routes/inventory.json`, plus 66 x
(`route.json`, `certification/certification.json`, `certification/evidence.json`).

## Result

```
validate_model_catalog             PASS
validate_makefile_portability      PASS
validate_spring_route_contract     PASS
validate_translation_route_matrix  PASS
make business-line-contracts       OK
```

`{"route_count": 156, "certified_route_count": 0, "locally_passed": 0,
  "external_certification_evidence": "NOT_RUN", "status": "PASSED"}`

Note what did **not** change: `locally_passed` stays 0 and
`certified_route_count` stays 0. The matrix expansion from 30 to 156 reset every
route to NOT_RUN (`origin/main`@`467e25551` had 30 routes all `PASSED_LOCAL`;
everything from `a54938b26` on has 156 routes with 0 passed). That reset is
correct — a 156-route matrix cannot inherit evidence produced for 30 — and the
validator accepts it.

## Regression check on the inventory edit

`test_matrix_consistency.py` — the module that binds the engine's language
tuples to `routes/inventory.json` — is **fully green** against the new
inventory. `test_language_set.py` is 23/24; the one failure is
`EXACT_TOOLCHAIN_PLATFORM_MISMATCH:kotlin:expected=Darwin/arm64:observed=Linux/x86_64`,
i.e. the container's platform, not the data.

## Still red, and correctly so

`pnpm test:translation-cancellation` now gets past the inventory parse and fails
with `TRANSLATION_ROUTE_NOT_LOCALLY_EXECUTABLE`. It points `ELMOS_REPOSITORY_ROOT`
at the real repository and requires a route with `localExecution === "PASSED"`
**and** `repositoryExecutionStatus === "PASSED"` with evidence refs.

No revision in this history has ever had `repository_execution_status == "PASSED"`
on any route — not `467e25551`, not `a54938b26`, not `c03782bfe`, not HEAD. The
test needs produced evidence and cannot pass on a bare checkout. Writing
`PASSED` plus evidence refs into the inventory to satisfy it is exactly the
overclaim `ROUTE_EVIDENCE_INVERTED` and the hardcoded-`LOCAL PASS` ban exist to
prevent, so it was left alone.

---

# Round 6: `test:translation-cancellation` — my mistake, corrected

## The evidence cannot be produced from here, and that is not the point

`createTranslationJob` refuses a route without
`localExecution === "PASSED"` **and** `repositoryExecutionStatus === "PASSED"`
plus evidence refs. That guard is **not** new — it is present at the merge base
`5543624b4`, at `c03782bfe`, and at `a54938b26` alike.

Producing that evidence means running the repository pipeline for real. The
toolchains are pinned to `Darwin/arm64` with absolute paths under
`/Users/stephen/.local` (`_EXPECTED_PYTHON_LOCAL_ANCHOR`,
`_EXPECTED_TYPESCRIPT_CACHE_ANCHOR`, and the `EXACT_TOOLCHAIN_PLATFORM_MISMATCH`
guards). Neither the Cowork Linux VM nor the Linux container can run it. It can
only be produced on the Mac.

A synthetic fixture repository root is also not viable: `assertRoutePacksExist`
walks **every** route in the inventory and `assertSafeRepositoryEnginePath`
requires the real analyzer files to exist under the root. The console is
deliberately built to read the real repository, not a stand-in.

## What was actually wrong: the test was on the wrong gate, and I put it there

| revision | test file present | `test:translation-cancellation` in `check` | inventory `locally_passed` |
|---|---|---|---|
| `5543624b4` (base) | no | — | — |
| `c03782bfe` (main) | no | **NOT in check** | 0 |
| `a54938b26` (perf) | yes | **in check** | 0 |

So the test was already failing on `a54938b26` — the fourth pre-existing red on
that side, alongside `discovery.analyze`, the 41-vs-40 `propose_candidates`
assertion, and the two dropped TypeScript terminators.

When I unioned the two `check` scripts into eleven, I pulled an
evidence-dependent test onto a gate that has to pass on a clean checkout. Main
had deliberately left it off. That was my error.

## Fix

`pnpm check` no longer runs it. The script stays defined and is reachable
through a new, explicitly named entry point:

```
"check":          "tsc --noEmit && …10 scripts… && next build"
"check:evidence": "pnpm test:translation-cancellation"
```

`check:evidence` is the gate for "this checkout carries produced route
evidence". It fails on a bare checkout by design, and passes once a repository
run has recorded a locally-passed route with repository evidence.

## `pnpm check` status after the change

| | |
|---|---|
| `tsc --noEmit` | 0 errors |
| `next build` | EXIT=0, 22 static pages |
| durable-lease, repository-translation, upstream-policy, operations-jobs-policy, billing-reconciliation-policy, admin-mutation-policy, runner-fleet-policy, chinadb-sql-policy | **PASS** |
| translation-report | 23/24 — the one failure is the device bridge refusing `rm .venv/.lock` ("Operation not permitted"); not reproducible off the mount |
| multimodal-intake-runner | `MULTIMODAL_ENGINE_UNAVAILABLE` — needs a running engine; this one was already on main's own `check` |

Both remaining failures are environmental to this session, not properties of the
checkout. `pnpm check` has not been observed green end to end anywhere I can
run it; on the Mac, with the pinned toolchain and the engine reachable, the
remaining two should pass.
