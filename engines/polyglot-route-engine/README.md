# ELMOS Polyglot Route Engine

This engine implements a compiler-backed, fail-closed vertical slice across Java,
Python, C#, and TypeScript. Every directed pair is independent.

The `typed-pure-function-v1` profile supports explicit primitive parameter and
return types, literals, identifiers, selected binary operators, `if`, and
`return`. Java uses the JDK Compiler Tree API, Python uses CPython AST, C# uses
Roslyn, and TypeScript uses the TypeScript Compiler API. Every emitted target is
compiled by its native toolchain and executed against the same behavior cases.

Unsupported statements, expressions, types, async behavior, side effects,
frameworks, databases, concurrency, reflection, and I/O fail closed. This exact
profile is `LIMITED`: all 12 directions pass native analysis, target compilation,
separate holdout, and representative behavior replay. Independent and external
certification remain `NOT_RUN`; repository orchestration never broadens this
semantic boundary.

Execution is exact-toolchain bound: Java 21.0.11, Python 3.12.12, .NET SDK
10.0.301 / Roslyn 5.6.0, and TypeScript 5.9.2 on Node 26.0.0. A missing or
different source or target toolchain blocks the route instead of accepting
language-level compatibility flags as equivalent evidence.

```bash
uv sync --locked
uv run pytest
uv run ruff check src tests
uv run mypy src
```

## Repository inventory and decomposition

Repository scope starts with a bounded, read-only inventory. It does not execute
customer code and does not infer repository-wide migration success from the
pure-function profile:

```bash
uv run elmos-polyglot-route inventory \
  --repository /approved/read-only/workspace \
  --repository-ref local:customer-repository \
  --source-language java \
  --target-language python \
  --output repository-route-plan.json
```

The command ignores known build/vendor directories, never follows symbolic
links, verifies that every accepted file stays stable while read, and enforces
file-count, per-file, and aggregate byte limits. Its content-addressed output
contains one `DISCOVERY_REQUIRED` work unit per source file. Every work unit
keeps execution at `NOT_RUN` until a function name and independent behavior-case
corpus are supplied; framework, database, I/O, concurrency, exceptions, async
and object-graph semantics remain explicit blockers.

`discover` classifies every work unit with a precise verdict (`READY`,
`UNSUPPORTED`, `NO_CANDIDATE_DECLARATION`, `UNREADABLE`) using the same
compiler-backed analyzer the migration itself uses -- a candidate name is
proposed cheaply but never accepted without that analyzer's confirmation.
`batch` then attempts only `READY` units that also have a matching
`{unit_id}.json` behavior-case file under `--cases-directory`, resumably via a
`batch-checkpoint.jsonl`, and never rounds a partial run up to `COMPLETE`.

## Whole-project assembly

A batch run proves each work unit in isolation. Every `PASSED` unit reuses the
same fixed emitted file name (`Migrated.java` / `Migrated.cs` / `migrated.py` /
`migrated.ts`, and for Java/C# the same class name too), so combining two units
verbatim would collide on the first duplicate -- a batch report by itself is
not a project anyone can build. `assemble` closes that gap for one already-run
batch report:

```bash
uv run elmos-polyglot-route assemble \
  --batch-report batch/batch-report.json \
  --batch-output batch \
  --destination assembled-library \
  --verify
```

For every `PASSED` unit it re-verifies the unit's recorded sha256 against the
batch output on disk (defense in depth against a tampered or stale batch
directory), then places the unit's already-emitted source under a per-unit
namespace -- a Java/C# package/namespace per unit, a Python/TypeScript module
per unit -- so nothing collides, and writes a real per-language build manifest
(`pom.xml` / a root `.csproj` / `pyproject.toml` / `package.json` +
`tsconfig.json`). `FAILED` and `SKIPPED_*` units are recorded, with their
reason, in `assembly-manifest.json` under `excluded_units`; they are never
silently dropped and never included in the assembled project.

`--verify` (or a separate `verify_assembled_project` call) runs a real
whole-project compile/build check with the same exact-toolchain contract the
per-unit harness already enforces (`javac` across all sources, `python -m
compileall`, `dotnet build`, or `tsc`), and only on success writes local-run
and cloud-publishing guidance (`docs/LOCAL_RUN.md`, `docs/CLOUD_PUBLISHING.md`,
`deploy/deployment-options.json`) into the assembled project. The assembled
artifact is a library of certified pure functions, not a running service, so
that guidance documents a real build + package-publish workflow (recommending
AWS CodeArtifact, since it is the one platform that natively covers all four
target package formats) rather than a Cloud Run-style container deployment.

Units are never merged into one shared namespace even when the build passes:
two different source files can define a same-named function with different
behavior, and assembly does not attempt to resolve that at the semantic level.
Callers must import each unit by its own id/module, not assume a combined API.
Independent verification and external certification remain `NOT_RUN` /
`NOT_CERTIFIED` regardless of local build success.

## Resumable repository pipeline

`repository-pipeline` composes inventory, compiler-backed discovery, resumable
per-unit execution, collision-safe assembly, and a real whole-project build into
one operator command:

```bash
uv run elmos-polyglot-route repository-pipeline \
  --repository /approved/read-only/workspace \
  --repository-ref local:customer-repository \
  --source-language java \
  --target-language python \
  --cases-directory /approved/independent-cases \
  --output /durable/tenant-job/pipeline
```

The output directory is a durable checkpoint boundary. Re-running the command
recomputes inventory and discovery from the read-only source, detects source
drift, resumes the per-unit batch checkpoint, rebuilds assembly from verified
bytes, and emits `repository-migration-artifact.zip` with an exact file/digest
manifest. `COMPLETE` requires every work unit to pass; missing behavior cases,
unsupported units or failures produce `PARTIAL` and remain visible in the
pipeline report. Local execution never changes independent or external evidence
from `NOT_RUN`.

## Single-declaration bridging (`emit` / `check`)

`migrate` is atomic (analyze -> emit -> validate against behavior cases), which
fits this engine's own repository pipeline but not every caller. `emit` and
`check` decompose that into two real, narrower primitives for callers that
handle emission and validation as separate steps with no behavior-case corpus
of their own -- specifically `modules/lowering`'s `TargetEmitter`/
`StaticValidator`, which delegate here via subprocess rather than reinventing
a second translation backend (see `PolyglotRouteEngineBridge.java` and
ADR-0023's addendum).

```bash
uv run elmos-polyglot-route emit \
  --source Calc.java --source-language java --target-language csharp \
  --function calculate --output emitted/

uv run elmos-polyglot-route check \
  --target-language csharp --file emitted/Migrated.cs --output checked/
```

`emit` runs the same real analyzer and emitter as `migrate`, with no
compilation and no execution; it needs only the *source* language's exact
toolchain. `check` compiles/type-checks one already-emitted file alone -- no
harness, no execution -- using the *target* language's exact toolchain; it is
deliberately narrower than `validate`, which requires behavior cases and
actually runs the code. Both fail closed exactly like the rest of this
engine: an unsupported construct, a same-language route, or a
missing/mismatched toolchain raises `RouteError` rather than a degraded
success.
