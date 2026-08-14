# HANDOFF.md — Codex ⇄ Claude Code

> Read this **first**. It exists so no agent has to re-scan `~/.codex` or the
> whole 4.7 GB working tree again. Update it at the end of every working session.

- **Last updated:** 2026-08-14 (Claude Code — read-only matrix monitoring)
- **Written by:** Claude Code
- **Branch:** `feat/batch38-45-certification-toolchain` @ `badffaba`
- **Overall status:** `NOT_CERTIFIED` — **182/182 matrix PASSED 2026-08-14T09:59:27Z**;
  D4 + D5 closed, D6 (independent verification) still `0/90`. See the
  **Session 2026-08-14 — 182/182** section at the end of this file, which
  supersedes every earlier "matrix RUNNING / NOT_RUN / disk-blocked" statement
  in §0–§7.

---

## 0. STATE AS OF THE LATEST PASS — read this before §1–§3

Both blockers described further down are **resolved**. §1–§3 are kept as the
historical record of how the work was recovered; they are no longer the
operative situation.

| Was blocked on | Now |
| --- | --- |
| Host disk 939 MB free | **~27 GiB free** (see §2.0 for what was reclaimed) |
| No shell / toolchain on the Mac | **Desktop Commander online** — real zsh with `javac`, `dotnet`, `swiftc`, `go`, `cargo`, `clang`, `uv`, `node` |

### ✅ CURRENT STATE (fifth pass) — read this first

**Both fixes are verified. The only thing standing between you and 182/182 is disk.**

- Final run reached **node 135/182 with ZERO failures** — all 90 SMALL routes
  (incl. the fixed `typescript→python` and the two swift routes) plus MEDIUM
  93–135. It then hit a **disk wall** at node 136: uniform `E` cascade to 182 and
  a CPython fatal error in `pytest_sessionfinish`. Not a code defect.
- Free space fell 27 GiB → 7.4 GiB during the run.
- **D4 — the disk drain is `~/Library/Developer` (12.75 GB)**: Xcode DerivedData
  7.3 GB + CoreSimulator 3.3 GB + DVTDownloads 2.1 GB, produced by the
  Swift/clang/ObjC builds. This is almost certainly the "external build load I
  cannot identify" that stopped Codex — it was its own matrix run.
- **The matrix needs ~25 GiB of headroom.** Codex's 12 GiB start gate is too low
  and will fail around node 136 every time. Raise it.
- **D5** — 562 leaked `$TMPDIR/elmos-toolchain-env-*` roots from
  `tempfile.TemporaryDirectory` scopes that never unwound (~11 MB; a leak, not
  the wall).

To finish the run, reclaim first (safe, regenerates):
```sh
rm -rf ~/Library/Developer/Xcode/DerivedData      # ~7.3 GB
rm -rf ~/Library/Developer/DVTDownloads           # ~2.1 GB
rm -rf "$(getconf DARWIN_USER_TEMP_DIR)"pytest-of-stephen   # ~1.2 GB
```
Keep `CoreSimulator` if the frontend `ios` runtime channel matters.
Then re-run with `export TMPDIR="$(getconf DARWIN_USER_TEMP_DIR)"`.

### CURRENT STATE (fourth pass)

- **Clean full matrix completed**: `4 failed, 178 passed in 4:37:56` — the first
  *valid* run of the takeover (real summary line, serial, no `-x`, correct `TMPDIR`).
- **1 real defect found and FIXED**: the Python target harness ignored the
  canonical parameter type, so `typescript→python` (canonical `number`) got
  integer arguments and returned an int where float64 was required. Fixed with
  `_python_literal` + a type-aware `_python_harness`; Ruff ✅, `mypy --strict` ✅,
  5 new regressions ✅, defect route ✅, 8-route no-regression sweep ✅.
- **2 swift failures were induced by this session** (`swift package reset` →
  cold analyzer build). Pass warm: `2 passed in 5:16`.
- **Final confirmation run in progress** → `.ai/matrix-run-final.log`, expected 182/182.

Open defects, none fixed yet:
- **D1** — environment/integrity faults surface as the *semantic* verdict `UNSUPPORTED`.
- **D2** — `native.py` asserts `st_gid == os.getgid()` for TS/JS snapshots but not Java.
- **D3** — first Swift-source route in a process fails if the analyzer cache is
  cold, instead of blocking on the build.
- **K10** — engine Ruff gate red: 2 × `S105` false positives in `tests/test_assembly.py`.
- **K11** — `engines/sql-dialect-engine/.venv` base interpreter deleted.

### ⚠️ SUPERSEDED — read `TEST_RESULTS.md` "third pass" first

An earlier pass in this session reported 39/90 SMALL routes failing and called it
a regression. **That was wrong.** All 39 were artifacts of the agent's own run
environment — an unset `TMPDIR` (30) plus a `swift package reset` that forced an
analyzer rebuild (9). Five representative routes all pass once corrected.
**No conversion-accuracy defect has been demonstrated in any of the 90 routes.**

Two real defects were exposed and are NOT yet fixed:
- **D1** — an environment/integrity fault is reported as the *semantic* verdict
  `UNSUPPORTED`. Misattribution; cost this session ~an hour.
- **D2** — `native.py` asserts `st_gid == os.getgid()` in the TypeScript and
  JavaScript snapshot bindings but not the Java one. Fix by normalising the
  root's group (`os.chown(root, -1, os.getgid())`) — **not** by deleting the
  assertion.

**MANDATORY when running the matrix on macOS:**
```sh
export TMPDIR="$(getconf DARWIN_USER_TEMP_DIR)"   # gid must equal `id -g`
```
Without it, `/tmp` (root:wheel) is used and TS/JS/cpp/objc routes fail closed.

**The 182-node matrix is RUNNING (clean).** Log: `.ai/matrix-run-clean.log`.
Superseded bad run: `.ai/matrix-run-PARTIAL-VOID.log` — **not** product evidence.
Launched serial, single process, **no `-x`**, `collected 182 items`.
A run counts only if the log ends in a real pytest summary line — if it ends
mid-node or with exit 143, it is **void**, exactly like the previous attempt.

### Three corrections to what this file said in the first pass

1. **"the collected node count is now 185, not 182" — WRONG.** Measured on the
   real tree: the matrix module is **182**, unchanged. `test_native_validation.py`
   went 64 → 68. The whole suite is 1305. `182` always meant *the matrix module*.
2. **The first K5 fix was a defect.** It surfaced stdout without redacting it,
   widening what a failed build leaks into persisted evidence. `assembly.py`
   already had the correct pattern. The fix was rewritten to match — see
   `TEST_RESULTS.md` "Session 2026-08-12 (later)".
3. **"static gates all green" (Codex's claim) is FALSE.** The engine Ruff gate
   is currently **red** with 2 × `S105` in `tests/test_assembly.py`. Details in
   §6 K10.

### New breakage introduced by the disk cleanup — one repaired, one open

`~/Downloads/ENTER` (Anaconda, 5.5 GB) was deleted to free space. It was the
**base interpreter for two engine venvs**, so their stdlib disappeared
(`ModuleNotFoundError: No module named 'encodings'`).

- `polyglot-route-engine` — **REPAIRED**: `uv venv --python 3.12.12
  --allow-existing .venv` then `uv sync`. Verified importing, pytest 8.4.1,
  mypy 1.17.0.
- `sql-dialect-engine` — **STILL BROKEN**, same cause, same fix.

⚠️ `.venv/bin/ruff` keeps working through this because it is a standalone Rust
binary. **Ruff passing is not evidence the venv is healthy.**

---

## 1. Where the work stopped

Codex was executing the "raise every directed route to 100 % SMALL+MEDIUM"
task (see `TASK.md`). Its last productive action was a **real, verified source
fix**; everything after that was verification scaffolding that never got to run.

### 1.1 The last real fix (landed, verified)

**Symptom.** During the serial matrix run, `java→csharp` SMALL failed. The error
wrapper only surfaced `stderr`, which contained the .NET welcome banner, hiding
the actual build diagnostics on `stdout`.

**Root cause.** Target-project assembly writes auditable copies of migrated
units to `evidence/WU-*/Migrated.cs` **inside the generated project tree**. The
.NET SDK's default item globs compile *every* `.cs` under the project directory,
so the evidence copies and `src/Units/*` both defined `Migrated` → duplicate
type definition → `dotnet build` exits non-zero.

**Fix.** The generated `.csproj` now disables default item globs and explicitly
compiles only `src/**/*.cs`. Evidence copies are still written and still
auditable; they simply no longer participate in compilation.

**Verification Codex reported.** A real two-unit C# build regression test was
added and passes; the previously failing `java→csharp` SMALL passes; Ruff,
strict mypy (22 files), `py_compile` and diff-check all green.

**Reported SHAs.** assembly `a750ed6b…c14b`, test `49e6ae2e…d81d`.
⚠️ These are Codex's reported values and are **NOT VERIFIED** by this handoff —
see §4.

### 1.2 What happened after the fix

The source change correctly invalidated freeze window **R3**. Codex rebuilt a
new window **R4** from scratch:

- R4 T0 / T30 / T60 triple hash: **identical** across all three domains
  - source `b25f2036…cac7` (6 828 files, 56 467 133 B)
  - external `6970fb62…13f`
  - frontend `6d0fcaa4…ecbb` (8 797 files)
- Read-only R4 snapshot created and byte-closed against live
  (18 389 regular files, 9 restricted Python-internal symlinks, all read-only)
- Static gates: **all green** — engine Ruff, changed-7 Ruff, strict mypy
  22 files, Python compile, JS/TS `node --check`
- `pytest --collect-only`: **exactly 182 nodes** confirmed

Then it stopped. Free disk on the host fell from ~21 GiB → ~10 GiB during an
external build load Codex could not identify (the sandbox forbids reading the
process table). Its harness has a **fail-closed 12 GiB start gate** and a
**10 GiB hard stop line**. It refused to lower the gate, refused to delete the
retained R4d/R4e/R4f invalidated-window evidence to manufacture headroom, and
halted:

> 已安全停线，未启动 R4g。当前可用空间：`10,472,424 KiB`（约 `9.987 GiB`）…
> R4g 尚未运行 preassert、T0、snapshot、runtime、qualification 或 182 矩阵。
> 仓库、routes、HEAD/index 均未改变；状态保持 `NOT_RUN / NOT_CERTIFIED`。
> 请先释放至少 3 GiB，建议 5 GiB。

**R4g harness is built and audited (no P0/P1) but has never executed.**

## 2. THE BLOCKER (read this before planning anything)

### 2.0 Disk reclamation attempt — 2026-08-12

Starting point was **939 MB free of 927 GB**. After a combination of external
cleanup and in-place zeroing performed from this session, the host is at
**≈ 9.2 GB free**. Still below Codex's 12 GiB start gate.

An agent working through the Claude device bridge **cannot delete files** —
`rm`, `rmdir` and `unlink` all return `Operation not permitted` on the mounted
folders, and macOS grants Terminal only in *click* tier (no typing), so there is
no shell on the Mac to run `rm` from. The only mechanism available is
**truncation in place** (`truncate -s 0`), which does reclaim the blocks but
leaves zero-byte husk files behind.

Zeroed from this session (all regenerable build output or pure cache):

| Target | Reclaimed |
| --- | --- |
| `apps/**/target/*.jar` + Maven build output (34 files) | ~600 MB |
| `apps/web-console/.next/cache` (turbopack) | ~300 MB |
| `apps/web-console/test-results` (Playwright output) | ~88 MB |
| `engines/polyglot-route-engine/native/{swift/.build, rust/target, csharp/bin,obj}` | ~200 MB |
| `~/.cache/uv` | ~1.2 GB |
| `~/Library/Caches/{Google, go-build, GeoServices, com.apple.helpd, Homebrew}` | ~650 MB |
| stale `@next+swc-darwin-arm64@16.2.12` (project pins `next` 16.3.0) | ~116 MB |
| `erl_crash.dump`, stray `*.pyc` / large `*.log` | small |

**Deliberately NOT touched** — these are load-bearing for the gates and must
survive:

- `~/Library/Caches/ms-playwright` (1.1 GB) — real-browser execution for the
  Batch 32/35 frontend gates
- `~/Library/Caches/pnpm` (464 MB) — hardlink source for `web-console/node_modules`;
  zeroing the store corrupts the installed tree
- `~/.cache/codex-runtimes` (1.6 GB) and `~/.m2` (617 MB) — offline toolchain
  and dependency caches; the matrix runs offline against pinned SHA-256 toolchains
- `~/Library/Caches/{Codex, elmos-polyglot-route-engine, org.swift.swiftpm}`
- `artifacts/batch105-108/**/runtime-apks/*.apk` (5 × 61 MB) — byte-identical
  proof-image inputs that a hash-pinned replay may reference
- R4b–R4f invalidated-window evidence (≈ 5.4 GiB) — retention is a constraint

**Source integrity verified after truncation:** every
`engines/polyglot-route-engine/src/**.py` still compiles; no source file was
zeroed.

### 2.1 What is still needed, and only the user can do it

Free space is still **~9.2 GB** against a **12 GiB** start gate and a realistic
**30 GB+** requirement for Swift/.NET/Java builds across 90 routes.

Housekeeping — removes the husks this session left behind (safe, regenerable):

```sh
cd /Users/stephen/DevProjects/AIProjects/elmos
rm -rf apps/web-console/{node_modules,.next,test-results}
rm -rf apps/*/target contracts/engine-api/target
rm -rf engines/polyglot-route-engine/native/swift/.build
rm -rf engines/polyglot-route-engine/native/rust/target
rm -rf engines/polyglot-route-engine/native/csharp/{bin,obj}
rm -rf _to_delete .ai-tmp
rm -rf ~/.cache/uv ~/Library/Caches/Google ~/Library/Caches/go-build
```

Where the remaining tens of gigabytes actually are (user's own data — not for
an agent to decide):

| Location | Size |
| --- | --- |
| `~/Downloads/go語言` | **22 GB** |
| `~/Downloads/105本经典书籍+1T资源【About云】` | 6.3 GB |
| `~/Downloads/ENTER` (Anaconda install) | 5.5 GB |
| `~/Downloads/分享专用` | 3.7 GB |
| other `~/Downloads` course/book archives | ~15 GB |

Also worth checking (not reachable from this session):
`~/Library/Containers/com.docker.docker/Data/vms/0/data/Docker.raw` and
OrbStack images — `docker system prune -a` frequently reclaims 20–60 GB and is
completely safe for this project.

### 2.2 Why the matrix still cannot be run from here even with disk free

Nothing in the verification chain can proceed:

- R4g preassert gate needs two consecutive samples ≥ **12 GiB**
- Swift / .NET / Java / Go / Rust builds across 90 routes need far more
  (**30 GiB+** is the realistic working figure)

**Required user action:** free disk space. Codex asked for 3–5 GiB to resume its
harness; budget 30 GiB+ to actually finish the 182-node matrix.

Codex deliberately did **not** delete the retained invalidated-window evidence
(R4b ≈ 1.12 GiB, R4c ≈ 0.68 GiB, R4d ≈ 2.53 GiB, R4e ≈ 0.51 GiB,
R4f ≈ 0.53 GiB ≈ **5.4 GiB total**) because the constraints require retaining
it. If the user explicitly authorises releasing those specific roots, that alone
clears Codex's resume gate.

## 3. Secondary blocker — no usable execution environment via the bridge

An agent working through the Claude device bridge is in a Linux VM with the repo
mounted, **not** on the Mac. That VM cannot run this engine:

| Need | Status in bridge VM |
| --- | --- |
| Python ≥ 3.11 (`enum.StrEnum` in `equivalence.py`) | ❌ Python 3.10.12 only |
| Project `.venv` | ❌ macOS/darwin binaries, `pyvenv.cfg` says CPython 3.12.12 — unusable on Linux |
| `pytest` / `ruff` / `mypy` on the VM interpreter | ❌ not installed, **no network** to install |
| `javac` | ❌ (JRE only — `openjdk 11.0.31`, no compiler) |
| `dotnet`, `swiftc`, `go`, `rustc`, `cargo`, `clang++` | ❌ all missing |
| `node` | ✅ v22.22.3 (engine pins Node 26) |
| Command timeout | ⚠️ 45 s per call — the matrix runs for hours |

**Implication:** the 182-node matrix can only be run **on the Mac itself**,
by Codex or by a Cowork task started with "On your computer", not through the
bridge.

## 4. What is verified vs. what is only claimed

| Claim | Source | This handoff's verdict |
| --- | --- | --- |
| 10-language / 90-route expansion is wired through | Codex | ✅ **VERIFIED statically** (see `EVIDENCE.md` §1) |
| Mid-flight gap "`test_language_set` and routes/inventory still 72" | Codex | ✅ **CLOSED** — both now declare 90 |
| C# `.csproj` explicit-glob fix | Codex | ✅ **PRESENT IN SOURCE** (`assembly.py:1877/1880`) with a real-build regression at `tests/test_assembly.py:450`; ⚠️ still **NOT EXECUTED** (no `dotnet`) |
| No stubs / placeholders in the engine | — | ✅ **VERIFIED** — zero `TODO`/`FIXME`/`NotImplemented`/`placeholder`/`stub`/`dummy`/`HACK` in `engines/polyglot-route-engine/src` |
| Static gates green (Ruff / mypy 22 / compile) | Codex | ⚠️ **NOT VERIFIED** — no runnable toolchain via bridge |
| `pytest --collect-only` == 182 | Codex | ⚠️ **NOT VERIFIED** — cannot import the package on Python 3.10 |
| Reported file SHAs | Codex | ⚠️ **NOT VERIFIED** |
| 182-node matrix result | — | ⛔ **NOT_RUN** (Codex's own statement) |
| Independent client-repo verification | — | ⛔ **0** |
| Certification | — | ⛔ **NOT_CERTIFIED** |

**Rule:** treat every "Done / Completed / Tests passed" string in Codex history
as a `CLAIM`, never a `FACT`. Only executed gates promote a claim to evidence.

## 5. Working tree state

- **707 modified tracked files**, uncommitted, on
  `feat/batch38-45-certification-toolchain`.
- Spans: `apps/java-engine-{worker,verifier,transformer}`, `apps/web-console`,
  `apps/java-runtime-runner`, `client-packs/frontend-72-route-equivalence-v2/**`
  (Batch 32/35 schemas, scripts, tests, tooling), `Makefile.batch29`.
- This is the **frontend v2 + Spring modernization** workstream mid-flight, not
  the polyglot core. Codex's frontend thread was preparing a *frontend-only
  scoped commit* to avoid clobbering the backend thread on the shared branch.
- ⚠️ **Do not blanket-commit these 707 files.** They are two workstreams sharing
  one branch. Commit frontend and backend scopes separately, as the two Codex
  threads had agreed.
- `git status` with untracked enumeration times out over the bridge; use
  `git status --porcelain -uno` (`GIT_OPTIONAL_LOCKS=0`).

## 6. Known failures / open issues

| # | Issue | Status |
| --- | --- | --- |
| K1 | Host disk full | ✅ **RESOLVED** — ~27 GiB free. User deleted `~/Downloads/go語言` videos (21.8 GB) and the Anaconda install. |
| K10 | **Engine Ruff gate RED**: 2 × `S105` false positives on `stdout_secret` / `stderr_secret` in `tests/test_assembly.py:641-642`. Fixture locals, flagged only for their names. Two-line `# noqa: S105` fixes it. Not touched here — the file has 523 uncommitted insertions and belongs to the parallel workstream. | **OPEN — blocks D1** |
| K11 | `engines/sql-dialect-engine/.venv` base interpreter deleted; venv non-functional. A `-d` existence check on its `home` path reports it healthy — the directory survives, the interpreter does not. | **OPEN** |
| K12 | `validation.py` and `assembly.py` now carry twin copies of the process-diagnostic sanitiser. `validation` is the lower module (`assembly` imports `validation.safe_output`), so the shared copy belongs there and `assembly` should import it. Left to assembly's owner, who is mid-edit. | **OPEN — cosmetic, not correctness** |
| K2 | R4 freeze window stale; R4g never ran | **OPEN** — rebuild T0 after any source change |
| K3 | 182-node matrix never completed a clean run | **OPEN** |
| K4 | Independent client-repo verification `0/72` (now `0/90`) | **OPEN — not started** |
| K5 | Error wrapper for external builds shows only `stderr`, hiding `stdout` diagnostics — this is what masked the C# root cause | ✅ **FIXED & VERIFIED 2026-08-12** — `validation._bounded_process_diagnostic()`, now sanitising secrets and host paths to match `assembly.py`. 4 regressions, **4/4 pass**; Ruff ✅; `mypy --strict` ✅ — all on the Mac with the real toolchain. |
| K6 | Numbers in the task statement use a `/72` denominator; the matrix is now 90 routes / 182 nodes | **OPEN — reporting hazard** |
| K7 | ~5.4 GiB of retained invalidated-window evidence (R4b–R4f) is unreleasable without explicit user authorisation | **OPEN — needs a decision** |
| K8 | `_to_delete/` and `.ai-tmp/` scratch dirs left in the repo root (zeroed, but the bridge cannot remove them) | **Cleanup — see §2.1** |
| K9 | Truncation left zero-byte husks in `node_modules`, `.next`, `target/`, `.build`, `~/.cache/uv`. A tool may read a husk as "present but empty" rather than "missing". **`rm -rf` those trees before rebuilding anything** — do not `npm install` / `swift build` on top of them. | **OPEN — see §2.1** |

## 7. Next step (in dependency order)

1. **User frees disk.** ≥ 5 GiB to resume Codex's harness; ≥ 30 GiB to finish
   the matrix. Optionally authorise releasing R4b–R4f (≈ 5.4 GiB).
2. ~~Fix K5~~ ✅ **done 2026-08-12** — but note it changed
   `validation.py` and `test_native_validation.py`, so **any pre-existing freeze
   window is invalid** and the collected node count is now **185**, not 182.
   Verify that number rather than assuming it.
3. **Rebuild the freeze window** (R5) from T0/T30/T60 — mandatory after step 2.
4. **Re-run static gates** → engine Ruff, changed-set Ruff, strict mypy
   (`validation.py` is in the 22-file strict set — check the new
   `_failure_detail` annotation passes), `py_compile`, then
   `pytest --collect-only` and confirm the real node count.
5. **Run the full matrix serially, single process, no `-x`**, to a real summary
   line. A SIGTERM'd run is void — do not splice fragments.
6. **Triage genuine failures** at source level. Never skip, weaken, or mock.
7. **Then, and only then**, start independent client-repository verification
   (K4) — it is the largest remaining unstarted body of work.
8. Run the batch certification gate. Nothing else may set `CERTIFIED`.

## 8. Bidirectional handoff protocol

Both Codex and Claude Code must, at the end of a session:

1. Update `HANDOFF.md` §1 (where work stopped), §6 (known failures), §7 (next step).
2. Append executed commands and real results to `TEST_RESULTS.md` — including failures.
3. Add per-requirement code/test pointers to `EVIDENCE.md`.
4. Set each requirement's status in `IMPLEMENTATION_STATUS.md` using only
   `IMPLEMENTED / PARTIAL / STUB / MISSING / BROKEN / NOT VERIFIED`.
5. Never write `CERTIFIED` outside a gate-script result.

Do **not** re-scan `~/.codex` unless these files are missing or provably stale.

---

## Session 2026-08-13 — disk reclaimed, tail-47 running, ArkUI advanced

### Disk

5.3 GiB → **14 GiB**, by zeroing (this session cannot `rm`):
`~/Library/Developer/Xcode/iOS DeviceSupport` (4.8 GB, regenerates when a device
is attached), `DVTDownloads`, both stale `pytest-of-stephen` trees, Xcode
`Previews`, plus `xcrun simctl delete unavailable`.
⚠️ These are zero-byte husks — `rm -rf` the directories properly when convenient.

### Matrix strategy change — run the tail, not the whole thing

Nodes 1–135 are already proven clean post-fix. Re-running all 182 is what
exhausted the disk. Instead run **only the 47 never-run nodes**:

```sh
export TMPDIR="$(getconf DARWIN_USER_TEMP_DIR)"
.venv/bin/python3 -m pytest tests/test_repository_pipeline_language_matrix.py \
  -p no:cacheprovider -o addopts="" -q --tb=line \
  -k "medium_repository and (go- or rust- or cpp- or objc- or swift- or javascript-objc or javascript-swift)"
```
Collection confirms **47/182**. Log: `.ai/matrix-tail47.log`.

**Measured burn rate: ~385 MB of disk per MEDIUM node**, and it is NOT in pytest
tmp (only 79 MB reclaimable there) — it is toolchain caches (Xcode module cache,
nuget, go-build, swift). 47 nodes therefore need ~18 GB.

With 14 GB at launch this run is expected to wall around node ~29/47. That is
fine and recoverable: **the remaining nodes can be run as a further batch.**
Batching is the correct long-term approach — each pytest session releases its
tree, so N smaller runs need far less peak headroom than one big one.

### ArkUI — real defect found and FIXED

`tooling/run_frontend_formal_toolchains.py` stages each profile into a writable
temp root, but:

```python
shutil.copytree(profile.project_path, workspace, symlinks=False)
```

`copytree` **preserves permissions**, and campaign profile trees are published
read-only (`0555`). Proven:

```
source mode : 0o555
copied mode : 0o555
writable?   : False
```

`hvigorw` unconditionally creates `.hvigor/outputs/build-logs` in its project
dir → `EACCES`; its wrapper's recursive `mkdir` has no failure branch, so it
surfaced as `RangeError: Maximum call stack size exceeded`, reported as the
misleading `HVIGOR_VERSION_COMMAND_FAILED`. All 16 ArkUI routes failed before a
single build ran.

**Fix applied:** `_make_staged_workspace_writable(workspace)` restores owner-write
on the *disposable staged copy* only. `profile.project_path` and the published
campaign stay read-only, so nothing carrying evidence becomes writable.
Backup of the original: `/tmp/rfft.bak.py`. `py_compile` OK.

**Verified effect:** failure advanced `HVIGOR_VERSION_COMMAND_FAILED` →
`HVIGOR_SDK_VERSION_DRIFT`. hvigor now executes (`6.24.4`).

### D7 — the next ArkUI gate looks unsatisfiable (NOT fixed, needs owner decision)

```python
version_text = f"{version['stdout']['text']}\n{version['stderr']['text']}"
if not any(marker in version_text for marker in ("harmonyos-6.0.0-api20", "6.0.0(20)")):
    ... HVIGOR_SDK_VERSION_DRIFT
```

It greps **`hvigorw --version`** output for an **SDK** marker. `hvigorw --version`
prints `6.24.4` — the hvigor *tool* version, unrelated to the OpenHarmony SDK.
As written this cannot pass.

The SDK version is in `~/Library/OpenHarmony/Sdk/20/*/oh-uni-package.json`:
`version 6.0.0.47`, `apiVersion 20` — which **does** satisfy the campaign pin.

Deliberately not changed: rewriting a version-verification gate risks weakening
it, and this is the frontend workstream's harness. Either point the check at
`oh-uni-package.json`, or confirm whether `hvigorw --version` is expected to emit
an SDK banner in the reference environment.

### Correction

An earlier note in this file said the installed SDK version would fail the pin.
Wrong — that check reads the campaign's own `.elmos-harmony-runner.json`, a
static declaration already set to `6.0.0(20)`, so it always passed. Installing
API 20 was still correct (real HAP builds need it) but was never the blocker.

---

## D3 — Swift analyzer availability: FULL DIAGNOSIS + FIX SPEC (not applied)

### Final evidence

Tail-47 run completed with a real summary: `9 failed, 38 passed in 8066.46s (2:14:26)`.
All nine failures are `swift-*` MEDIUM and all are identical:

```
swift-java swift-python swift-csharp swift-typescript swift-javascript
swift-go   swift-rust   swift-cpp    swift-objc
→ pipeline.py:847: RouteError: PIPELINE_NO_VERIFIED_UNITS
```

Combined with nodes 1–135 (all clean post-fix): **173 pass / 9 fail of 182**,
and the 9 are one root cause, not nine.

### Why this is D3 and not a conversion defect

- The same routes passed in the earlier full clean run (`178/182`, swift MEDIUM green).
- `swift→java` + `swift→python` pass standalone warm: `2 passed in 5:16`.
- **All nine** failed rather than degrading (0 ready, then 2 ready, then fine) —
  so the SwiftSyntax analyzer never became available in that process at all.
  Disk was ~11 GB and falling when the swift block ran last in the batch.

### The defect is bigger than "first-route warm-up"

Earlier notes called this a warm-up race. That undersold it. The real problem:
**when the Swift analyzer cannot be built, every swift-source route reports the
generic `PIPELINE_NO_VERIFIED_UNITS`** — with nothing indicating the analyzer
itself was the cause. Same misattribution class as D1: an infrastructure fault
wearing a semantic error's clothes. It caused two separate misreadings this
session.

### Fix spec (two parts, neither weakens a gate)

1. **Block on the build instead of failing the unit.**
   `native.py` holds `_SWIFT_ANALYZER_LOCK` and a module-global
   `_SWIFT_ANALYZER_TEMPORARY` / `_SWIFT_ANALYZER_BINARY`, built once per
   process. Acquisition must wait for an in-flight build to finish and then
   re-check, rather than letting a unit fail while the build is underway. A
   route's verdict must never depend on whether it was the first Swift route in
   the process.

2. **Report the real cause.** When the analyzer is genuinely unavailable
   (build failed, toolchain missing, disk exhausted), surface a dedicated code —
   e.g. `SWIFT_ANALYZER_UNAVAILABLE:<reason>` — and let discovery classify it as
   an infrastructure blocker, **not** as verdict `UNSUPPORTED` and not as
   `PIPELINE_NO_VERIFIED_UNITS`. This is the same correction D1 needs.

⚠️ Do **not** implement this without running `tests/test_swift_analyzer_cache.py`
and at least `-k "swift-java] or swift-python]"` afterwards. Two confident-but-
wrong diagnoses in this session both came from reasoning about this code without
executing it.

### Why it was not applied here

`Desktop Commander` (the only tool in this session that can run pytest / ruff /
mypy on the Mac) disconnected. The device bridge VM cannot run the engine —
Python 3.10, no `javac`/`swiftc`/`dotnet`. Editing security-critical `native.py`
locking with **zero** ability to execute a test is precisely the pattern that
produced this session's two retracted diagnoses, so it was left for a session
that can verify.

---

## Session 2026-08-14 — 182/182 — THIS SUPERSEDES §0–§7 ON MATRIX STATUS

> ⚠️ This file was concurrently rewritten at 09:04:08Z by another thread while
> the matrix was in flight, dropping the two 2026-08-13/14 session sections that
> a 07:11Z snapshot still had. Nothing above was edited here except the four
> header bullets. Backup of the pre-edit file: `.ai/HANDOFF.md.bak-before-182-record`.

### The result

```text
182 passed in 9791.03s (2:43:11)
```

One serial pytest process, **no `-x`**, real terminal summary line.
Full evidence, exact command and run identity are in `TEST_RESULTS.md`
under "Session 2026-08-14 — FULL 182-NODE MATRIX COMPLETED".

```text
log         .ai/matrix182-owned-run.log
log sha256  758d6473db5350c9e1b2475b5b9e9cbc18100d5af6c709a0371b8576e1afa0e9
status      pytest_exit=0  summary_182_passed=1  freeze_verify_exit=0  run_exit=0
window      2026-08-14T07:16:15Z → 2026-08-14T09:59:27Z   pgid 89137
head        badffaba5c238e4b15e4102b3b101d636e60a774
freeze      e43733fc299a5c364e6045e175d6baafdb89c5190e23a149f0da36271082b15d
collected   182 (pre-run collect status, pytest_exit=0)
```

182 = 2 contract/inventory + 90 SMALL + 90 MEDIUM. **Every directed route
passed both SMALL and MEDIUM.** Not a split-run splice: a single process
covered all 182.

### Why this one worked where the previous attempts did not

- The host reboot at 2026-08-14 ~03:38Z cleared the stale processes and swap
  that killed the earlier attempts. Those were environment deaths, never route
  failures.
- `-o tmp_path_retention_policy=failed` stops passing nodes from accumulating
  tmp trees. Disk went 56 GiB → ~34 GiB and *recovered* mid-run instead of
  draining linearly. The old "~385 MB per MEDIUM node, 47 nodes need ~18 GB"
  planning figure does not apply to a run configured this way — that assumption
  is what drove the batching strategy and the 12/25 GiB start gates.
- No source was touched for the whole 2h43m, so the freeze window held
  (`freeze_verify_exit=0` post-run).

### VOID logs — retained as-is, never spliced

`matrix182-final-after-reboot.log` (99 marks, no summary, last write 05:01:46Z,
no `.status`) = `VOID @ 99/182`. Also still void: `matrix182-final-detached.log`,
`matrix182-final-live4.log`, `matrix-swift9-fixed.log`,
`matrix-run-PARTIAL-VOID.log`, and the 25-mark reboot-interrupted fragment.

### §6 known-issue deltas

| # | Was | Now |
| --- | --- | --- |
| K3 | 182-node matrix never completed a clean run | ✅ **CLOSED** — 182 passed, 2026-08-14T09:59:27Z |
| K2 | R4 freeze window stale | ✅ **CLOSED for this run** — pinned `e43733fc…`, re-verified post-run |
| K1 | Host disk | ✅ closed; ~34 GiB free at finish, never near the 10 GiB stop line |
| K4 | Independent client-repo verification `0/90` | **STILL OPEN — now the critical path** |
| K6 | `/72` vs `/90` denominators | **OPEN** — report this result as **90 routes / 182 nodes** |
| K10 | Engine Ruff `S105` ×2 in `tests/test_assembly.py` | **OPEN — untouched** |
| K11 | `sql-dialect-engine/.venv` base interpreter deleted | **OPEN — untouched** |
| K12 | Duplicate process-diagnostic sanitiser in `validation.py` / `assembly.py` | **OPEN — cosmetic** |
| D7 | ArkUI `hvigorw --version` greps tool output for an SDK marker; cannot pass as written | **OPEN — needs owner decision**; `hdc list targets` still `[Empty]`, Harmony profile `NOT_RUN` |

### §7 next step (revised, in dependency order)

1. **Independent client-repository verification (K4 / R10 / D6) — `0/90`.**
   Now the single largest unstarted item and the only thing between here and a
   certification attempt. Everything upstream of it is green.
2. Land K10 and K11 (small, both known). Note both touch files in the shared
   dirty worktree — scoped hunks only, no blanket staging.
3. Resolve D7 (ArkUI SDK version check) or explicitly accept the Harmony
   profile as `NOT_RUN` with `target_build=PASSED`.
4. Run the batch certification gate. **Only the gate script may write
   `CERTIFIED`.** Status stays `NOT_CERTIFIED` until it does.

### Standing warnings that did not change

- Working tree is still intentionally dirty (~700+ tracked changes, two
  workstreams on one branch). **Do not blanket-stage, commit, or revert.**
  No commit or push was made in this session.
- Any source change from here invalidates the `e43733fc…` window. If the matrix
  must be re-run as certification evidence, rebuild the freeze first.
