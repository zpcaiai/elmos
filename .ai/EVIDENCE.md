# EVIDENCE.md

> Requirement → file → symbol → test → command → result.
> A row without an executed command is explicitly marked `NOT EXECUTED`.
> Nothing here is a certification claim.

Audit date: **2026-08-12** · Branch `feat/batch38-45-certification-toolchain` @ `f8c25fae`

## 2026-08-13 continuation evidence

| Requirement / defect | Implementation evidence | Executed evidence | Current verdict |
| --- | --- | --- | --- |
| Remaining MEDIUM tail | `.ai/matrix-tail47.log` | 38 passed, 9 Swift-source failed, 135 deselected in 8066.46 s | **PARTIAL**; all non-Swift tail routes passed |
| Infrastructure failures must not masquerade as unsupported semantics | `discovery.py` preserves inventory execution/integrity failures as `Verdict.NOT_RUN` while completed semantic enumeration failure remains a blocker | 2 targeted regressions passed | **IMPLEMENTED locally** |
| Analyzer snapshot GID must be exact and fail-closed | `native._normalize_private_analyzer_root_group` prechecks, changes group only, then postchecks identity and mode | `test_analyzer_snapshot_root_group.py`: 16 passed | **IMPLEMENTED locally** |
| Swift probe environment must equal sanitized environment | `native.py` and Swift tests include private deterministic `TEST_TELEMETRY_DIR` | `test_swift_analyzer_cache.py`: 33 passed | **IMPLEMENTED locally**; real route rerun disk-blocked |
| Frozen matrix shape | language-matrix collection | exactly 182 nodes | **VERIFIED** |
| Static engine gates | Ruff over `src tests tools`; strict mypy over all 22 source files; Python compile | Ruff pass; mypy pass for 22 files; compile exit 0 | **VERIFIED for stated scope** |
| Ten-language/90-route declared shape | `models.py`, `routes/inventory.json`, route packs | `test_language_set.py`: 12 passed | **VERIFIED locally** |
| Batch 29 repository contract | repository Schema files and gate tests | local Schema check: 2 valid; gate tests: 5 passed; official Make target network-blocked | **PARTIAL**; official target not green |
| Independent verification / certification | no independent campaign or eligible external evidence | 0/90; gate not run | **MISSING / NOT_CERTIFIED** |

The interrupted post-fix `swift→java` attempt is deliberately excluded from
route evidence. It was stopped solely to prevent disk exhaustion and produced
no valid route verdict.

---

## 1. Ten-language / 90-route expansion — statically verified

This is the one area where the handoff audit produced *new* independent
evidence. Codex's history contains a mid-flight report that the expansion was
incomplete:

> 当前唯一已知中间缺口是 test_language_set 与 routes/inventory 仍旧 72
> ("the only known intermediate gap is that test_language_set and
> routes/inventory are still 72")

**That gap is closed.** Direct inspection of the working tree:

### R1/R2/R3 — language and pair declarations

- **File:** `engines/polyglot-route-engine/src/elmos_polyglot_route/models.py`
- **Symbols:**
  - `Language` — `Literal` with 10 members: `java, python, csharp, typescript, javascript, go, rust, cpp, objc, swift`
  - `SUPPORTED_LANGUAGES` — same 10, as a tuple
  - `COMPLETE_MATRIX_LANGUAGES` — same 10; `ROUTED_LANGUAGES` aliases it
  - `SPECIALIZED_DIRECTED_PAIRS` — 8 explicit entries (cpp/objc/swift/java), unchanged
  - `NODEJS_DIRECTED_PAIRS` — comprehension over pairs containing `"javascript"` → 18
  - `COMPLETE_MATRIX_DIRECTED_PAIRS` — full directed permutation minus identity → 90
  - `ROUTED_PAIRS` — alias of the above
  - `is_routed_pair`, `is_specialized_pair`, `requires_concrete_source_spans`
- **Design note worth preserving:** the code comments state that
  `SPECIALIZED_DIRECTED_PAIRS` is deliberately *not* extended by the Node.js
  work because "that name and its eight entries are an immutable Batch 29 proof
  scope." The 18 JS directions therefore carry their own evidence/gate state.
  This is the correct call — it prevents the new routes from inheriting the
  exact-eight proof strength they have not earned.
- **Command:** `python3 -c "import elmos_polyglot_route.models …"` → **FAILED**,
  `ImportError: cannot import name 'StrEnum' from 'enum'` (bridge VM is
  Python 3.10; `equivalence.py` requires ≥ 3.11). Declarations were therefore
  read directly from source, not executed.
- **Result:** `NOT EXECUTED` — source-read verified.

### R4 — route pack completeness

- **Command:** `ls routes | grep -c -- '-to-'`
- **Result:** `90` ✅ (executed)
- **Command:** `ls routes | grep -v -- '-to-'`
- **Result:** `inventory.json` only — no stray directories ✅ (executed)

### R5 — inventory contents

- **File:** `routes/inventory.json`
- **Command:** `jq -r '{route_count, n_routes:(.routes|length), languages:(.languages|length), sets:(.route_sets|keys)}' routes/inventory.json`
- **Result** ✅ (executed):
  ```json
  {
    "route_count": 90,
    "n_routes": 90,
    "languages": 10,
    "sets": [
      "cpp-objc-swift-java-exact-8",
      "javascript-node26-completion-18",
      "legacy-complete-30",
      "nine-language-complete-72",
      "nine-language-completion-34",
      "ten-language-complete-90"
    ]
  }
  ```
  This matches the six route-set keys asserted in
  `tests/test_language_set.py::test_inventory_declares_the_complete_90_with_preserved_provenance_sets`
  exactly. Note the deliberate retention of `nine-language-complete-72` as a
  named provenance set — the pre-expansion surface is preserved rather than
  overwritten, so historical `x/72` evidence stays attributable.

### Corresponding test

- **File:** `engines/polyglot-route-engine/tests/test_language_set.py`
- **Nodes:** `test_route_contract_is_complete_ten_language_matrix_with_exact_subsets`,
  `test_every_declared_routed_pair_has_a_pack_and_nothing_else_does`,
  `test_inventory_declares_the_complete_90_with_preserved_provenance_sets`,
  `test_repository_orchestration_has_a_complete_ten_language_surface`,
  `test_concrete_span_policy_is_profile_and_route_specific`,
  `test_no_supported_language_remains_engine_only_after_explicit_matrix`
- **Command:** `pytest tests/test_language_set.py` → **NOT EXECUTED** (no runnable
  interpreter/toolchain via the bridge — see `HANDOFF.md` §3)

## 1b. C# assembly fix (R8) — Codex claim confirmed present in source

- **File:** `engines/polyglot-route-engine/src/elmos_polyglot_route/assembly.py`
- **Lines 1867–1884** emit the generated `polyglot-migrated-library.csproj`:
  ```xml
  <EnableDefaultCompileItems>false</EnableDefaultCompileItems>
  ...
  <Compile Include="src/**/*.cs" />
  ```
- **Test:** `tests/test_assembly.py:450`
  `test_csharp_build_compiles_only_assembled_sources_not_evidence_copies`
  — asserts both csproj strings, asserts the two `evidence/*/Migrated.cs`
  copies still exist (so auditability is preserved, not traded away), and then
  asserts `verify_assembled_project("csharp", destination)["build_verification_status"] == "PASSED"`,
  i.e. a **real** `dotnet build`, not a string check.
- **Command:** `pytest tests/test_assembly.py -k csharp_build` → **NOT EXECUTED**
  (no `dotnet` reachable). Codex reports it passing.

## 1c. Stub / fake-implementation sweep — clean

- **Command:** `rg -e '\bTODO\b' -e '\bFIXME\b' -e 'NotImplemented' -e 'placeholder' -e '\bstub\b' -e '\bdummy\b' -e '\bXXX\b' -e 'HACK' engines/polyglot-route-engine/src`
- **Result** ✅ (executed): **zero matches**
- **Command:** `rg -n '^\s+pass\s*$' engines/polyglot-route-engine/src`
- **Result** ✅ (executed): 3 matches —
  `equivalence.py:949` (`class _UnsupportedFormal(RouteError): pass`),
  `project_graph.py:485` (`class _DuplicateJsonKey(ValueError): pass`),
  `native.py:3320` (`except OSError: pass` around a best-effort `chmod` in
  Swift-analyzer temp cleanup). All legitimate.

## 1d. R12 — `stdout` discarded on external build failure (FIXED this session)

- **File:** `engines/polyglot-route-engine/src/elmos_polyglot_route/validation.py`
- **Defect symbol:** `_run()` — `detail = (completed.stderr or completed.stdout).strip()[-4_000:]`
- **Executed demonstration of the defect:**
  ```
  OLD detail -> 'Welcome to .NET! Telemetry is collected.'
  OLD contains the real diagnostic? False
  ```
  (input: `stdout="error CS0101: … definition for Migrated"`,
  `stderr="Welcome to .NET! Telemetry is collected."`)
- **Fix symbols:** `_failure_detail()`, `_FAILURE_STREAM_LIMIT`
- **Test file:** `engines/polyglot-route-engine/tests/test_native_validation.py`
- **Test symbols:** `test_failed_external_build_reports_stdout_even_when_stderr_is_noisy`,
  `test_failed_external_build_with_no_output_is_reported_explicitly`,
  `test_failed_external_build_bounds_each_stream_independently`
- **Command:** `PYTHONPATH=src python3 -m pytest tests/test_native_validation.py -p no:cacheprovider -k failed_external_build -v`
- **Result** ✅ **3 passed, 64 deselected in 0.08s** (Python 3.11.15, pytest 9.1.1)
- **Non-regression command:** whole module, baseline vs patched
- **Result** ✅ baseline `64 collected / 30 failed`, patched `67 collected / 30 failed`
  — same 30 environmental (`javac`/`swiftc`/`clang`-dependent) failures, 3 net new passes,
  0 new failures.

## 2. Repository identity

- **Command:** `git branch --show-current` → `feat/batch38-45-certification-toolchain` ✅
- **Command:** `git remote -v` → `origin https://github.com/zpcaiai/elmos.git` ✅
- **Command:** `git log --oneline -1` → `f8c25fae feat(frontend): harden pairwise formal equivalence evidence` ✅
- **Command:** `GIT_OPTIONAL_LOCKS=0 git status --porcelain -uno | wc -l` → `707` ✅

## 3. Host capability inventory (why nothing else could be executed)

- **Command:** `df -h /Users/stephen/DevProjects/AIProjects/elmos`
- **Result** ✅ (executed): `927G size · 926G used · 939M avail · 100%`
- **Command:** `for t in javac dotnet swift go rustc cargo mypy ruff pytest; do command -v $t; done`
- **Result** ✅ (executed): all `MISSING` in the bridge VM
- **Command:** `java -version` → `openjdk 11.0.31` (JRE; no `javac`)
- **Command:** `node -v` → `v22.22.3` (engine pins Node 26)
- **Command:** `python3 -V` → `Python 3.10.12` (engine needs ≥ 3.11)
- **Command:** `cat engines/polyglot-route-engine/.venv/pyvenv.cfg`
- **Result** ✅: `version_info = 3.12.12`, `home = /Users/stephen/Downloads/ENTER/bin`,
  `uv = 0.11.16` — a macOS venv; its `site-packages` contains darwin `.so`
  artefacts (`…__mypyc.cpython-312-darwin.so`, `rpds_py`) and is not loadable
  from the Linux bridge VM. Attempting to reuse it as a `PYTHONPATH` produced
  `ModuleNotFoundError: No module named 'exceptiongroup'`.

## 4. Codex-reported evidence — recorded, NOT verified

Carried forward verbatim so the next session can check it cheaply, but
explicitly **not** promoted to fact:

| Item | Codex-reported value |
| --- | --- |
| assembly source SHA after C# fix | `a750ed6b…c14b` |
| C# regression test SHA | `49e6ae2e…d81d` |
| R4 T0 source digest | `b25f2036…cac7` (6 828 files, 56 467 133 B) |
| R4 T0 external digest | `6970fb62…13f` |
| R4 T0 frontend digest | `6d0fcaa4…ecbb` (8 797 files) |
| Frozen frontend digests | `c05d…e2bb` / campaign `8265…84d35` |
| R4 snapshot shape | 18 389 regular files, 9 restricted Python-internal symlinks, all read-only; 12 core modules confirmed importing only from snapshot |
| Static gates | engine Ruff, changed-7 Ruff, strict mypy 22 files, `py_compile`, JS/TS `node --check` — all reported green |
| Collection count | `182` nodes exactly |
| Retained invalidated windows | R4b ≈ 1.12 GiB · R4c ≈ 0.68 GiB · R4d ≈ 2.53 GiB · R4e ≈ 0.51 GiB · R4f ≈ 0.53 GiB |

## 5. Recovered-history provenance

Codex sessions were read read-only from `~/.codex/sessions/**/rollout-*.jsonl`.
`~/.codex/auth.json` and every other credential-bearing file were **never
opened**. Nothing under `~/.codex` was modified.

Primary threads for the active task:

| Thread ID | Rollout file | Role |
| --- | --- | --- |
| `019fe3cf-d456-7291-be3e-db63ff75503b` | `2026/08/09/rollout-2026-08-09T07-57-56-…jsonl` (51 MB) | polyglot core / matrix / disk-space stop |
| `019fe3c7-c08c-7992-9260-38bfab959a0c` | (referenced via delegation) | frontend-client-engine, Batch 32/35 |
| `019ff183-e1e9-7853-9d8c-aa0b364dc135` | `2026/08/11/rollout-2026-08-11T23-49-39-…jsonl` (31 MB) | `java→csharp` failure, root cause, C# fix, R4 rebuild |
| `019ff188-f91f-7832-ac7e-d37112c5f2c9` | `2026/08/11/rollout-2026-08-11T23-55-13-…jsonl` (31 MB) | R3 snapshot integrity, static gates, collection = 182 |

417 rollout files exist in total; ~30 of the most recent were filtered by `cwd`
to isolate the elmos-scoped ones rather than loading the archive wholesale.

---

## 2026-08-20 current-session evidence ledger

### Python local binding frontend

| Evidence | Current result |
| --- | --- |
| `python_analyzer.py` | `ast.AnnAssign` emits typed IR `let`; bare/unbound/non-canonical forms fail with explicit source codes |
| `discovery.py` | new Python/LET source-domain rejections classify as `UNSUPPORTED`, not `NOT_RUN` |
| Atomic tests | 116 collected, exit 0 |
| Ruff / strict MyPy | PASS / PASS on the task-owned Python source scope |
| Real repository | clean LangGraph `49ae27c2ae983cfb92091b0dea9f7bc37a716479`: 447 tracked `.py`, 2 structural candidates, 0 analyzer READY |
| Measurement artifact | `.ai/python-let-real-repository-measurement-2026-08-20.json`, SHA-256 `8bf904c0792daaa591d5c4e5caa0a2f686beaa96ef0d6d45dcf23ab5ddc3d19e` |
| Decision | observed gain 0; keep profile v1; `NOT_CERTIFIED` |

The final four-file scope committed as `a1d842042` (and unchanged at
`fe836aab9`) has these SHA-256 values:

```text
discovery.py                     6b0daffc3fceeb1fc886d3d8619726e6971f54fc95cb6a4db2dc82bad288d9a7
python_analyzer.py               5b4247d1616b5b6afc09cd89b3a01670a6a0b2aa3b13eab5523f8238c362a3cf
test_repository_pipeline.py      034938a5196aed8dc0801e9cabcb5500144b9ab543262b455de5d8fe95d3bd5e
test_python_local_bindings.py     70d3e582ecea4f3989b7092206386a6428a4985d9cd82135c6b9416b3209c461
```

The matrix owner reported the sole `fixed2` repository matrix **223/223 PASS**,
the post-freeze set **503/503 PASS**, and pushed `a1d842042` plus `fe836aab9`
with local/tracking/remote SHA equality and an empty index. ArkUI/Harmony device
runtime evidence remains `NOT_RUN`; this result does not change certification.

### Execution Intelligence

- `make certify`, `make all`, and the CI readiness entrypoint are coded to
  propagate a nonzero decision instead of suppressing it.
- This protects only the command exit boundary. The local JSON/synthetic harness
  can still be authored by the same executor and lacks digest-bound signed
  provenance plus an independent verifier.
- 2026-08-20 exact-source local evidence: entrypoint regression `3 passed`; package
  tests `280 passed / 18 skipped`; Ruff, strict MyPy over 26 source files, and
  workflow YAML parsing passed. A fresh real `make certify` returned exit 2 and
  `BLOCK (pass 9 / fail 2 / not executed 0)` as required by the evidence floor.
- Readiness remains `BLOCK / NOT_CERTIFIED`; no local synthetic result is
  external, production, customer, or certification evidence.

### Snapshot CAS slice

> Historical pre-closure baseline. The dated 2026-08-24 evidence and the later current-source delta
> are recorded below; `NOT_RUN` statements in this subsection are not current.

- That historical source implemented capture-time archive/manifest roots as one atomic,
  generation-safe set; resource bindings separate immutable object metadata
  from repository/project ownership; and verified dual-read accepts legacy
  `cas:sha256:` and sized `cas://sha256/...` references under explicit modes.
- JDBC catalog rows now preserve labels and exact provenance digest size.
  Default-off tenant-local AES-GCM uses fresh nonces and tenant/key/digest-bound
  AAD. This is a local encrypted tier, not production KMS or rotation evidence.
- A durable JDBC ActionCache index now stores reconstructable metadata plus
  invalidation/quarantine state. The v2 signature subject covers the complete
  key/result/producer/risk/writer, and verified receipts/JDBC readback bind and
  recompute its envelope digest. Current focused negative tests passed;
  persisted trust decisions are still not cryptographically reverified against
  signature bytes, key policy or current revocation state on lookup.
- Evidence bound to that historical source: full `modules/cas` tests and focused
  catalog/GC, ActionCache/encryption, snapshot/integrations, persistence
  migration and portfolio tests passed; control-plane main compile/package and
  task-scoped static checks passed. The ordinary control-plane testCompile is
  `BLOCKED_BY_UNRELATED_TEST_COMPILE` by the out-of-scope ChinaDB test constructor.
  Live PostgreSQL, Docker/provider validation and a real two-process shared tier
  remain `NOT_RUN`.
- Still unresolved: snapshot delete/release caller, commit-unknown root
  reconciliation, tenant-unscoped legacy reads, the workspace-service legacy-only path,
  production KMS/key rotation, live PostgreSQL, a real shared object tier,
  ActionCache execution wiring and trust revalidation, and the portfolio
  process-local key→digest index.
- The collector now treats missing/unreadable/substituted roots and unknown or malformed
  manifests as unresolved and blocks the entire sweep; no production collector/delete caller
  or complete retention/deletion lifecycle has been evidenced. Catalogue loads preserve legal
  hold, but a hold applied after load can still race the later store delete without an atomic
  production GC epoch/lock.
- Runtime posture remains default-off `SINGLE_HOST / NOT_CERTIFIED`; no
  cross-instance, at-rest production, GC-complete, or certification claim is
  supported.

No local result in this section changes R10 independent-client evidence,
external verification, customer evidence, production evidence, or
`certified_route_count=0`.

### 2026-08-24 CAS / Snapshot / EI evidence correction

The rows below are retained as exact-source, exact-environment evidence from
2026-08-24. Later CAS/catalog, tiering, ActionKey/dispatcher, workspace materialization,
snapshot archiving and pre-V9 bootstrap changes are not covered by these Maven, JUnit,
PostgreSQL or MinIO runs and must not be described as current-source regression results.

| Evidence | Result | Supported claim |
| --- | --- | --- |
| Java focused Maven scope | 197/197 PASS across 34 classes | the 2026-08-24 task-owned Java contracts compiled and passed locally; this is historical exact-source evidence |
| PostgreSQL 17 / Flyway | V72 reached; 72/72 validated and applied in both final live runs | fresh-schema migration is executable locally; not a historical production upgrade proof |
| CAS JDBC live | 10/10 PASS, no skip | catalog metadata, roots, durable ActionCache and current-trust invalidation work on a real local PostgreSQL |
| Snapshot/RLS/webhook live | 5/5 PASS, no skip | tenant context resets, immutable lifecycle, stale reconciliation and signed-webhook tenant routing work on a real local PostgreSQL |
| Snapshot lease/scheduler live | 3/3 PASS, no skip | fenced lease contention/recovery and bounded tenant-fair queue claiming work on a disposable PostgreSQL 17.5 instance |
| MinIO process probe | PASS, PIDs 35250/35273, digest `a5f0c1b47f09bc1dcdd8d090143d9d2cef194ace81a91173e49690a214842c09`, 75 bytes | two distinct JVMs share an external object tier on one host |
| EI package | 299 pass / 11 skip; PG conformance 22 pass / 0 skip | local code plus real local PostgreSQL backend contract |
| EI static/install | Ruff PASS; strict MyPy PASS over 28 sources; wheel 25/7/2 resources PASS | source and installed-package engineering integrity |
| EI external trust | focused pytest 48/48; Ruff PASS; strict MyPy PASS over 29 sources | digest-pinned authority root, signed monotonic trust snapshot and fresh revocation cache fail closed locally |
| EI gate | schema-valid thin evidence -> `BLOCK`, exit 2; empty evidence -> `NOT_CERTIFIED` | failure and missing evidence both fail closed without conflation |
| GitHub App evidence harness | unittest 17/17; Ruff PASS | local request/receipt/reconciliation contract only; no real App, delivery, redelivery or production DB |
| Multi-host Kubernetes probe | bash/static PASS; missing-config negative exit 2 | fail-closed harness only; no cluster was contacted and no two-host evidence exists |
| ArkUI/Harmony | `hdc` 3.2.0b; `hdc list targets -v` -> `[Empty]` | `NOT_RUN`, no device evidence |

MinIO raw receipt directory:
`.ai/cas-two-process-shared-tier-20260824T070853Z/`. Its own summary says
`SINGLE_HOST_EXTERNAL_PROCESS`, `LOCAL_EXECUTED_SELF_ATTESTED`, and `NOT_CERTIFIED`.

The local KMS tests validate provider binding, AAD, zeroization and startup refusal when no provider
exists; they do not exercise a production KMS/HSM. ActionCache now has an opt-in asynchronous
durable hit-or-enqueue dispatcher that refuses to start unless exactly one current-trust
revalidator, identity-bound authorizer, typed payload policy and durable `ExecutionJobPort` are
supplied. The repository does contain a JDBC execution-job adapter, but the dispatcher is not bound
to the tenant API and no deployment-owned production authorizer, payload policy or independently
governed trust/revocation authority is supplied. The job port also has no authoritative lookup by
idempotency key, so an uncertain enqueue remains `UNKNOWN_RECONCILIATION_REQUIRED` and is not
blindly retried. Runner completion lacks a signed `ActionResult`, output manifest and provenance,
so completion write-back is intentionally absent.

V72 provides fenced materialization leases and a bounded global reconciliation queue, with exact
runtime-role function grants. Its disposable PostgreSQL tests do not establish deployment of stable
holder identities, scheduler election, production archive/GC participation or cross-host behavior.
The GitHub evidence collector has fail-closed local tests, but no real App or delivery was used. A
fresh 72-migration database does not cure the pre-existing V9 ordering hazard for a database containing
historical `audit_events`. The current pre-V9 bootstrap is default-read-only, requires a durable
pending receipt before an apply-mode database connection, never writes Flyway history, and preserves
mutation/commit/rollback acknowledgement loss as `OUTCOME_UNKNOWN`; only a confirmed rollback may
produce `BLOCKED`. `py_compile` and its focused unittest suite passed 18/18, but no real historical
PostgreSQL assess/apply run has been executed.

#### Current post-2026-08-24 source delta

Current code adds the following bounded engineering capabilities:

- `CasCatalog` requires atomic metadata-plus-root publication and exact-generation release;
  JDBC uses a single tenant transaction and logical-root lock, while the in-memory implementation
  rolls metadata and roots back if publication fails.
- `TieredCasStore` propagates durable writes through nested tiers, retains a failed flush item for
  retry, and coordinates local access, write-back, reclaim and eviction state under locks.
- portfolio ActionCache mappings use durable `CasCatalog` `ACTION_CACHE` logical roots, publish only
  after `putDurable`, support complete-manifest lookup and generation-bound invalidation, and do not
  revoke a global root merely because one process misses its transient tier.
- ActionKey v2 uses schema-owned component order and structured compound digests with no v1 fallback;
  the asynchronous dispatcher performs exact-key and tenant checks before ordered authorization,
  bounds canonical payloads, persists a request digest and fails closed on uncertain queue outcomes.
- workspace snapshot reads are CAS-first; legacy compatibility is default-denied and, when explicitly
  enabled, remains digest-verified. The RLS resolver binds organization/snapshot/run in a fresh
  transaction. Materialization uses a bounded private no-follow spool and rejects traversal,
  escaping links, special files, privileged metadata and unsupported tar extensions. The deterministic
  archiver applies no-follow identity and node/file bounds.

The validation boundary for this current delta is intentionally narrow: pre-V9 `py_compile` plus
unittest **18/18 PASS**, and targeted `javac` for the Tiered/Compatible slices **PASS**. Current-delta
Maven/JUnit, live PostgreSQL and MinIO validation are **NOT_RUN** and await this task's focused
reverification. The 2026-08-24 results above cannot be reused to close that gap.

Supported status therefore remains exactly:

- CAS: `SINGLE_HOST / NOT_CERTIFIED`
- Execution Intelligence: `BLOCK / NOT_CERTIFIED`
- ArkUI/Harmony device: `NOT_RUN / NOT_CERTIFIED`

### 2026-08-26 current-source focused revalidation

The current CAS/snapshot source was revalidated with JDK 21 using only the task-owned focused
classes. The CAS, snapshot, integrations and portfolio set reported 197 tests, 0 failures, 0
errors and 2 explicit filesystem-assumption skips: 195 executed tests passed. Both skips are
symlink-inode hard-link-anchor cases on the current filesystem; they are not counted as passed.
The workspace/control-plane set passed 63/63, and the pre-V9 bootstrap unittest remained 18/18.

This source now has a local repository resource-lifecycle protocol: epoch-bound ACTIVE -> RETIRING
-> RETIRED transitions, durable root-to-resource edges, a retirement write fence, exact-generation
root release, and batch binding release only after all mapped and legacy roots are inactive. It is
an API/protocol result, not a production deletion result: no control-plane, webhook or repository
deletion caller invokes repository retirement. Production resource reclamation therefore remains
blocked.

V76 adds atomic deletion tombstones and lifecycle fences, including one tenant -> resource ->
sorted-object -> logical-root lock order. Its live PostgreSQL test did not run: the persistence
module test compilation is currently blocked by the unrelated `WalletMigrationContractTest` lambda
compile error. No V76/Flyway/live-PostgreSQL claim is made.

Production snapshot capture is intentionally fail closed. The control-plane requires an
authoritative fenced source lease, rejects legacy reusable rows without persisted lease provenance,
and the only JGit adapter currently supplies a local self-attestation. Therefore both new and reuse
production capture paths are `BLOCKED`, not passed. Docker materialization unit tests verify bounded
spooling, canonical tar/PAX validation and an explicit helper ENTRYPOINT/CMD, but no Docker runtime
or cross-host materialization was executed.

The final status remains exactly CAS `SINGLE_HOST / NOT_CERTIFIED`, Execution Intelligence
`BLOCK / NOT_CERTIFIED`, and ArkUI/Harmony `NOT_RUN / NOT_CERTIFIED`.
