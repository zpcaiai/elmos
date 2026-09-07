# Production certification suite

Three layers, each answering a different question.

| Layer | File | Question |
|---|---|---|
| Package invariants | `test_package_invariants.py` | Are the README's structural claims still true of the code? |
| Golden corpus | `test_golden_corpus.py` + `../golden/` | Did any Skill's behaviour change on a fixed repository? |
| Honesty invariants | `test_package_invariants.py::TestHonestyInvariants` | Do the three honesty rules still hold end to end? |
| Live toolchain | `test_live_toolchain.py` | Does the *other* layer work — a real compiler and test runner over a real tree? |

## Running

```bash
pytest tests/certification -q                 # the gate
ELMOS_UPDATE_GOLDEN=1 pytest tests/certification -q   # deliberate re-record
```

## Why re-recording is explicit

A corpus that re-baselines whenever the output moves can only *describe* a
regression, never detect one. `ELMOS_UPDATE_GOLDEN=1` is therefore required,
and a changed fixture is reported separately from a changed output: comparing
outputs across two different inputs could pass while the behaviour regressed.

The recorded observation is a digest **plus named projections**, so a failure
reads as `output.transformEvidence.changedPaths: was [4 files], now [1 file]`
rather than as two opaque hashes. A projection that resolves to nothing is
recorded as the string `<missing>` — never as `null` — so a field that
disappears cannot pass as a field that is empty. (That sentinel caught a bug
in this suite's own projection paths on the first run.)

## Coverage

All **23** catalog Skills have at least one case (25 cases total), including
both branches of the verification gate: without an executor (blocking gates
undecided, run does not pass) and with real recorded evidence (the mechanical
gates flip to pass and nothing remains undecided).

## The live layer

Everything else exercises the deterministic core, where "no executor" is the
honest default — which leaves the second half of the two-layer design
untested. `test_live_toolchain.py` closes that: it materializes a snapshot to
a temp directory, runs a real `pytest` and a real `ruff` through
`SubprocessExecutor`, and checks what actually happened.

The load-bearing test is `test_the_transform_output_survives_a_real_test_run`:
the pure core computes a cross-file rename with no shell and no filesystem,
the result is written to disk, and a real pytest is asked whether it works. If
the core's scope analysis were wrong — an importer missed, a call site left
behind — this is where it stops being a theory. Removing the
importer-following action from the recipe turns it red.

It also checks the sandbox's advertised guarantees against the real executor:
a non-allowlisted binary is refused, an escaping working directory is refused
by name (`path_escape` / `invalid_path` / `missing_working_directory`), a host
environment variable does not reach the subprocess, and a timeout is decisive
*as a failure* — never as a pass, because `succeeded` requires a completed
command with exit code 0.

These tests skip when a toolchain is absent, and
`test_the_live_suite_actually_ran_something` fails if *everything* skipped:
otherwise removing pytest from the image would turn the file into a row of
skips and the suite would still report success.

## What the invariants actually check

- **Zero third-party imports**, enforced by parsing every module's AST. The
  zero-dependency claim is a security property — nothing to pin, nothing to
  audit — so it is checked, not asserted in prose.
- **Only `sandbox.py` imports `subprocess`**, so "no executor" stays a state
  the core can *report* rather than one it can route around.
- **No network-capable import anywhere**, including in a test helper.
- **No handler is a stub**: each is checked for size and for not delegating to
  the pending-skill path, so catalog coverage cannot be satisfied by 23
  functions that return `blocked`.
- **Unknown payload fields are rejected** for all 23 Skills: a typo'd key means
  the caller asked for something the handler is not doing.
- **A payload cannot grant itself filesystem reach** — `workspace_root` is
  trusted context, and a payload claiming one is refused.
- **A handler exception becomes a `failed` envelope**, never a traceback and
  never a partial success.
- **With no executor, blocking gates are undecided and the run does not pass.**
- **An undecodable source file lowers coverage** and appears in `unscanned`;
  a declared binary asset does neither. Conflating the two is how "we could not
  read it" becomes "there was nothing there".
- **A declared adapter level never exceeds the native engine level.** A
  descriptor claiming L4 for Python still resolves to L2, because a signature
  is not an implementation.
- **A pinned clock is actually threaded**, asserted in both directions: the
  same instant must give identical bytes *and* a different instant must give
  different bytes. Only the first would pass for a `now` that is parsed and
  then ignored — which is precisely the state the package was in.
- **The clock is trusted context, not a payload field.** A caller who could
  set the time could date an approval into the past.
- **Every case is byte-identical in a fresh process with a different hash
  seed.** The in-process check is not enough: two dispatches in one process
  share one wall clock, so they agree even while the runtime is reading it.

## Two defects this suite found in the package it certifies

Both were live, and neither was visible to the 347 functional tests.

**A determinism claim that was false.** `DispatchContext.now` existed, but
`build_trusted_context` did not accept it and no handler threaded it, so four
Skills — orchestrator, approval gate, rollback, evidence — timestamped their
output from the wall clock. Same input, different bytes, one second later. The
in-process determinism test passed throughout, because both dispatches read the
same clock. The cross-process test is what exposed it.

**Anti-cheat accusing every honest refactor.** A rename rewrites the *inside*
of an assertion; the old line disappears and a new one replaces it in the same
hunk. The line-level rule reported that as an assertion removal, so the proof
case — a clean, idempotent, scope-correct rename — failed its anti-cheat gate.
The file-level counter in the same function said `assertionsRemoved: 0` at the
same time, which is what confirmed it. A check that cries wolf on the normal
case gets switched off, which is strictly worse than not having it. The rule
now reports the **net** loss and locates it precisely, with the file-level
count kept only as a fallback for whole-file rewrites.
