# Findings — 2026-08-18 (Claude session)

> Additive note. Written to its own file, not into `HANDOFF.md`, because a
> second agent was editing the polyglot engine while this was written.
> Nothing in this file is a certification claim.

## 0. Concurrency warning — READ FIRST

Between 11:16 and 12:00 on 2026-08-18 a **second agent was actively editing
`engines/polyglot-route-engine` in this working tree.** Observed directly:

- `.git/index.lock` — 0 bytes, created 11:16, no `git` process holding it
  (abandoned). Moved aside to `/tmp/elmos-stale-index.lock.<epoch>`, not deleted.
- Modified-file count went **6 → 20** between 11:42 and 12:00.
- `assembly.py` rewritten at 11:36:31 and again at 11:59:44.
- New surface appearing: `php` in `models.py`, `tools/generate_php_route_packs.py`,
  `tools/pin_php_toolchain.py`, `tests/test_php_target.py`.

**Conclusion: an 11th language (PHP) is being added right now.** This session
therefore stopped writing to the polyglot engine. No commit was made to it — a
`git add` attempted at ~11:40 failed on the stale lock and staged nothing
(`git diff --cached` empty, verified).

Any test result for this engine taken during that window describes a moving
tree and should not be treated as a gate result.

## 1. Confirmed CLOSED since the last handoff

| ID | Status | Evidence (executed on the Mac, this session) |
| --- | --- | --- |
| K3 / R9 | **CLOSED** | `.ai/matrix182-owned-run.log`: `182 passed in 9791.03s (2:43:11)`; `.status` records `pytest_exit=0`, `freeze_verify_exit=0`, `summary_182_passed=1` |
| K10 | **CLOSED** | `ruff check .` on the engine → `All checks passed!`. Not gamed: `select = ["E","F","I","B","UP","S"]`, `ignore = ["S101","S603"]` — **S105 is still enforced**; the `stdout_secret`/`stderr_secret` fixtures no longer exist |
| K11 | **CLOSED** | `sql-dialect-engine/.venv` rebuilt (`uv venv --python 3.12` + `uv sync --extra dev`). Proven: **167 passed in 0.22s**; `ruff check .` clean |
| K12 | **CLOSED** | `assembly.py:61` now does `from .validation import _bounded_process_diagnostic, safe_output`; exactly one definition remains, in `validation.py` |

## 2. FIXED — 8 pre-existing failures in `tests/test_native_validation.py`

**Not a regression.** Verified by extracting `HEAD` (`530ca2640`) with
`git archive` into a sibling directory and running the same selection against
it: **identical 8 failures, identical error.** (A first attempt from `/tmp`
produced `SWIFT_ANALYZER_PACKAGE_UNSAFE` instead — a path-safety artifact of
`/tmp`, not a comparable baseline. Re-run from
`/Users/stephen/DevProjects/AIProjects/elmos-head-check` to get a clean compare.)

Failing nodes:

- `test_native_source_and_target_execute_lossless_string_and_exact_fp64_observations[cpp|objc|swift|java]`
- `test_swift_canonical_unicode_equality_diverges_from_java_code_unit_equality`
- `test_native_emitted_target_relifts_exact_helper_and_rejects_body_tamper[cpp|objc|swift]`

### Root cause — stale tests, not an engine defect

The engine renames target symbols on purpose. `single_unit.py` documents it:

> a function name is rejected for cpp and objc because their global symbol
> namespace is open, and for java, csharp and swift because of the runtime
> function namespace — so the emitted symbol is frequently not the one that
> was analyzed.

That is **exactly** the failing language set. `emit()` builds an
`IdentifierPlan` and emits `elmos_fn_<digest>` (`identifier_hygiene.py:789`),
but these three tests then hand `validate()` the **source** `Function`, whose
`.name` is still `same` / `echo`. Every harness interpolates `function.name`
verbatim (`validation.py:650, 729, 784, …`), so the emitted file defines
`elmos_fn_caa1c06d8c7689d0` while the harness calls `same`.

Observed compiler output (surfaced only because the R12 `stdout` fix landed —
before it, this was hidden behind a useless banner):

```
TARGET_VALIDATION_FAILED:swiftc:returncode=1:stdout="<empty>":
stderr="main.swift:15:15: error: cannot find 'same' in scope"
```

### FIXED — applied and verified 2026-08-18 12:35

Applied exactly as specified below. Result:

- the 8 targeted nodes: **8 passed, exit 0** (280.77s of real toolchain work —
  they are real passes, not skips; a skip would print `s`)
- whole module re-run: **73 passed, exit 0**, zero failures, no regressions
- `ruff check tests/test_native_validation.py` → clean

The `relifts_exact_helper` test needed a second change beyond the spec: it
never called `validate()` at all, it called
`analyze(target, language, "ratio", emitted_target=True)` on the *emitted*
file. It now asks for `target_function.name` and compares the relifted IR
against the **target view** rather than the source IR — the two differ by
exactly the planned rename and nothing else, so this is a stricter statement
of the same property, not a weaker one.

### Original fix spec

Mirror the production pattern already in `single_unit.emit_only` and
`engine.py:3359`. Add one helper to the test module:

```python
def _emitted_target(ir: SemanticIR, language: Language) -> tuple[EmittedFile, Function]:
    """Emit `ir` and return the file with the function the file actually defines."""
    plan = plan_identifiers(ir, language)
    return emit(ir, language, identifier_plan=plan), target_ir_view(ir, plan).functions[0]
```

and at each of the failing `validate(emit(...), ..., <source_function>, ...)`
call sites use the pair it returns. `validate_source(...)` calls must keep the
**source** function — the source file really does define `echo`.

**This does not lower the acceptance bar.** The tests still emit real code,
invoke the real `swiftc`/`javac`/`clang` toolchain, execute the binary, and
assert the same fp64-hex / hex-utf8 observations. The only change is calling
the symbol the engine actually emits instead of one it never emits.

**Do not apply this until the PHP refactor lands and the tree is quiet.**
Re-verify against a clean baseline afterwards: the 8 must go green *and* the
per-language toolchain-profile assertions must still execute.

## 3. FIXED — `sql-dialect-engine` had no working lint, type, or CI gate

The gap was wider than first reported. This package had **no `[tool.mypy]`,
no `[tool.ruff]`, and no CI job** — so `ruff` was running on its defaults
(E4/E7/E9/F only) and `mypy` was never run at all. Worse, its dev tools sat in
`[project.optional-dependencies]` rather than `[dependency-groups]`, so the
`uv sync --locked` invocation every other engine's CI uses **would not have
installed pytest**. The gate was not weak; it was absent.

Fixed:

1. **6 mypy errors.** `sqlglot.__version__` read once into a typed local with a
   narrow `# type: ignore[attr-defined]` (sqlglot declares no `__all__`; the pin
   is still exact and still fails closed). `psycopg2` import marked
   `# type: ignore[import-untyped]`, matching the convention already used for
   `pymysql` in the same file. `ident.this` narrowed with `assert isinstance`,
   matching the narrowing convention already in `parser.py`. `_SubParsersAction`
   parameterised as `_SubParsersAction[argparse.ArgumentParser]`.
2. **21 ruff findings** once the house rule set (`E,F,I,B,UP,S`) was applied —
   import sorting, `UP038` isinstance unions, `UP035`/`UP017`, and 10 `E501`
   long lines wrapped by hand.
3. **Config added** mirroring the other engines: `[tool.ruff]` +
   `[tool.ruff.lint]` (`select = ["E","F","I","B","UP","S"]`,
   `ignore = ["S101","S603"]`) and `[tool.mypy]` (`strict = true`).
4. **Dev tooling moved** to `[dependency-groups]` and aligned to the house
   versions (mypy 1.17.0, pytest 8.4.1, ruff 0.12.5) so "ruff clean" means the
   same thing across the repository. `uv.lock` regenerated.
5. **CI job added** (`sql-dialect-engine`), same shape as the others:
   `uv sync --locked` / `uv run pytest` / `uv run ruff check src tests` /
   `uv run mypy src`.

Verified by running that exact CI sequence locally: **167 passed**, ruff
`All checks passed!`, mypy `Success: no issues found in 10 source files`,
exit 0. The 167 tests passed before and after, so none of the refactoring
changed behaviour.

## 4. Verified green this session (before the tree started moving)

- `project-synthesis-engine`: **62/62 pass**, exit 0 — covers the in-flight
  `DURABILITY_PROFILES` change in `production_runtime.py`
- `polyglot-route-engine`: `ruff check .` clean; `mypy --strict` clean on
  `assembly.py`, `validation.py`, `discovery.py`, `project_graph.py`
- `sql-dialect-engine`: 167/167 pass; ruff clean

## 5. Still open

| ID | Item |
| --- | --- |
| K4 | Independent client-repository verification — **0/90, still the critical path** |
| R11 | Formal certification — `NOT_CERTIFIED`, blocked on K4 |
| ~~D7~~ | **CLOSED** — see §6 |
| K6 | Report denominators as **90 routes / 182 nodes**, never `/72` |
| K7 | ~5.4 GiB retained invalidated-window evidence (R4b–R4f) — needs a user decision |

## 6. D7 — ArkUI SDK version gate: already fixed in the live runner

The unsatisfiable grep (`hvigorw --version` searched for `harmonyos-6.0.0-api20`
/ `6.0.0(20)`, when that command prints the hvigor *tool* version `6.24.4`)
survives in **one** copy only. There are three distinct versions of
`run_frontend_formal_toolchains.py` in the tree:

| Copy | md5 | State |
| --- | --- | --- |
| `tooling/`, `verification-packs/…-v2/`, `client-packs/…-v2/` | `4456284…` | **correct** |
| `verification-packs/…-v1/`, `client-packs/…-v1/` | `d079542…` | stale grep |

The live copy already replaced the grep with `discover_openharmony_sdk_metadata()`,
which reads the SDK manager's component-level `oh-uni-package.json` files —
the authoritative local identity — and requires the complete five-component
API-20 set, binding each metadata file by digest and rejecting symlinks,
partial installs, extra fields and version drift.

**Executed against the installed SDK this session:**

```
resolved_root = /Users/stephen/Library/OpenHarmony/Sdk/20
  ets          valid=PASSED  api=20 version=6.0.0.47
  js           valid=PASSED  api=20 version=6.0.0.47
  native       valid=PASSED  api=20 version=6.0.0.47
  previewer    valid=PASSED  api=20 version=6.0.0.47
  toolchains   valid=PASSED  api=20 version=6.0.0.47
```

So D7 is satisfiable and satisfied on this host.

### The v1 copy is deliberately NOT patched

`verification-packs/…-v1/…/run_frontend_formal_toolchains.py` is
**digest-bound**. Its sha256 `1c5ad012a263f4b6c88778d72398143337194843620716952b623db7f96a4a72`
is recorded in four evidence manifests:

- `verification-packs/frontend-72-route-formal-equivalence-v1/formal-campaign/frontend-formal-route-campaign.json`
- `verification-packs/frontend-72-route-formal-equivalence-v1/formal-campaign/toolchain/frontend-formal-toolchain-evidence.json`
- the two matching files under `client-packs/frontend-72-route-equivalence-v1/`

Editing it would silently break the v1 campaign's provenance chain to fix a
gate that the superseding v2 campaign already implements correctly. Sealed
evidence should stay sealed; leaving the stale grep in a retired pack is the
lesser error. **Do not "tidy" this file.**
