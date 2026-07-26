# ELMOS Polyglot Route Engine

This engine implements a compiler-backed, fail-closed vertical slice across Java,
Python, C#, and TypeScript. Every directed pair is independent.

The `typed-pure-function-v1` profile supports explicit primitive parameter and
return types, literals, identifiers, selected binary operators, `if`, and
`return`. Java uses the JDK Compiler Tree API, Python uses CPython AST, C# uses
Roslyn, and TypeScript uses the TypeScript Compiler API. Every emitted target is
compiled by its native toolchain and executed against the same behavior cases.

Unsupported statements, expressions, types, async behavior, side effects,
frameworks, databases, concurrency, reflection, and I/O fail closed. This local
profile is `EXPERIMENTAL`; independent certification remains `NOT_RUN`.

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
