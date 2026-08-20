# BUILD_CACHE_HANDOFF.md

> Read this before touching `engines/build-cache-engine/`.
> Companions: `BUILD_CACHE_TASK.md`, `BUILD_CACHE_IMPLEMENTATION_STATUS.md`,
> `BUILD_CACHE_TEST_RESULTS.md`, `BUILD_CACHE_EVIDENCE.md`.

- **Last updated:** 2026-08-20 (pass 4)
- **Written by:** Claude (Cowork cloud session)
- **Overall status:** `CERTIFIED_IN_SANDBOX` — 31/31 skills implemented,
  **933 tests (926 pass, 7 skip)**, 1 skill `PARTIAL` and only because two
  toolchains do not exist for this platform.

## 0. What landed in pass 4

Passes 1 and 2 are committed. **Pass 3 was delivered but never committed** —
`git status` still shows `elmos_route_stages.py`, `tools/`, `tests/fixtures/`,
`test_overlay.py` and `test_snapshot_portability.py` as untracked and
`snapshot.py`, `native_adapters.py` and `test_native_toolchains.py` as
modified. So the next commit carries **passes 3 and 4 together**. Nothing
earlier was deleted by either pass.

```text
engines/build-cache-engine/                          46 modules, 24 322 lines · 41 test files, 12 165 lines
agent-skills/packages/elmos-build-cache-staging-sota/ the v1.1.0 package, vendored and validated on the Mac
agent-skills/runtime/                                 31 SKILL.md installed (7 new)
.ai/BUILD_CACHE_*.md                                  this evidence set
```

The input was `elmos-build-cache-staging-sota-skills-v1.1.0`: the 24 existing
skills re-stamped to `version: 1.1.0`, plus **7 new P8 skills** implemented as
7 new modules.

New engine files:

| Path | What it is |
| --- | --- |
| `src/elmos_build_cache/cache_policy.py` | The policy SPI and six policies: LRU (baseline), SIEVE, S3-FIFO, W-TinyLFU, size-aware TinyLFU, GDSF |
| `src/elmos_build_cache/cache_trace.py` | Privacy-preserving trace capture, corpora with time-separated splits, leakage/drift detection, ten workload generators |
| `src/elmos_build_cache/cache_simulator.py` | Equal-capacity replay, five objective profiles, gates, the benchmark report |
| `src/elmos_build_cache/cache_admission.py` | Cost/value-based admission with cost provenance and per-tenant quotas |
| `src/elmos_build_cache/dag_prefetch.py` | Next-use index built from the real `ConversionDag`, prefetch budgets, locality-aware placement |
| `src/elmos_build_cache/policy_orchestrator.py` | Rule-based selection over workload fingerprints, policy epochs, shadow policies, pinned fallback |
| `src/elmos_build_cache/learned_control.py` | Off-path bounded parameter tuning, signed model registry, clipping as the safety property |
| `src/elmos_build_cache/policy_certification.py` | Benchmark matrix, Pareto frontier, signed certificates, the rollout ladder |
| `src/elmos_build_cache/policy_plane.py` | The one place configuration becomes behaviour; held by `ConversionPipeline` and wired into its probe, commit and wave-boundary paths |
| `schemas/cache-{policy,trace-event,benchmark-report}.schema.json` | Three new contract schemas (and their `_data/` copies) |
| `tests/test_{cache_policy,cache_trace,cache_simulator,cache_admission,dag_prefetch,policy_orchestrator,learned_control,sota_acceptance,policy_integration}.py` | 292 new tests |

**Changed behaviour worth knowing about:**

- **`package_version` is now `1.1.0`** in `config/elmos-cache.yaml` and
  `CacheConfig`. It is declarative and is **not** folded into any digest, so
  this does *not* cause a cold run.
- **`config/elmos-cache.yaml` gains a `policy:` section.** The loader is total,
  so an unknown key in it is an error. Every SOTA behaviour in it defaults to
  off: no adaptive switching, no learned tuning, no trace capture, no prefetch.
- **`HotIndex` now takes a policy.** With `policy.enabled: true` (the shipped
  default) the in-process action-cache index runs W-TinyLFU instead of the
  built-in LRU. It is an accelerator and never authoritative, so this cannot
  change any answer — only how often a database read is skipped. Set
  `policy.enabled: false` for the previous behaviour exactly.
- **`GarbageCollector` gained an optional `replacement` policy.** When set (the
  CLI sets it from `policy.l2_policy`), it re-orders deletion candidates and
  annotates each `reason` with `policy=… rank=…`. It cannot change *which*
  objects are candidates — the root set decides that, and is declared to the
  policy first.
- **`CachePolicy.forget()` is new**, and `PolicyCounters` gained
  `invalidations`. A revocation is not an eviction and is no longer counted as
  one.
- **A W-TinyLFU bug was fixed.** It ran its frequency contest against a
  main-region incumbent that was not competing for the slot, so a cache with
  free space rejected newcomers and never warmed. If you have benchmark numbers
  from before this pass, they are wrong for W-TinyLFU and size-aware TinyLFU.
- **New CLI groups: `policy` and `trace`** — seven read-only commands. None of
  them mutate the cache.
- **`ConversionPipeline` gained a `signer` keyword.** It is optional and only
  required when `policy.learned_tuning` is on: an unsigned model registry
  cannot verify what it loads, so the plane refuses to construct rather than
  degrading quietly.
- **`RunReport` gained a `policy` field.** `None` unless something in the
  `policy` section is switched on, so an opted-out report is byte-identical to
  what it was before.

## 1b. What landed in pass 3

Passes 1 and 2 are committed. This is a **third, additive** change; nothing
earlier was deleted and nothing outside these two paths was touched.

```text
engines/build-cache-engine/          (pass 3 state: 38 modules, 18 573 lines · 33 test files, 9 166 lines)
.ai/BUILD_CACHE_*.md                 this evidence set
```

New files:

| Path | What it is |
| --- | --- |
| `src/elmos_build_cache/elmos_route_stages.py` | The bridge to `engines/polyglot-route-engine`: ELMOS's own analyzer, IR and emitter as cache stages |
| `tools/cross_platform_snapshot.py` | Builds one fixed repository and prints this host's snapshot digest |
| `tests/fixtures/cross_platform_snapshot.json` | The digests captured so far, per platform and per filesystem |
| `tests/test_elmos_route_stages.py` | 16 tests driving the real conversion engine |
| `tests/test_overlay.py` | 36 tests, including a real kernel overlayfs mount |
| `tests/test_snapshot_portability.py` | 21 tests: the captured fixture plus the hazard audit |

Changed behaviour worth knowing about:

- **Snapshot logical paths are now composed to NFC.** A decomposed macOS
  spelling used to produce a different root digest for the same checkout. This
  is a fix, and it **moves the root digest of any repository with non-ASCII
  decomposed filenames** — expect one cold pass for those.
- **`snapshot.portability_findings(snapshot)`** is new: case collisions,
  normalisation folds, Windows reserved names and illegal characters, trailing
  dots and spaces, over-long paths, symlinks. It is a report, not an error; the
  caller decides.
- **`GradleMavenAdapter` env changed**: `MAVEN_OPTS_REPO` (never read by
  anything) became `MAVEN_REPO_LOCAL`, plus a derived
  `MAVEN_OPTS=-Dmaven.repo.local=…` which Maven actually honours. The adapter's
  fingerprint therefore moves — a one-off miss on that adapter.
- `NativeBuildCacheAdapter.derived_environment()` is a new hook for variables
  whose value is not a bare path.

## 1. Commit — do this yourself

The cloud session's bridge to the Mac **cannot delete files**, so any `git`
command that needs a lock leaves undeletable debris. No `git` command was run.

```bash
cd ~/DevProjects/AIProjects/elmos
# add narrowly: `agent-skills/runtime/` also holds unrelated untracked work
# (chinadb-* skills) that must not be swept into this commit
git add engines/build-cache-engine
git add agent-skills/packages/elmos-build-cache-staging-sota
git add 'agent-skills/runtime/elmos-*'
git add .ai/BUILD_CACHE_*.md

git status --short          # expect ~64 staged paths, no chinadb-*, no .venv
git commit -m "feat(build-cache): bridge the real conversion engine and implement the v1.1.0 SOTA cache-policy plane"
git push
```

`agent-skills/packages/_to_delete/elmos-build-cache-staging-sota-v1.1.0.tar.gz`
is the transfer tarball; the bridge cannot delete, so remove it yourself.

Two scratch directories were left on your Mac by the cross-platform capture and
cannot be removed from here:
`~/DevProjects/AIProjects/elmos/.ai-tmp/xplat-probe` and
`~/DevProjects/AIProjects/elmos/.ai-tmp/xplat-fixture`. Delete them at your
convenience.

## 2. Reproduce the gates

```bash
cd engines/build-cache-engine
python3.12 -m venv .venv
.venv/bin/pip install -e '.[postgres,s3]' ruff==0.12.5 mypy==1.17.0 pytest==8.4.1 'moto[s3,server]>=5.0'

.venv/bin/ruff check src tests tools
.venv/bin/mypy
.venv/bin/pytest tests                        # PostgreSQL rows skip without the DSN
ELMOS_TEST_POSTGRES_DSN=postgresql://user:pw@127.0.0.1:5432/elmos_cache .venv/bin/pytest tests
.venv/bin/pytest tests -m "not toolchain"     # skip the real build tools

cd ../../agent-skills/packages/elmos-build-cache-staging-sota && ./validate.sh

# the policy plane, from the operator surface
cd engines/build-cache-engine
.venv/bin/elmos-cache policy show
.venv/bin/elmos-cache policy matrix          # 30 cells; no_single_winner must stay true
.venv/bin/elmos-cache policy benchmark --workload monorepo-scan --capacity-fraction 0.05
```

**The Mac's system Python is 3.10 and cannot run this engine.** Use 3.12.
`tools/cross_platform_snapshot.py` deliberately runs on 3.10+, so it can be
executed on hosts that cannot run the engine.

The route-engine tests find `engines/polyglot-route-engine/src` as a sibling
automatically; `ELMOS_POLYGLOT_ROUTE_SRC` overrides that. They need
`z3-solver` (the route engine's own dependency) importable.

## 3. Ordered next steps

| # | Work | Why it matters | Closes |
| --- | --- | --- | --- |
| 1 | **Capture the two missing snapshot digests.** `python3 tools/cross_platform_snapshot.py` on macOS natively and on Windows, then paste each JSON line into `tests/fixtures/cross_platform_snapshot.json` under `platforms`. The test asserts agreement automatically and stops skipping. | Gate 1's last two rows. Two commands. | gate 1 |
| 2 | **Calibrate `observability.DEFAULT_SLOS`.** Run the ten `BENCHMARK_SCENARIOS` against a real ELMOS conversion corpus and replace the estimates (95 % no-change, 70 % small-change). | PERF-001/002 measure a harness plus small real builds, not a workload. | gate 9 |
| 3 | **Run the route bridge on the pinned host.** On Darwin/arm64 with the engine's toolchain trees present, `RouteStages(strict_toolchain=True)` will produce *pinned* toolchain digests and the non-Python analyzers become reachable. Everything else is already wired. | Turns the bridge's one refusal into a full route. | — |
| 4 | **Issue a production certificate over a real ELMOS output tree.** `CertificationService` issues, verifies and revokes today, but has never bound a certificate to a real conversion's tree digest. | gate 10 | gate 10 |
| 5 | **Certify Xcode/Swift and Flutter/pub** on a machine that has them: `tests/test_native_toolchains.py` has a slot for each, and the cold/warm/import/clean-room shape the other seven use is right there to copy. | 2 of 10 adapters uncertified against their tool. | — |
| 6 | **A full Maven build** where Central is reachable. Redirection is certified; resolution is not. | — | — |
| 7 | **Key management.** `Ed25519ProvenanceSigner` holds raw key bytes; back it with a KMS/HSM. The interface is designed for that substitution and `public_keyset()` already exposes only verification material. | The private key still lives in the process. | — |
| 8 | **AWS-specific S3 behaviour** — IAM denial paths, lifecycle rules, regional consistency — against a real bucket. | REMOTE rows are certified against S3 *semantics*, not against AWS. | — |

## 3b. Ordered next steps for the policy plane

| # | Work | Why it matters |
| --- | --- | --- |
| 1 | **Capture real traces.** Turn on `policy.trace_capture` in one project, let it run, then `elmos-cache trace verify` and re-run `policy matrix` against the captured corpus. Everything downstream — selection, tuning, certification — is currently reasoning about synthetic workloads. | The single biggest gap in this pass. |
| 2 | **Run one policy through the ladder.** `SIMULATOR → SHADOW` costs nothing (shadow policies observe, they do not serve). Only after shadow evidence exists is a canary meaningful. | The ladder is tested but has never carried a real deployment. |
| 3 | **Consider admission at the CAS write path too.** It is now consulted before an action-cache *entry* is recorded (`policy.admission_enabled`), which is the safe seam: the artifact is already sealed and promoted, so a refusal costs a recomputation and never a file. Extending it to refuse the CAS write itself is a bigger step and touches authoritative storage. | Would turn a recomputation saving into a storage saving. |
| 4 | **Give certification a real key.** `policy certify` without `--signing-key` uses an ephemeral key and says so in the output. Point it at the same key hierarchy as provenance. | A certificate nobody else can verify is a note to self. |
| 5 | **Calibrate `CostModel`.** `token_ms`, `storage_ms_per_mb`, `pollution_ms_per_mb` and `trust_risk_ms` are engineering estimates. Every admission decision is downstream of them. | The value function is only as good as its constants. |

## 4. Design decisions worth knowing before you change things

- **The policy plane may not decide correctness.** `cache_policy` cannot see
  validation levels as an authority, only as a weight; `ActionCache`'s policy
  checks are untouched by it. If you find yourself passing a `ValidationLevel`
  into an eviction decision as a *gate*, stop.
- **Protected roots are refused admission, never evicted.** When only protected
  objects remain, `_make_room` returns `CAPACITY_FULLY_PROTECTED` and the
  newcomer is what gives way. Do not "fix" this by evicting a pin.
- **`state_digest()` excludes counters on purpose.** Two caches that took the
  same decisions have the same state; hit counts are observation, not state.
- **Object size is immutable per key.** A size change for a live key is a
  `ContractViolation`. Keys are content-addressed, so a size change means the
  caller is confused about identity.
- **`forget()` is not `_evict_one()`.** Anything that removes an entry for
  correctness reasons must go through `forget`, or the churn and eviction
  metrics start describing something that did not happen.
- **The hot index was chosen as the first seam deliberately.** It is never
  authoritative. Do not promote the policy plane to the CAS until it has run
  there for a while.
- **Clipping, not accuracy, is what makes the learned controller safe.** A
  perfectly accurate model with no bounds is more dangerous than a mediocre one
  with them.

- **The route bridge is keyed on the IR, not the file.** That is the entire
  reason it bridges at `semantic-ir` rather than at the source. If you move the
  key to the source digest, every comment costs a re-emission.
- **The bridge refuses rather than substitutes.** A toolchain the route engine
  does not pin produces `RouteEngineUnavailable` in strict mode, and an
  explicitly unpinned identity in permissive mode — never a plausible-looking
  digest. Two different compilers sharing one cache entry is the failure this
  prevents.
- **`TEST_VERIFIED` is earned by execution.** `differential_check` compiles the
  emitted Java and runs it against the Python original. If you make it return
  `True` by default you have removed the only thing standing between a wrong
  translation and every downstream consumer.
- **Function bodies are never walked for symbols** (`treesitter_hash._Walker`);
  walking a body would turn locals into public API.
- **Signature text is masked, body text is not.** A literal inside an annotation
  is *surface*, tracked by `surface_digest`.
- **Snapshot paths are composed to NFC** at record time. Do not "optimise" that
  away: it is the difference between one digest and two.
- **`ABORTED → RESERVED` is the only backwards edge** in the staged-file state
  machine. Do not add others.
- **Two operations deliberately commit before raising**: nondeterminism
  quarantine (`action_cache`) and staged-file abort (`staging`).
- **`cas.materialize` never hardlinks by default**; `share="link"` is opt-in.
- **Restore is a full lifecycle** — `pipeline._restore` claims a lease and
  re-stages every cached output through reserve → seal → promote.
- **The contract data exists twice on purpose**: `schemas/`, `openapi/`,
  `migrations/` for humans, `src/elmos_build_cache/_data/` for imports.
  `test_repository_contract_copies_match_the_packaged_ones` fails if they drift.

## 5. Known hazards

- `sqlite3` + `synchronous=FULL` + `journal_mode=WAL` is the local profile. Do
  not put the metadata file on NFS.
- The chaos harness and the overlay test mount real filesystems through
  `ctypes`. They need `CAP_SYS_ADMIN`; without it they skip rather than
  pretending.
- `FilesystemRemoteBackend.fail` is a chaos hook, not a feature flag.
- The `elmos-cache` CLI defaults `--tenant default`; always pass `--tenant`.
- Toolchain tests really invoke compilers, and the route-engine tests really
  run `javac` and `java`. Both are marked `toolchain`-adjacent; use
  `-m "not toolchain"` where that is unwanted.
- `elmos_route_stages._python_reference` executes the source module to get an
  oracle for the differential run. It is a test-time path over first-party
  source; do not point it at untrusted input.
- `policy matrix` replays 10 workloads × 3 capacities × 6 policies. It takes
  around a minute and allocates freely; it is not something to call per request.
- A `CachePolicyCertificate` binds to a corpus, a capacity, an objective, a
  commit and a hardware profile. Changing any of them expires it —
  `expired_reasons()` tells you which. Do not carry a certificate across a
  capacity change.
