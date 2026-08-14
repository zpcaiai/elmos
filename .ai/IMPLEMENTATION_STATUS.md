# IMPLEMENTATION_STATUS.md

> Requirement → Evidence matrix for the **active task only** (see `TASK.md`).
> Status vocabulary is closed: `IMPLEMENTED` · `PARTIAL` · `STUB` · `MISSING` ·
> `BROKEN` · `NOT VERIFIED`.
>
> `IMPLEMENTED` requires **all** of: real business logic (no TODO / `pass` /
> `NotImplemented` / placeholder / hardcoded success), wired into a real call
> chain, covered by a test that exercises the behaviour, and an **executed**
> result recorded in `TEST_RESULTS.md`.
>
> Last audit: **2026-08-14**, Claude Code, `badffaba`, working tree dirty
> (721 tracked changes excluding untracked files). Real local tests were run;
> see the current-state override below and `TEST_RESULTS.md`.

## 2026-08-13 current-state override

The older per-row table below is retained as historical audit detail. Current
runtime evidence supersedes its earlier `not executed` cells:

- R1–R7: the matrix still collects exactly **182** tests; the declared
  ten-language/90-route shape remains live.
- R9: **PARTIAL**, not `BROKEN / NOT_RUN`. All 90 SMALL routes passed in the
  valid prefix. The remaining 47 MEDIUM tail produced 38 passes and nine
  Swift-source infrastructure failures. The Swift probe-environment mismatch
  is fixed and unit-verified, but a real rerun is blocked by disk headroom.
- D1 infrastructure status preservation: **IMPLEMENTED**, 2 regressions pass.
- D2 analyzer snapshot root-group normalization: **IMPLEMENTED**, 16 tests pass.
- Swift cache/network exact-environment regression: **IMPLEMENTED**, the full
  module passes 33/33.
- R10 remains **MISSING**: independent client-repository verification is 0/90.
- R11 remains **MISSING / NOT_CERTIFIED**. No eligible campaign/evidence exists
  for the only permitted certification gate.

---

## Batch 29 — polyglot route matrix (ACTIVE)

| # | Requirement | Status | Implementation evidence | Test evidence | Runtime evidence | Remaining work |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | Language set is 10 languages incl. JavaScript as an identity distinct from TypeScript | **IMPLEMENTED** (static) | `models.py` — `Language` Literal + `SUPPORTED_LANGUAGES` = 10 entries incl. `"javascript"`; `COMPLETE_MATRIX_LANGUAGES` = same 10 | `tests/test_language_set.py::test_route_contract_is_complete_ten_language_matrix_with_exact_subsets` asserts `len(COMPLETE_MATRIX_LANGUAGES) == 10` | ⛔ not executed | Execute the assertion |
| R2 | Directed route surface is 90 | **IMPLEMENTED** (static) | `models.py` — `COMPLETE_MATRIX_DIRECTED_PAIRS` computed as the full directed permutation; `ROUTED_PAIRS` aliases it | same test: `len(ROUTED_PAIRS) == 90`, `len(set(ROUTED_PAIRS)) == 90` | ⛔ not executed | Execute |
| R3 | 18 Node.js directions carry their own evidence identity | **IMPLEMENTED** (static) | `models.py` — `NODEJS_DIRECTED_PAIRS` derived from pairs where `"javascript" in {source, target}`; deliberately kept out of `SPECIALIZED_DIRECTED_PAIRS` (immutable 8-entry proof scope) | `test_language_set.py` asserts `len(NODEJS_DIRECTED_PAIRS) == 18` and `len(SPECIALIZED_DIRECTED_PAIRS) == 8` | ⛔ not executed | Execute |
| R4 | A route pack exists for every declared pair and nothing else | **IMPLEMENTED** (static) | `routes/` contains exactly **90** `<src>-to-<tgt>` directories + `inventory.json`, no extras (verified by directory count) | `test_every_declared_routed_pair_has_a_pack_and_nothing_else_does` (both directions of the set difference) | ⛔ not executed | Execute |
| R5 | `routes/inventory.json` declares 90 with preserved provenance sets | **IMPLEMENTED** (static) | `inventory.json`: `route_count = 90`, `len(routes) = 90`, `len(languages) = 10`, `route_sets` keys exactly = `{legacy-complete-30, cpp-objc-swift-java-exact-8, nine-language-completion-34, nine-language-complete-72, javascript-node26-completion-18, ten-language-complete-90}` | `test_inventory_declares_the_complete_90_with_preserved_provenance_sets` | ⛔ not executed | Execute |
| R6 | Repository orchestration surface is complete for all 10 languages | **IMPLEMENTED** (static) | `repository._EXTENSIONS` maps `.cjs/.js/.mjs → javascript` alongside the other 9; `assembly._BUILD_FILES` has 10 keys incl. `"javascript": ("package.json",)` | `test_repository_orchestration_has_a_complete_ten_language_surface` asserts all four sets equal `SUPPORTED_LANGUAGES` | ⛔ not executed | Execute (`_DECLARATION_PATTERNS` / `_PLACERS` confirmed only indirectly via the 10-key `_BUILD_FILES` and the JS assembly-shape test) |
| R7 | Concrete-span policy applies to specialised **and** Node.js routes | **IMPLEMENTED** (static) | `models.requires_concrete_source_spans` returns `True` for `typed-pure-module-v1`, and for `typed-pure-function-v1` when the pair is specialised **or** in `NODEJS_DIRECTED_PAIRS`; unknown profiles fail closed to `True` | `test_concrete_span_policy_is_profile_and_route_specific` | ⛔ not executed | Execute |
| R8 | C# target assembly must not compile evidence copies | **PARTIAL** (code + test confirmed present; never executed) | ✅ `assembly.py:1877` emits `<EnableDefaultCompileItems>false</EnableDefaultCompileItems>` and `:1880` `<Compile Include="src/**/*.cs" />` | ✅ `tests/test_assembly.py:450 test_csharp_build_compiles_only_assembled_sources_not_evidence_copies` — asserts the glob change, asserts the 2 evidence copies still exist, and asserts a **real** `verify_assembled_project("csharp", …)["build_verification_status"] == "PASSED"` | ⛔ not executed — no `dotnet` reachable | Run the regression on the Mac |
| R9 | Every directed route passes SMALL **and** MEDIUM | **IMPLEMENTED** ✅ *(2026-08-14)* | — | `tests/test_repository_pipeline_language_matrix.py` (frozen suite, **182** collected nodes; pre-run collect `pytest_exit=0, collected_nodes=182`) | ✅ **`182 passed in 9791.03s (2:43:11)`** — one serial process, no `-x`, real summary line, `pytest_exit=0`, `freeze_verify_exit=0`. Log `.ai/matrix182-owned-run.log` sha256 `758d6473…a0f0e9`; head `badffaba`; freeze `e43733fc…`; 2026-08-14T07:16:15Z→09:59:27Z. 182 = 2 contract + 90 SMALL + 90 MEDIUM | None for the matrix itself. Re-running as *certification* evidence requires a fresh freeze window if any source changes |
| R10 | Independent client-repository verification | **MISSING** | — | — | ⛔ `0` routes verified | Largest unstarted work item |
| R11 | Formal certification | **MISSING** | Gate script is the only permitted setter | — | ⛔ `NOT_CERTIFIED` | R9 now satisfied; **blocked on R10 alone** |
| R12 | External-build failures surface `stdout` as well as `stderr` | **IMPLEMENTED** ✅ *(fixed this session)* | `validation.py` — new `_failure_detail()` + `_FAILURE_STREAM_LIMIT`; both streams preserved, each bounded independently, empty stream omitted, `no-output:returncode=N` instead of an empty detail. `TARGET_VALIDATION_FAILED:{cmd}:{detail}` shape unchanged | 3 new regressions in `tests/test_native_validation.py`: `…reports_stdout_even_when_stderr_is_noisy`, `…with_no_output_is_reported_explicitly`, `…bounds_each_stream_independently` | ✅ **3/3 PASS** (Python 3.11.15, pytest 9.1.1); whole-module baseline vs patched = 30 failures both, 0 new | Re-run inside the Mac's real gate set (Ruff + strict mypy) before the next freeze |

## Batch 32 / 35 — frontend v2 route equivalence (parallel workstream, mid-flight)

| # | Requirement | Status | Notes |
| --- | --- | --- | --- |
| F1 | `client-packs/frontend-72-route-equivalence-v2` formal campaign packs | **PARTIAL** | ~700 uncommitted modified files across implementation/replay schemas (`batch32`, `batch35`), validators, tooling, oracle provenance graph. Codex's frontend thread reported it was in "final pack atomic publish / final review" but had **not** committed, pending the backend thread's unfreeze signal. |
| F2 | Frontend-only scoped commit | **MISSING** | Explicitly deferred to avoid clobbering the backend thread on the shared branch. |

## Audit notes — fake-implementation sweep

The stub/placeholder sweep across `engines/polyglot-route-engine/src`
**completed clean**:

- `TODO` / `FIXME` / `NotImplemented` / `placeholder` / `stub` / `dummy` /
  `XXX` / `HACK` → **zero matches** across the entire engine source.
- Bare `pass` → 3 matches, all legitimate: two empty exception-subclass bodies
  (`_UnsupportedFormal`, `_DuplicateJsonKey`) and one `except OSError: pass`
  guarding a best-effort `chmod` during Swift-analyzer temp cleanup. No
  placeholder logic and no swallowed business errors.

This is an unusually clean result and materially raises confidence that the
engine's implementation is real rather than scaffolded. It does **not** say the
implementation is *correct* — only executed tests can say that, and the matrix
has not run.

Two further structural signals worth carrying forward:

- The engine's stated posture is genuinely fail-closed, not permissive: the
  README documents explicit refusals (`JAVA_FLOAT_PRECISION_OUTSIDE_CERTIFIED_SUBSET`,
  `SWIFT_OPERATOR_FOLDING_FAILED`, `SPECIALIZED_STRING_SEMANTICS_UNSUPPORTED`,
  `SPECIALIZED_CASE_OUTSIDE_CANONICAL_NO_ERROR_DOMAIN`, …) and the tests assert
  on those exact error codes rather than on generic exceptions. That is real
  boundary enforcement, not decoration.
- `test_language_set.py` contains an explicit anti-vacuity guard
  (`test_the_routed_set_is_not_empty_and_engine_only_is_not_everything`) whose
  docstring says it "guards against a future edit that 'fixes' this file by
  declaring every language engine-only, which would make every check below
  vacuous." The suite is written by someone anticipating gate-gaming — a point
  in favour of trusting its shape, though still not its execution.

---

## 2026-08-14 current-state override — supersedes the 2026-08-13 override above

The full 182-node matrix **completed with a real terminal summary line**:

```text
182 passed in 9791.03s (2:43:11)
```

One serial pytest process, no `-x`, `pytest_exit=0`, `freeze_verify_exit=0`,
window 2026-08-14T07:16:15Z → 09:59:27Z, head `badffaba`, freeze manifest
`e43733fc299a5c364e6045e175d6baafdb89c5190e23a149f0da36271082b15d`, log sha256
`758d6473db5350c9e1b2475b5b9e9cbc18100d5af6c709a0371b8576e1afa0e9`.
Full detail in `TEST_RESULTS.md` § "Session 2026-08-14".

Status changes:

- **R1–R7 → IMPLEMENTED (executed).** Their "⛔ not executed" runtime cells are
  now closed: the 2 contract/inventory nodes ran inside this matrix process and
  passed, alongside all 180 route nodes.
- **R8 → IMPLEMENTED.** The C# explicit-glob regression executed for real as
  part of the passing matrix; the `java→csharp` route passes SMALL and MEDIUM.
- **R9 → IMPLEMENTED.** Every one of the 90 directed routes passed **both**
  SMALL and MEDIUM in a single valid run. The earlier `BROKEN / NOT_RUN` and
  `PARTIAL` verdicts are superseded.
- **R10 remains MISSING.** Independent client-repository verification is still
  **0/90**. This is now the *only* requirement between the engine and a
  certification attempt.
- **R11 remains MISSING / `NOT_CERTIFIED`.** Unblocked on R9, still blocked on
  R10. Only a batch gate script may ever change this.

Definition-of-Done (see `TASK.md` §6):

```text
D1 static gates      ✅
D2 suite shape 182   ✅  (collect status: collected_nodes=182)
D3 freeze window     ✅  pinned e43733fc…, re-verified post-run
D4 full matrix run   ✅  182 passed, real summary, no -x, single process
D5 route success     ✅  90/90 directed routes, SMALL and MEDIUM
D6 independent ver.  ⛔  0/90
D7 certification     ⛔  NOT_CERTIFIED
```

Out of scope of this result and still open: K10 (engine Ruff `S105` ×2),
K11 (`sql-dialect-engine/.venv`), K12 (duplicate sanitiser), and the ArkUI /
Harmony profile, which stays `NOT_RUN` with `target_build=PASSED` because
`hdc list targets` returns `[Empty]`.
