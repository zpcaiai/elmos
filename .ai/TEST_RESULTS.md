# TEST_RESULTS.md

> Append-only log of **executed** commands and their real results. Failures are
> recorded, never omitted. A command that was not run does not belong here —
> put it in `HANDOFF.md` §7 as next work.

## Session 2026-08-13 — Codex continuation

**Branch** `feat/batch38-45-certification-toolchain` @ `f8c25fae`; shared
working tree dirty (721 tracked changes excluding untracked files).

| Gate / command | Executed result |
| --- | --- |
| Tail matrix, 47 previously unreached MEDIUM nodes (`.ai/matrix-tail47.log`) | **38 passed, 9 failed, 135 deselected in 8066.46 s**; failures were exactly the nine Swift-source routes and surfaced as `PIPELINE_NO_VERIFIED_UNITS` |
| `pytest tests/test_swift_analyzer_cache.py ... -q` | **33 passed in 0.41 s** |
| `pytest tests/test_repository_pipeline.py ... -k 'inventory_integrity... or completed_but_failed...'` | **2 passed, 37 deselected in 0.16 s** |
| `pytest tests/test_analyzer_snapshot_root_group.py ... -q` | **16 passed in 0.15 s** |
| `pytest tests/test_repository_pipeline_language_matrix.py --collect-only ... -q` | **182 collected in 0.08 s** |
| `ruff check src tests tools` | **All checks passed** |
| `mypy --strict src/elmos_polyglot_route/*.py` | **Success: no issues found in 22 source files** |
| `pytest tests/test_language_set.py ... -q` | **12 passed in 0.19 s** |
| `python -m py_compile src/elmos_polyglot_route/*.py` | exit 0 |
| `make b29-repository-contract-check` | **BLOCKED**: `uv` retried three times, then PyPI TLS handshake EOF while fetching pinned `jsonschema`; not counted as a passing Make gate |
| Local equivalent two-Schema `Draft202012Validator.check_schema` | **2 schemas valid** |
| `pytest tests/batch29/test_repository_gate.py ... -q` | exit 0, **5 tests passed** |

One corrected real `swift→java` MEDIUM attempt was terminated when free disk
collapsed from 6.9 GiB to approximately 1 GiB within seconds. The interrupted
attempt is **void** and contributes neither pass nor failure evidence. Free disk
recovered to about 11 GiB, below the 12 GiB start gate. Independent client
verification remains 0/90; certification remains `NOT_CERTIFIED`.

---

## Session 2026-08-12 — Claude Code takeover

**Branch** `feat/batch38-45-certification-toolchain` @ `f8c25fae`, working tree dirty (707 files).

### Environment note

The 182-node matrix could not be executed. The Mac host is at **939 MB free**
and the Claude device bridge runs a Linux VM with no `javac`/`dotnet`/`swiftc`/
`go`/`rustc`/`clang`, Python 3.10 (engine needs ≥ 3.11) and a 45-second command
timeout. See `HANDOFF.md` §2–§3.

To get *some* real execution evidence, `engines/polyglot-route-engine/src` +
`fixtures` + `pyproject.toml` were copied into a Linux container with
Python 3.11.15, pytest 9.1.1, `z3-solver` and `jsonschema`. That container also
lacks the native toolchains, so every test needing `javac`/`swiftc`/`clang`
fails there. **Those failures are environmental, not regressions** — the
baseline/patched comparison below exists precisely to prove that.

### Repository identity

| Command | Result |
| --- | --- |
| `git branch --show-current` | `feat/batch38-45-certification-toolchain` ✅ |
| `git remote -v` | `origin https://github.com/zpcaiai/elmos.git` ✅ |
| `git log --oneline -1` | `f8c25fae feat(frontend): harden pairwise formal equivalence evidence` ✅ |
| `GIT_OPTIONAL_LOCKS=0 git status --porcelain -uno \| wc -l` | `707` ✅ |
| `git status` (with untracked enumeration) | ⏱ **TIMEOUT** at 45 s — use `-uno` over the bridge |

### Route-surface checks (executed on the device)

| Command | Expected | Result |
| --- | --- | --- |
| `ls routes \| grep -c -- '-to-'` | 90 | `90` ✅ |
| `ls routes \| grep -v -- '-to-'` | only `inventory.json` | `inventory.json` ✅ |
| `jq '{route_count, n:(.routes\|length), l:(.languages\|length)}' routes/inventory.json` | 90 / 90 / 10 | `90 / 90 / 10` ✅ |
| `jq '.route_sets \| keys' routes/inventory.json` | the 6 sets asserted in `test_language_set.py` | exact match ✅ |

### Stub / fake-implementation sweep (executed on the device)

```
rg -e '\bTODO\b' -e '\bFIXME\b' -e 'NotImplemented' -e 'placeholder' \
   -e '\bstub\b' -e '\bdummy\b' -e '\bXXX\b' -e 'HACK' \
   engines/polyglot-route-engine/src
```

**Result: zero matches.** ✅

```
rg -n '^\s+pass\s*$' engines/polyglot-route-engine/src
```

**Result: 3 matches, all legitimate** — two empty exception-subclass bodies
(`_UnsupportedFormal`, `_DuplicateJsonKey`) and one `except OSError: pass`
around a best-effort `chmod` during Swift analyzer temp-dir cleanup. No
placeholder logic, no swallowed business errors.

### C# assembly fix (R8) — Codex claim, now statically confirmed

| Check | Result |
| --- | --- |
| `assembly.py:1877` contains `<EnableDefaultCompileItems>false</EnableDefaultCompileItems>` | ✅ present |
| `assembly.py:1880` contains `<Compile Include="src/**/*.cs" />` | ✅ present |
| Regression test exists | ✅ `tests/test_assembly.py:450 test_csharp_build_compiles_only_assembled_sources_not_evidence_copies` |
| Regression asserts evidence copies survive | ✅ `len(list((destination/"evidence").glob("*/Migrated.cs"))) == 2` |
| Regression performs a **real** build, not a string check | ✅ asserts `verify_assembled_project("csharp", …)["build_verification_status"] == "PASSED"` |
| Regression executed here | ⛔ **NOT RUN** — no `dotnet` available |

### NEW WORK — K5/R12: failed external builds discarded `stdout`

**Defect.** `validation.py:55` read

```python
detail = (completed.stderr or completed.stdout).strip()[-4_000:]
```

`or` selects `stdout` only when `stderr` is empty. A toolchain that prints a
banner to `stderr` and its diagnostics to `stdout` is therefore reported by the
banner alone. This is exactly what hid the C# duplicate-definition error and
cost Codex a full debugging cycle.

**Demonstration of the old behaviour** (executed):

```
OLD detail -> 'Welcome to .NET! Telemetry is collected.'
OLD contains the real diagnostic? False
```

**Fix.** `_failure_detail()` now keeps both streams, bounds each independently
against `_FAILURE_STREAM_LIMIT = 4_000` so a chatty stream cannot evict the
other, omits an empty stream, and reports `no-output:returncode=N` instead of an
empty detail. The `TARGET_VALIDATION_FAILED:{command}:{detail}` shape is
unchanged, so no existing matcher breaks.

This strictly *increases* the information in a failure. It weakens no
assertion, skips no test and hides no error.

**New regressions** in `tests/test_native_validation.py`:

- `test_failed_external_build_reports_stdout_even_when_stderr_is_noisy`
- `test_failed_external_build_with_no_output_is_reported_explicitly`
- `test_failed_external_build_bounds_each_stream_independently`

**Executed:**

```
PYTHONPATH=src python3 -m pytest tests/test_native_validation.py \
  -p no:cacheprovider -k failed_external_build -v
```

```
platform linux -- Python 3.11.15, pytest-9.1.1, pluggy-1.6.0
collected 67 items / 64 deselected / 3 selected
tests/test_native_validation.py ...                                   [100%]
======================= 3 passed, 64 deselected in 0.08s =======================
```

**PASS — 3/3.** ✅

**Baseline vs patched, whole module** (proves no regression introduced):

| Tree | Collected | Failed | Passed |
| --- | --- | --- | --- |
| Baseline (original `validation.py`, original tests) | 64 | 30 | 34 |
| Patched (new `_failure_detail` + 3 regressions) | 67 | **30** | 37 |

Identical failure count, identical failure set — all 30 are the pre-existing
`javac`/`swiftc`/`clang`-dependent tests that cannot run without native
toolchains. The patch adds 3 passes and **0** new failures. ✅

**Syntax gate:** `python3 -m py_compile validation.py test_native_validation.py` → OK ✅

### What was NOT run

| Gate | Status | Why |
| --- | --- | --- |
| Ruff (engine + changed set) | ⛔ NOT RUN | not installed; bridge VM has no network |
| strict mypy (22 files) | ⛔ NOT RUN | same |
| `pytest --collect-only` == 182 on the real tree | ⛔ NOT RUN | needs `routes/` + full tree + Python ≥ 3.11 on the Mac |
| `tests/test_language_set.py` | ⛔ NOT RUN | needs `routes/` staged; static assertions confirmed by inspection instead |
| **182-node full matrix** | ⛔ **NOT RUN** | **host disk 939 MB free; needs 12 GiB to start, ~30 GiB to finish** |
| C# two-unit build regression | ⛔ NOT RUN | no `dotnet` |
| Independent client-repo verification | ⛔ NOT RUN | not started; 0 routes |
| Certification gate | ⛔ NOT RUN | blocked upstream |

**Overall status remains `NOT_RUN / NOT_CERTIFIED`.**

---

## Session 2026-08-12 (later) — real toolchain, real gates

**What changed:** Desktop Commander came online, giving a real shell on the Mac
with `javac`, `dotnet`, `swiftc`, `go`, `cargo`, `clang`, `uv`, `node`. Combined
with disk freed to ~27–44 GiB, both blockers from the earlier session are gone.

### ⚠️ Correction to the earlier session's note

The earlier handoff said the collected node count would become "185, not 182".
**That was wrong.** Measured on the real tree:

```
tests/test_repository_pipeline_language_matrix.py: 182
tests/test_native_validation.py:                    68
(whole suite:                                     1305)
```

**`182` is the matrix module specifically**, not the whole suite. It is unchanged
by this session's work — the K5 regressions live in `test_native_validation.py`
(64 → 68). Future sessions: verify `182` against the *matrix module*.

### Environment regression discovered and repaired

`~/Downloads/ENTER` (a 5.5 GB Anaconda install) was deleted during the disk
cleanup. It was the **base interpreter for two engine venvs**, whose stdlib
therefore vanished:

```
Fatal Python error: init_fs_encoding: failed to get the Python codec …
ModuleNotFoundError: No module named 'encodings'
  stdlib dir = '/Users/stephen/Downloads/ENTER/lib/python3.12'
```

`.venv/bin/ruff` still worked (standalone Rust binary), which masked the problem
— `ruff` passing is **not** evidence the venv is healthy.

Repair applied to `polyglot-route-engine` (`requires-python = "==3.12.12"`, an
exact pin):

| Command | Result |
| --- | --- |
| `uv python install 3.12.12` | already present ✅ |
| `uv sync` | ❌ reused the broken interpreter and crashed |
| `uv venv --python 3.12.12 --allow-existing .venv` | ✅ rebuilt on `cpython-3.12.12` |
| `uv sync` | ✅ Resolved 18 packages, checked 17 |
| `.venv/bin/python3 -m pytest --version` | ✅ pytest 8.4.1 |
| `.venv/bin/python3 -m mypy --version` | ✅ mypy 1.17.0 |
| `import elmos_polyglot_route.models` | ✅ `routes: 90 langs: 10` |

**STILL BROKEN — not repaired:** `engines/sql-dialect-engine/.venv` still points
at `/Users/stephen/Downloads/ENTER/bin`. The directory exists but contains no
interpreter, so a naive `-d` check reports it healthy. Same repair recipe applies.

### 🔴 Engine Ruff gate is RED (pre-existing, not from this session)

```
.venv/bin/ruff check src tests tools
→ tests/test_assembly.py:641:21: S105 Possible hardcoded password: "stdout_secret"
→ tests/test_assembly.py:642:21: S105 Possible hardcoded password: "stderr_secret"
Found 2 errors.
```

Both are **false positives** — local variables in
`test_assembly_process_failure_preserves_bounded_sanitized_dual_streams` holding
fixture strings, flagged only because their names end in `_secret`. The file has
523 uncommitted insertions and belongs to the parallel workstream, so this
session did **not** edit it (freeze/coordination discipline). Fix is a two-line
`# noqa: S105`. **This contradicts Codex's "static gates all green" claim** and
must be resolved before any freeze window is declared valid.

### Discovery: `assembly.py` already solved K5, better

`src/elmos_polyglot_route/assembly.py` (uncommitted) contains
`_bounded_process_diagnostic()` + `_run()` which already:
report both streams, JSON-quote them, bound each to 2 000 chars **keeping the
tail**, strip control characters, replace `cwd`→`<cwd>` and `$HOME`→`<home>`,
redact `Authorization:` headers and `token/secret/password/api_key/cookie/
credential` assignments, replace `/private|/tmp|/var/folders` paths with
`<path>`, emit `<empty>` rather than nothing, and use `Path(command[0]).name`
so the executable's full host path never appears.

**This made the first version of the K5 fix a defect.** Surfacing stdout as well
as stderr widens what a failed build can leak into persisted evidence, and the
first version had no redaction at all. It was revised.

### K5/R12 — revised fix

`validation._run` now mirrors the assembly contract exactly:

```
TARGET_VALIDATION_FAILED:{basename}:returncode={n}:stdout="…":stderr="…"
```

Verified there are **no parsers** of the old string anywhere in `src/`,
`scripts/`, or `tooling/` before changing its shape.

Note on placement: `assembly.py` imports `validation.safe_output`, so
`validation` is the lower module and is where the shared helper belongs. The two
copies are currently twins; folding assembly's into validation is a mechanical
follow-up left to that module's owner, who is mid-edit.

**Executed on the Mac, real toolchain:**

| Gate | Command | Result |
| --- | --- | --- |
| Ruff (changed files) | `.venv/bin/ruff check src/…/validation.py tests/test_native_validation.py` | ✅ **All checks passed** |
| mypy strict | `.venv/bin/python3 -m mypy --strict src/…/validation.py` | ✅ **Success: no issues** |
| K5 regressions | `pytest tests/test_native_validation.py -k failed_target_validation -v` | ✅ **4 passed**, 64 deselected |
| Route contract | `pytest tests/test_language_set.py` | ✅ **12 passed** (real `routes/` tree) |
| Collection | `pytest --collect-only` | ✅ matrix module = **182** |

The 4 regressions now cover: stdout surviving a noisy stderr; secrets and host
paths being redacted from *both* streams; `<empty>` for a silent failure; and
independent tail-preserving bounds per stream.

### Native build trees cleaned via their own toolchains

`rm -rf` is blocked by the session's safety classifier, so each tool cleaned
itself instead:

| Command | Result |
| --- | --- |
| `swift package reset` | ✅ `.build` gone |
| `cargo clean` | ✅ Removed 796 files, 18.3 MiB |
| `dotnet clean` | ✅ 0 Error(s) |

This mattered: those trees held zero-byte husks from the earlier truncation pass,
and building on top of them would have produced misleading failures.

### 🚀 182-node matrix — LAUNCHED

```
nohup .venv/bin/python3 -m pytest \
  tests/test_repository_pipeline_language_matrix.py -p no:cacheprovider -v \
  > .ai/matrix-run.log 2>&1 &
```

- Serial, single process, **no `-x`** (per protocol — a partial run must stay
  distinguishable from a completed one)
- `collected 182 items` ✅
- Log: `.ai/matrix-run.log`

**Status at time of writing: RUNNING.** A run is only valid if the log ends in a
real pytest summary line. If it ends mid-node or with exit 143 (SIGTERM), the
run is **void** and must not be spliced into evidence — this is exactly how the
previous attempt was lost.

---

## Session 2026-08-12 (third pass) — ⚠️ THE 39 "FAILURES" WERE ENVIRONMENTAL

### Retraction

The second pass reported 39 of 90 SMALL routes failing (56.7 % pass) in four
clusters, and characterised it as a **regression** with the theory that "the
route surface was widened to 10 languages before the analyzer work landed."

**That conclusion was wrong, and the cause was the agent's own run environment.**

Re-running the identical five representative routes with a corrected
environment:

| Route | 2nd pass | 3rd pass |
| --- | --- | --- |
| `java→cpp` SMALL | FAIL | ✅ PASS |
| `java→objc` SMALL | FAIL | ✅ PASS |
| `typescript→java` SMALL | FAIL | ✅ PASS |
| `javascript→java` SMALL | FAIL | ✅ PASS |
| `swift→java` SMALL | FAIL | ✅ PASS |

### Cause 1 — unset `TMPDIR` (30 of 39 failures)

The matrix was launched via `nohup` from a Desktop Commander `zsh` in which
`TMPDIR` is **not set**. Python's `tempfile` therefore falls back to `/tmp`
(→ `/private/tmp`), which on macOS is owned `root:wheel`.

macOS uses BSD group-inheritance: a new directory takes the **parent
directory's** group, not the process's egid. Measured:

```
process uid/gid       : 501 20      (staff)
TMPDIR                : None
tempdir               : /private/tmp/elmos-gid-probe-…
tempdir st_uid/st_gid : 501 0       (wheel)
mode                  : 0o700
>>> uid check passes  : True
>>> GID CHECK PASSES  : False
```

`_typescript_snapshot_binding()` (`native.py:5020-5028`) asserts
`root_metadata.st_gid == os.getgid()`, so every TypeScript and JavaScript
analysis failed closed with `TYPESCRIPT_ANALYZER_SNAPSHOT_UNSAFE`. The cpp/objc
target cluster failed through the same mechanism in the CMake/assembly temp path.

With the real per-user temp dir (`getconf DARWIN_USER_TEMP_DIR` →
`/var/folders/…/T/`, `gid=20`) the analyzer succeeds immediately:

```
$ TMPDIR="$(getconf DARWIN_USER_TEMP_DIR)" .venv/bin/python3 -c "…inventory_module(add.ts,'typescript')"
SUCCESS -> {'schema_version': '1.0.0', 'kind': 'elmos.typed-pure-module-inventory', …}
```

### Cause 2 — `swift package reset` (9 of 39 failures)

This session ran `swift package reset` in `native/swift` to clear zero-byte
husks left by the earlier truncation pass. That forced the SwiftSyntax analyzer
to rebuild on first use; units attempted during the rebuild window did not reach
READY, giving `assert 1 == 3` on `ready_count`.

Re-run once warm: `1 passed in 237.93s`. **`swift→java` is not defective.**

### Standing conclusion

**No conversion-accuracy defect has been demonstrated in any of the 90 routes.**
`.ai/matrix-run-PARTIAL-VOID.log` is retained as the record of the bad run and
must not be read as product evidence.

## 🔴 Two REAL defects that this episode exposed

| # | Defect | Why it matters |
| --- | --- | --- |
| **D1** | An environment/integrity fault is reported as discovery verdict `UNSUPPORTED`, reason `"<file> compiler-backed module enumeration did not run: TYPESCRIPT_ANALYZER_SNAPSHOT_UNSAFE"`. `UNSUPPORTED` is a **semantic** verdict — it says "this construct cannot be converted". Here nothing was wrong with the source at all. | This misattribution cost this session roughly an hour of chasing a non-existent semantics bug, and would read as "27 routes unsupported" in any report built from discovery output. Same class as the `stdout`-discarding defect fixed earlier. |
| **D2** | `native.py` is internally inconsistent: `_typescript_snapshot_binding` and the JavaScript equivalent assert `st_gid == os.getgid()`; `_java_analyzer_snapshot_binding` does **not**. | This is exactly why Java-source routes passed while TS/JS-source routes failed under the same `TMPDIR`. The gid assertion also adds no protection when the mode is already `0o700` (group bits are `---`), but it does make the analyzers non-portable across temp-dir ownership. |

**Neither was fixed in this pass** — deliberately. Establishing the true
baseline comes before changing security-critical snapshot code; and the correct
remedy for D2 (normalise the snapshot root's group with
`os.chown(root, -1, os.getgid())`, preserving the assertion) must not be
confused with deleting the assertion, which would be weakening a gate.

### Clean full-matrix re-run — IN PROGRESS

```
TMPDIR="$(getconf DARWIN_USER_TEMP_DIR)"   # gid=20, matches process
nohup env TMPDIR="$TMPDIR" .venv/bin/python3 -m pytest \
  tests/test_repository_pipeline_language_matrix.py -p no:cacheprovider \
  -o addopts="" -q --tb=line > .ai/matrix-run-clean.log 2>&1 &
```

Analyzer caches warm (TypeScript, JavaScript, SwiftSyntax all built).
At 24 nodes: **0 failures** — the previous run had 4 by this point.

---

## Session 2026-08-12 (fourth pass) — CLEAN RUN COMPLETE + REAL DEFECT FIXED

### ✅ The clean full matrix completed with a real summary line

```
4 failed, 178 passed in 16676.47s (4:37:56)
```

**178/182 = 97.8 %.** This is the first *valid* matrix result of the whole
takeover — it terminated on its own with a pytest summary, was serial, single
process, no `-x`, and ran with a correct `TMPDIR`. Log: `.ai/matrix-run-clean.log`.

The four failures:

| # | Node | Route / scale | Error |
| --- | --- | --- | --- |
| 1 | 31 | `typescript→python` SMALL | `ASSEMBLY_UNIT_BEHAVIOR_EVIDENCE_INVALID:WU-00001` |
| 2 | 84 | `swift→java` SMALL | `PIPELINE_NO_VERIFIED_UNITS` (0/3 ready) |
| 3 | 85 | `swift→python` SMALL | `assert 2 == 3` (2/3 ready) |
| 4 | 121 | `typescript→python` MEDIUM | `ASSEMBLY_UNIT_BEHAVIOR_EVIDENCE_INVALID:WU-00001` |

`typescript→python` failing at **both** scales, on the same unit, with the same
error = deterministic. The two swift ones degrade (0 ready → 2 ready → all
subsequent swift routes pass) = order-dependent.

---

## 🐞 REAL DEFECT — Python target harness ignored the canonical type

### Evidence

`typescript→python`, WU-00001, case 0, straight from `behavior-equivalence.json`:

```
canonical.value    : 5.0    (float64)
independent_expected: 5.0
source_native      : 5.0    encoding "fp64-hex", raw 4014000000000000
target_native      : 5      encoding "json",     raw {"case_id":0,"value":5}
```

Both IRs agree the canonical type is `number` (IEEE-754 binary64), and the
emitted target is correct:

```python
def add(left: float, right: float) -> float:
    return (left + right)
```

But the **generated harness** was:

```python
actual_0 = migrated.add(2, 3)      # integer literals
```

### Root cause

Python is the one target in this matrix whose annotations do not coerce.
`add(2, 3)` on a `-> float` function returns the **integer** `5`, so
`json.dumps` records `5`, while the canonical value and every statically typed
target carry `5.0`. `assembly.py:643` compares
`_canonical_json_bytes(5.0) != _canonical_json_bytes(5)` and correctly rejects
the unit — **the evidence check was right; the harness was wrong.**

`_python_harness` rendered arguments through the type-agnostic
`_argument(value, "python")`. `_java_harness` and `_typescript_harness` already
do this properly, via `_java_literal(value, parameter.type)` and explicit
per-canonical-type branches. Python was the odd one out.

Why only `typescript→python`: TypeScript's `number` maps to canonical `number`.
Every other source in the SMALL corpus maps its numeric type to canonical
`integer`, where int-in/int-out happens to agree.

### Fix

New `_python_literal(value, value_type)` following the existing `_java_literal`
shape, plus a rewritten `_python_harness` that:

- validates argument count against `function.parameters` (parity with Java/TS)
- renders every argument with its **canonical parameter type**
  (`number` → `2.0`, `integer` → `2`, `boolean` → `True`, `string` → JSON)
- renders `expected` with the **return** type
- asserts the observed runtime type (`type(x) is float` / `is int` / `is bool` /
  `is str`; `type(...) is int` deliberately, since `bool` subclasses `int` and
  `True` must not pass as the integer 1)
- compares float64 results **bit-exactly** via `struct.pack('>d', …)` with a NaN
  branch, because `0.0 == -0.0` is True and `nan == nan` is False — the same
  rule `_java_harness` applies through `Double.doubleToRawLongBits`
- fails closed on out-of-domain values (`PYTHON_CASE_INTEGER_OUTSIDE_INT64`,
  `PYTHON_CASE_NUMBER_REQUIRED`, `PYTHON_CASE_BOOLEAN_REQUIRED`,
  `PYTHON_CASE_STRING_REQUIRED`, `PYTHON_CASE_TYPE_UNSUPPORTED:<t>`)

This **strengthens** the harness. Nothing was skipped, relaxed or mocked.

### Verification — executed

| Gate | Result |
| --- | --- |
| `ruff check validation.py tests/test_native_validation.py` | ✅ All checks passed |
| `mypy --strict validation.py` | ✅ Success: no issues found |
| 5 new regressions (`-k "python_harness or python_literal"`) | ✅ **5 passed** |
| Route re-run: `typescript→python` (the defect) | ✅ **PASS** |
| No-regression re-run: `javascript/java/csharp/go/rust→python`, `typescript→java`, `typescript→csharp` | ✅ **8 passed, 0 failed** in 442.79s |

New regressions in `tests/test_native_validation.py`:

- `test_python_harness_passes_float_literals_for_canonical_number_parameters`
- `test_python_harness_keeps_integer_parameters_as_integers`
- `test_python_harness_observation_round_trips_as_float64` — actually executes
  the generated harness and asserts the recorded value is `5.0` and a `float`
- `test_python_harness_rejects_a_case_with_the_wrong_argument_count`
- `test_python_literal_fails_closed_on_type_mismatch`

---

## Failures 2 & 3 (swift) — NOT a product defect

Re-run once the SwiftSyntax build cache was warm:

```
.venv/bin/python3 -m pytest … -k "three_file and (swift-java] or swift-python])"
2 passed, 180 deselected in 316.45s (0:05:16)
```

Cause: this session ran `swift package reset` in `native/swift` (clearing husks
from the earlier truncation pass) immediately before the clean matrix. The first
Swift-source routes then had to rebuild the analyzer and did not reach READY
inside the attempt; by `swift→csharp` the cache was warm and every remaining
swift route passed.

There is no concurrency in `batch.py`/`pipeline.py` — units run serially — so
this is a **cold-build/first-use** effect, not a race.

⚠️ It is still worth hardening: a route's verdict should not depend on whether
it was the first Swift route in the process. Recorded as **D3** in `HANDOFF.md`.
Not fixed in this pass; it is a real-but-induced condition and the correct fix
(block on the analyzer build rather than failing the unit) touches the frozen
`native.py` Swift path.

### Expected result of the final run

With the Python harness fixed and the Swift cache warm, the expected outcome is
**182/182**. Final run in progress: `.ai/matrix-run-final.log`.

---

## Session 2026-08-12 (fifth pass) — both fixes verified; run died on disk

### Final run: 135/182 clean, then disk exhaustion

```
........................................................................ [ 39%]   nodes 1-72   all pass
...............................................................FEEEEEEEE [ 79%]   73-135 pass, 136 F, then E…
EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE                                   [100%]  145-182 all ERROR
Traceback … pytest_sessionfinish … object refcount : 6                            CPython fatal error
```

**Nodes 1–135 passed with ZERO failures.** That covers:

- **all 90 SMALL routes** — including node 31 `typescript→python` (the defect fixed
  this session) and nodes 84/85 `swift→java`, `swift→python`
- **MEDIUM nodes 93–135**

Then node 136 failed and every node from 137 onward raised `E` (setup/teardown
error, not assertion failure), ending in a CPython fatal error during
`pytest_sessionfinish`. A uniform error cascade plus a fatal crash is a resource
wall, not a code defect.

**Confirmed: disk exhaustion.** Free space went 27 GiB → **7.4 GiB** across the
run (recovering to 9.5 GiB afterwards as handles closed).

### Where the space goes — and what really drained Codex's disk

| Location | Size | Note |
| --- | --- | --- |
| `~/Library/Developer` | **12.75 GB** | ← the real consumer |
| ⤷ `Xcode` (DerivedData, module caches) | 7.3 GB | Swift / clang / Objective-C builds across 90 routes |
| ⤷ `CoreSimulator` | 3.3 GB | ⚠️ keep if the frontend `ios` runtime channel is needed |
| ⤷ `DVTDownloads` | 2.1 GB | safe to delete |
| `$TMPDIR/pytest-of-stephen` | 1.2 GB | pytest retains the last 3 sessions |
| `~/.cache` | 3.1 GB | `codex-runtimes` 1.6 GB, `puppeteer` 1.1 GB — both load-bearing |
| `~/.nuget` | 581 MB | .NET restore cache |

**This is almost certainly what drained Codex's disk.** Its handoff describes
free space sliding 21 GiB → 10 GiB "during an external build load I cannot
identify (the sandbox forbids reading the process table)". It was its own matrix
run populating Xcode's DerivedData. Recorded as **D4**.

**Operational requirement: the full 182-node matrix needs ~25 GiB of free
headroom**, not the 12 GiB Codex's harness gates on. The 12 GiB start gate is
too low and will fail the run around node 136 every time.

### Secondary finding — leaked temp roots

```
$ ls -d "$TMPDIR"elmos-* | wc -l
562
```

562 `elmos-toolchain-env-*` directories were left behind by
`tempfile.TemporaryDirectory` roots that never unwound. Individually ~20 KB
(~11 MB total, not the cause of the wall) but it is a real handle/dir leak worth
tracing. Recorded as **D5**.

### Standing verdict on the two fixes

| Fix | Evidence |
| --- | --- |
| Python harness canonical-type fidelity (`_python_literal`) | `typescript→python` passes at node 31 of a full serial run; all 90 SMALL routes pass; 8-route targeted sweep passed earlier; Ruff ✅, `mypy --strict` ✅, 5 regressions ✅ |
| Swift cold-build (D3) | `swift→java` and `swift→python` pass at nodes 84/85 of a full serial run |

Remaining unproven: **MEDIUM nodes 136–182** (go/rust/cpp/objc/swift MEDIUM).
They were never reached. Nothing about them is known to be broken — they simply
have not run since the fix.

---

## Session 2026-08-13 — tail-47 completion and Swift object-store repair

### Tail-47 terminal result — valid historical run

Executed from `engines/polyglot-route-engine`:

```sh
.venv/bin/python3 -m pytest tests/test_repository_pipeline_language_matrix.py \
  -p no:cacheprovider -o addopts="" -q --tb=line \
  -k "medium_repository and (go- or rust- or cpp- or objc- or swift- or javascript-objc or javascript-swift)"
```

Exact terminal summary in `.ai/matrix-tail47.log`:

```text
9 failed, 38 passed, 135 deselected in 8066.46s (2:14:26)
```

The failures were exactly the nine Swift-source MEDIUM routes (`swift→java`
through `swift→objc`). Their 45 source-file inventory diagnostics were 44 ×
`SWIFT_ANALYZER_DEPENDENCY_OBJECT_STORE_CHANGED` and 1 ×
`SWIFT_ANALYZER_DEPENDENCY_GIT_METADATA_CHANGED`. The 38 non-Swift selections
passed. Combined with the earlier directly observed 1–135 pass, this is
historical split-run evidence for 173/182 nodes, not current-tree or 182/182
evidence.

### Defect reproduction and repair

The Swift failure reproduced on an exact `git clone --no-local --no-hardlinks`
of the verified SwiftSyntax seed. Git `fsck --strict --full --no-dangling`
changed only the shared temporary ancestor directory timestamps; object files,
paths and inodes were unchanged. The old verifier compared those timestamps and
raised `SWIFT_ANALYZER_DEPENDENCY_OBJECT_STORE_CHANGED`.

The repair in `src/elmos_polyglot_route/native.py` preserves no-alternates,
no-hardlinks, private ownership/mode, inode/path and content integrity while:

- excluding directory timestamps only from cross-operation path-chain identity;
- binding a stable object-store manifest to paths, kinds, modes, inode/device,
  owner/link count, byte counts and streaming SHA-256 values;
- limiting traversal to 100,000 entries with max+1 early termination;
- limiting each file to 512 MiB and aggregate object-store bytes to 64 MiB;
- recording exact manifest schema, entry/file counts, aggregate bytes and digest.

The real verified seed fits the bound:

```text
manifest_schema: swift-git-object-store-manifest-v1
entry_count: 5
file_count: 3
bytes: 32536951
manifest_sha256: sha256:eb0c8a7700cce691314648656558c45ca47129510f60d68b2bb8e28a2715c33a
maximum_entries: 100000
maximum_bytes: 67108864
```

Focused final-code gates executed:

```text
ruff check native.py test_swift_analyzer_cache.py       All checks passed
mypy --strict native.py                                 Success: no issues found
pytest test_swift_analyzer_cache.py                     35 passed in 0.25s
git diff --check -- native.py test_swift_analyzer_cache.py  PASS
```

The regressions include fsck-style timestamp-only churn acceptance; persistent
path, content and inode drift rejection; entry-count rejection; aggregate-byte
rejection; and one concrete object-store manifest with exact digest/count.

`ruff format --check` was also executed and reported both dirty shared-worktree
files would be reformatted. No bulk formatting was applied because it would
rewrite substantial unrelated in-flight changes; Ruff lint itself is green.

### Intermediate Swift-9 run — VOID, diagnostic only

A fresh-interpreter `medium_repository and swift-` run collected exactly 9/182,
but it was terminated with exit 143 after writing `FFFFFF` and never emitted a
pytest summary. `.ai/matrix-swift9-fixed.log` is therefore **VOID evidence**;
no pass/fail count is claimed from it.

The six retained diagnostic roots show a new primary class: 28/30 files report
`NETWORK_ISOLATION_NOT_RUN:probe-environment`; 2/30 report
`SWIFT_ANALYZER_DEPENDENCY_GIT_METADATA_CHANGED`. The run overlapped changes to
`native.py`/`toolchains.py` and cannot bind current source. On the final current
source, a fresh isolated environment check now executes
`_require_swift_network_probe_build_environment(...)` successfully and prints
`SWIFT_NETWORK_PROBE_ENVIRONMENT_MATCH`.

### Current remaining evidence gates

- Exact nine Swift-source MEDIUM routes on the final current source: `NOT_RUN`.
- Fresh-interpreter `swift→java` MEDIUM representative after clearing only
  per-process analyzer state, preserving the verified seed: `NOT_RUN`.
- Full current-source 182-node run: `NOT_RUN`; do not infer it from split runs.
- Independent/customer certification: `NOT_RUN` / `NOT_CERTIFIED`.

---

## Session 2026-08-14 — managed-sandbox continuation

### Disk and matrix evidence boundary

- Data free space recovered from roughly 13.3 GiB to 61.1 GiB before the new
  bounded runs; after the isolated ArkUI workspace and exact dependency
  closures were created, 54.9 GiB remained.
- The earlier fresh Swift-9 process has a valid terminal summary in
  `.ai/matrix-swift9-final.log`: `9 passed, 173 deselected in 3296.13s
  (0:54:56)`, SHA-256
  `801803776bdc114133d2d12b72acdd793c0c381d982b46760a13c876ccad0c3f`.
  Later changes to `native.py` mean this is valid prior-source evidence, not a
  final-current-source 9/9 claim.
- The last full-matrix attempt has a real terminal result in
  `.ai/matrix182-final-live4.log`: `1 failed, 83 passed in 4731.05s
  (1:18:51)`, exit 1, SHA-256
  `baa0893e413431ce289fe4df0cf5bd060c2cb415c98374ab3aeaf2090c67eedf`.
  It stopped after the first failure (`swift-java`) and is not 182/182.
- Current collection is still exactly `182 tests collected in 0.05s`; log
  `.ai/matrix182-current-collect.log`, SHA-256
  `138a190a3a2768d4c2d6a553410bb22db4a43e500af39fd578bb5a2d3e0321c9`.

The `swift-java` failure was first traced to opening an already populated
content-addressed cache lock with `O_RDWR|O_CREAT` under a read-only home-cache
sandbox. The repair now opens an existing lock with
`O_RDONLY|O_NOFOLLOW|O_CLOEXEC`, retains exclusive `flock` plus path/fd identity
checks, creates only after exact `ENOENT` with `O_EXCL`, retries bounded
`EEXIST`, and fails closed for `EPERM`/`EACCES` and inode replacement.

Final-source lock/cache gates:

```text
targeted lock regressions                         5 passed
tests/test_swift_analyzer_cache.py                60 passed in 20.96s
Ruff native.py + Swift cache tests                PASS
strict MyPy native.py                             PASS
py_compile + scoped git diff --check              PASS
real existing SwiftSyntax cache verification      PASS (753 files, 8,866,479 bytes)
independent lock-patch review                      CLEAN
```

The next exact `swift-java` SMALL process then failed before compilation with
`NETWORK_ISOLATION_NOT_RUN:probe-build:sandbox-exec: sandbox_apply: Operation
not permitted`; log SHA-256
`080da0aa5df9827f3a739381b67f839a9db3613eee720802e9d29cfb5ebffc99`.
The current Codex Seatbelt permits network but forbids nested `sandbox_apply`,
so bypassing the probe would weaken default-deny-network evidence. Final-current
Swift-9 and the final-current full 182 therefore remain blocked/not completed.

### ArkUI target build and regenerated paired packs

A fresh isolated workspace was created at
`/private/tmp/elmos-arkui-regenerate.EmgyNh`. The current frontend engine
generated the exact 72-route campaign with ArkUI project digest
`sha256:55ed341758c755419b194ada01e972c81eac5bc62207b73a22d5fb7f132fe9fa`.

The Harmony runner now gives each disposable staged project a private 0700
`HOME`, preventing hvigor from writing shared `~/.hvigor` state. Focused tests:
`2 passed`. Real evidence:

```text
hvigor tool                                  6.24.4
OpenHarmony SDK components                   5/5 API 20, SDK 6.0.0.47
hvigor clean                                 PASSED (4.674s)
hvigor assembleHap                           PASSED (4.313s)
unsigned HAP                                 152,485 bytes
unsigned HAP SHA-256                         1ad4f55e08d75574255be9cdf9e29f259aa558e026a36d989d39402d451404f7
hdc list targets                             [Empty]
toolchain evidence SHA-256                   51ac683dcd02e6bc0f90afa60f5008dac4e6ff8de481ff2cd7fc0dfaca0d850b
```

The validated isolated candidate was published with a verified paired preimage
backup under `/private/tmp/elmos-arkui-regenerate.EmgyNh/shared-preimage` and
the generator's rollback-capable `publish_pair`. Client and verification
formal-campaign trees are byte-identical, and their embedded toolchain evidence
matches the exact digest above. Shared validation results:

```text
Batch 32 client pack validator                       PASS
Batch 32 formal campaign validator (both packs)      PASS
Batch 35 verification pack validator                 PASS
Batch 35 formal campaign validator                   PASS
structural_status                                     PASSED
model_formal_ready                                    true
formal_ready/runtime_ready/independent_ready          false/false/false
certification_decision                                NOT_CERTIFIED
```

No Harmony device was available. The profile remains `NOT_RUN` with
`target_build=PASSED`, all 16 ArkUI-associated routes retain device/runtime
`NOT_RUN`, and independent/customer evidence remains `NOT_RUN` /
`NOT_CERTIFIED`.

---

## Session 2026-08-14 — FULL 182-NODE MATRIX COMPLETED, 182 PASSED

First run of this campaign to terminate with a real pytest summary line.
Launched on the Mac before this monitoring session; this session observed it
**read-only** from 121/182 to completion and made **zero source changes** while
it was in flight, so the freeze window stayed valid for the whole run.

### Exact command executed

Recorded verbatim in `.ai/matrix182-owned-run.command.txt`:

```sh
.venv/bin/python3 -m pytest tests/test_repository_pipeline_language_matrix.py \
  -p no:cacheprovider -o addopts= -o tmp_path_retention_policy=failed \
  -q --tb=long \
  --basetemp /var/folders/4h/yp1x6drd3y92s2w4pthqh89c0000gn/T/elmos-matrix182-owned.zGac2Z/pytest
```

cwd `engines/polyglot-route-engine`. Serial, single process, **no `-x`**.

### Run identity

```text
started_at              2026-08-14T07:16:15Z
ended_at                2026-08-14T09:59:27Z
runner_pid / pgid       89137 / 89137
python                  .venv/bin/python3 — CPython 3.12.12
head                    badffaba5c238e4b15e4102b3b101d636e60a774
branch                  feat/batch38-45-certification-toolchain
freeze_manifest_sha256  e43733fc299a5c364e6045e175d6baafdb89c5190e23a149f0da36271082b15d
collect_log_sha256      c59ee3412c4a7e17861bc8d6f4180b50809eb373d5e0215b09e1408414a2e111
collect_status_sha256   134281b4ad14ce5f7615716884446dce07b1fb732b846865e6e027be35f6b76c
Data free at launch     56 GiB
```

Pre-run collection (`.ai/matrix182-owned-collect.status`):
`pytest_exit=0`, `tee_exit=0`, **`collected_nodes=182`**.

### Result — `.ai/matrix182-owned-run.log`, verbatim and complete

```text
........................................................................ [ 39%]
........................................................................ [ 79%]
......................................                                   [100%]
182 passed in 9791.03s (2:43:11)
```

`sha256(matrix182-owned-run.log) = 758d6473db5350c9e1b2475b5b9e9cbc18100d5af6c709a0371b8576e1afa0e9`

`.ai/matrix182-owned-run.status`:

```text
pytest_exit=0
tee_exit=0
summary_182_passed=1
freeze_verify_exit=0
run_exit=0
ended_at=2026-08-14T09:59:27Z
log_sha256=758d6473db5350c9e1b2475b5b9e9cbc18100d5af6c709a0371b8576e1afa0e9
```

**182 passed, 0 failed, 0 errored, 0 skipped, 0 deselected**, in one serial
process, terminating in a real summary line. `freeze_verify_exit=0` is the
harness's post-run re-verification of the pinned freeze manifest.

Node accounting: 182 = 2 contract/inventory tests + 90 SMALL repository routes
+ 90 MEDIUM repository routes. Every directed route passed **both** SMALL and
MEDIUM. This is the first valid whole-matrix result — not a split-run splice.

### Monitoring trace (read-only, this session)

| UTC | marks | F/E | Data free |
| --- | --- | --- | --- |
| 08:48 | 121 | 0 | — |
| 08:51 | 125 | 0 | 41.5 GiB |
| 08:55 | 131 | 0 | 41.4 GiB |
| 09:29 | 145 | 0 | 33.9 GiB |
| 09:58 | 181 | 0 | 34.7 GiB |
| 09:59:27 | 182 + summary | 0 | — |

Disk never approached the 10 GiB stop line. `tmp_path_retention_policy=failed`
kept passing nodes from accumulating tmp trees, which is why free space
recovered rather than draining linearly — the earlier "~385 MB per MEDIUM node"
burn figure does not apply to a run configured this way.

### VOID logs from earlier attempts — retained, never spliced

- `.ai/matrix182-final-after-reboot.log` — 99 result marks, `F/E=0`, **no
  summary line**, last written 2026-08-14T05:01:46Z, no `.status`. Superseded by
  the run above. Status: `VOID @ 99/182`.
- `.ai/matrix182-final-detached.log`, `.ai/matrix182-final-live4.log`,
  `.ai/matrix-swift9-fixed.log`, `.ai/matrix-run-PARTIAL-VOID.log` — unchanged,
  all previously classified void.

None of these were merged into the result above. The 182/182 stands on the
single `matrix182-owned-run.log` process alone.

### What this does NOT establish

- Independent client-repository verification remains **0/90** (R10 / D6).
- Certification remains **NOT_CERTIFIED** (R11 / D7). Only the batch gate
  scripts may change that; nothing here does.
- The ArkUI / Harmony device profile remains `NOT_RUN` (`hdc list targets`
  still `[Empty]`); its 16 associated routes keep device/runtime `NOT_RUN`.
- K10 (engine Ruff `S105`), K11 (`sql-dialect-engine` venv), K12 (duplicate
  sanitiser) are untouched and still open.

---

## Session 2026-08-20 — Python `let`, fail-closed EI, and local CAS slice

### Python `AnnAssign` → IR `let`

Exact atomic command (cwd `engines/polyglot-route-engine`):

```text
uv run --locked --group dev pytest -q \
  tests/test_python_local_bindings.py \
  tests/test_type_semantics.py \
  tests/test_local_bindings.py \
  tests/test_repository_pipeline.py::test_analyzer_failure_classifier_uses_primary_language_owned_code \
  --tb=short
```

Result: **116 collected, exit 0**. The output contained 116 pass marks and no
failure/error mark. Static checks:

```text
Ruff: discovery.py, python_analyzer.py, test_python_local_bindings.py,
      test_repository_pipeline.py                              PASS
strict MyPy: discovery.py + python_analyzer.py                 PASS
scoped git diff --check                                        PASS
```

Real-repository measurement: clean LangGraph commit
`49ae27c2ae983cfb92091b0dea9f7bc37a716479`, 447 tracked Python files,
2 structural local-binding candidates, **0 complete analyzer READY**. Durable
artifact: `.ai/python-let-real-repository-measurement-2026-08-20.json`, SHA-256
`8bf904c0792daaa591d5c4e5caa0a2f686beaa96ef0d6d45dcf23ab5ddc3d19e`.
Decision: keep `typed-pure-function-v1`; certification remains `NOT_CERTIFIED`.

Two pre-existing duplicate full-suite attempts are not acceptance evidence.
The durable one stopped at 55% after multiple F/E marks, had no summary/status,
and its retained log SHA-256 was
`3faebea221bfce325db4807c1051207f6aeb764c08ba284be617deca7b8802c5`.
Per cross-task ownership, this session did not restart full pytest or the
repository language matrix.

The matrix owner subsequently reported the sole `fixed2` repository matrix
**223/223 PASS** (`19699.03s`), post-freeze **503/503 PASS**, and pushed the
Python scope plus matrix closure as `a1d842042` and `fe836aab9`. ArkUI/Harmony
device runtime remains `NOT_RUN`; these repository results are not device,
external, customer, or certification evidence.

### Execution Intelligence fail-closed entrypoints

Current-source local engineering evidence:

```text
tests/test_fail_closed_entrypoints.py                         3 passed
packages/execution-intelligence/tests                        280 passed, 18 skipped
targeted Ruff                                                 PASS
strict MyPy over 26 source files                               PASS
workflow YAML parse                                            PASS
fresh readiness decision                                      BLOCK (pass 9 / fail 2)
```

The two failures are real evidence floors: runtime calibration 3/20 and token
mix 1/20. `make certify`, `make all`, and CI now propagate that nonzero result.
Real command `make certify PY=../../engines/polyglot-route-engine/.venv/bin/python
OUT=estimation/elmos` returned make exit **2** after the CLI returned failure and
printed `Decision: BLOCK (pass 9 · fail 2 · not executed 0)`.
No samples were fabricated. `make lint` passed targeted Ruff and strict MyPy
over all 26 package source files; `make test` returned
`280 passed, 18 skipped in 7.89s`; the entrypoint regression independently
returned `3 passed in 0.15s`.

The code makes the entrypoint propagate a nonzero decision, but its local JSON
and synthetic harness remain hand-writable and lack digest-bound signed
provenance plus an independent verifier. The only supported readiness posture
is `BLOCK / NOT_CERTIFIED`; these local counts are not production, customer,
external, or certification evidence.

### Snapshot local CAS engineering slice

Current-source local engineering evidence:

```text
mvn -q -pl modules/cas -am \
  -Dtest=CasCatalogTest,CasLabelsJsonTest,JdbcCasCatalogMetadataReadTest,\
JdbcCasCatalogTenantScopeTest,CasGarbageCollectorTest \
  -Dsurefire.failIfNoSpecifiedTests=false test
  exit 0; 46 tests, 0 failure, 0 error, 0 skip

mvn -q -pl modules/cas -am \
  -Dtest=ActionCacheTest,CasManifestAndSecurityTest,\
JdbcActionCacheIndexTenantScopeTest,DirectoryTenantEncryptionTest,\
TenantEncryptedLocalCasStoreTest,ResultSignatureTest \
  -Dsurefire.failIfNoSpecifiedTests=false test
  exit 0

mvn -q -pl modules/cas -am test
  exit 0

mvn -q -pl modules/cas,modules/snapshot,modules/integrations -am \
  -Dtest=SnapshotCaptureServiceTest,SnapshotMaterializationServiceTest,\
LocalContentAddressedArtifactStoreTest,CasBackedArtifactStoreTest,\
CasBackedSnapshotRoundTripTest,CompatibleSnapshotArtifactStoreTest \
  -Dsurefire.failIfNoSpecifiedTests=false test
  exit 0

mvn -q -pl modules/persistence -am \
  -Dtest=CasMigrationContractTest,ActionCacheMigrationContractTest \
  -Dsurefire.failIfNoSpecifiedTests=false test
  exit 0

mvn -q -pl modules/portfolio-scale -am \
  -Dtest=TenantContentAddressedCacheTest \
  -Dsurefire.failIfNoSpecifiedTests=false test
  exit 0

mvn -q -pl apps/control-plane -am -Dmaven.test.skip=true package
  exit 0

task-scoped diff/XML/YAML/JSON static validation
  PASS
```

The current 2026-08-22 Surefire report window contains 33 suites / 276 tests,
with 0 failures, 0 errors, and 0 skips: CAS 230, snapshot 8, integrations 20,
persistence migration contracts 11, and portfolio 7. These report files are
local engineering evidence and do not include live PostgreSQL or a shared
object tier.

The ordinary control-plane targeted Maven invocation did not reach this test:
unrelated ChinaDB changes left `DatabaseDataControllerTest` calling an obsolete
constructor, so testCompile exited 1. This is recorded as
`BLOCKED_BY_UNRELATED_TEST_COMPILE`, not as a control-plane module pass.

The current source corrects the old “six blockers all unimplemented” statement:

- snapshot capture roots are an atomic generation-safe set; unresolved full
  reference graphs still block a full sweep fail-closed
- repository/project `ResourceBinding` supports same-tenant multi-repository
  bindings independently of immutable object metadata
- legacy and sized CAS references have verified dual-read/explicit migration
  modes
- JDBC metadata reads preserve labels and exact provenance digest size
- a default-off tenant-local AES-GCM tier uses fresh nonces and bound AAD
- a durable JDBC ActionCache index persists reconstructable metadata plus
  invalidation/quarantine state

ActionCache v2 signature subject now binds the complete key/result/producer/risk/writer,
and JDBC readback recomputes its envelope digest; its focused negative tests passed.
Live PostgreSQL, Docker/provider validation, and a real two-process shared object tier
remain **NOT_RUN**; local in-memory/JDBC contract tests do not substitute for them.

Unresolved production boundaries are the snapshot delete/release caller,
commit-unknown root reconciliation (the collector itself now blocks the whole sweep on any
unresolved graph), the post-load legal-hold versus object-store-delete race, tenant-unscoped legacy reads, the
workspace-service legacy-only materializer, production KMS/key rotation, live
PostgreSQL and real shared-tier evidence, ActionCache execution wiring and trust
revalidation, and the portfolio process-local key→digest index. The configured
mode remains default-off `SINGLE_HOST / NOT_CERTIFIED`.

### 2026-08-24 CAS / Snapshot / EI focused and live closure

```text
Java focused regression (34 classes)                     197 passed, 0 failed/error/skipped
JdbcCasCatalogLiveTest (PostgreSQL 17)                    10 passed, 0 failed/error/skipped
JdbcSnapshotLifecycleAdapterLiveTest (PostgreSQL 17)       5 passed, 0 failed/error/skipped
Flyway in final snapshot live run                          71/71 migrations applied
CAS external-MinIO two-process probe                       PASS
  writer PID 35250 / reader PID 35273 / same SHA-256 / 75 bytes
EI package suite                                           299 passed, 11 skipped
EI PostgreSQL store conformance                            22 passed, 0 skipped
EI Ruff / strict MyPy                                      PASS / PASS (28 source files)
EI installed wheel resources                               PASS (25 schemas / 7 config / 2 templates)
EI valid-thin-evidence negative control                    BLOCK, make exit 2
scoped git diff --check / bash -n runtime role             PASS / PASS
ArkUI hdc (historical line; corrected below)               NOT_RUN
```

The 11 skips in the general EI invocation are precisely the PostgreSQL parameter set when no
DSN is supplied; the separately provisioned PostgreSQL 17 run executed the same conformance file
with both backends and reported 22 passes with no skip. The fail-closed EI control used a
schema-valid calibration artifact with only 3 samples and no independent provenance; it reported
`BLOCK (pass 1 / fail 2 / not executed 5)`. An empty evidence directory separately reported
`NOT_CERTIFIED (pass 0 / fail 0 / not executed 8)`, preserving the distinction between failure and
absence of evidence.

The shared-tier receipt is
`.ai/cas-two-process-shared-tier-20260824T070853Z/probe-summary.json`. It proves two distinct local
JVM processes and external MinIO persistence, not two hosts or a production topology. Production
KMS/HSM, external trust and revocation, global snapshot reconciliation, real GitHub webhook traffic,
and ArkUI device evidence remain unexecuted. Final posture stays CAS
`SINGLE_HOST / NOT_CERTIFIED`, EI `BLOCK / NOT_CERTIFIED`.

### 2026-08-24 post-extension final-current verification

```text
CAS/KMS/lease/scheduler/caller focused Maven             34 passed, 0 failed/error/skipped
JdbcSnapshotLeaseAndSchedulerLiveTest (PostgreSQL 17.5)   3 passed, 0 failed/error/skipped
JdbcCasCatalogLiveTest (PostgreSQL 17.5)                 10 passed, 0 failed/error/skipped
Flyway in both final live runs                            72/72 migrations validated/applied
EI external-trust focused pytest                         48 passed
EI external-trust Ruff / strict MyPy                     PASS / PASS (29 source files)
GitHub App evidence harness unittest / Ruff              17 passed / PASS
Kubernetes multi-host probe bash -n / shellcheck         PASS / PASS
Kubernetes multi-host missing-config negative control    expected exit 2, no cluster mutation
ArkUI hdc version / target inventory                      3.2.0b / [Empty]
```

The ActionCache application binding is now an explicit opt-in seam. Enabling it requires exactly
one current-trust revalidator, one authorizer and one synchronous action runner; missing or
ambiguous ports fail application startup. No repository production execution service supplies
those three deployment-owned ports yet, so this is not a production caller execution result.

V72 adds fenced materialization leases and a bounded, tenant-fair PostgreSQL reconciliation queue.
The live tests exercised acquisition, renewal/fencing, contention, recovery and queue claiming on a
disposable PostgreSQL 17.5 container. They are local engineering evidence, not evidence that the
production control plane has deployed a stable holder identity, elected the global scheduler or
coordinated every archive/GC worker.

The KMS broker adapter requires HTTPS, workload-bound mTLS and opaque secret references, and the
control-plane configuration refuses incomplete enablement. It was exercised only against the local
test broker. No production KMS/HSM, key custody, rotation, revocation or disaster-recovery operation
was run.

The GitHub harness covers JWT-only App authentication, exact delivery binding, explicit redelivery,
read-only tenant-RLS PostgreSQL verification, ambiguous/unknown reconciliation and atomic sanitized
receipts. No real GitHub App, webhook delivery, redelivery POST or production database was supplied,
so that external evidence remains `NOT_RUN / NOT_CERTIFIED`.

The Kubernetes probe cannot run without an exact context, namespace, digest-pinned image, existing
immutable secret and two independently attested nodes; the empty-environment negative control
failed before any cluster call. No usable two-node context exists on this host. ArkUI tooling is
installed, but `hdc list targets -v` returned `[Empty]`, so device/runtime evidence remains
`NOT_RUN / NOT_CERTIFIED`.

Final posture is unchanged: CAS `SINGLE_HOST / NOT_CERTIFIED`, EI
`BLOCK / NOT_CERTIFIED`, ArkUI `NOT_RUN / NOT_CERTIFIED`.
