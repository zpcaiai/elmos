# Engine test entrypoint

ELMOS has 42 top-level engine directories and 43 test steps: the
`database-data-engine` owns both a Java worker and the nested Python SQL
transpiler. The authoritative mapping is
`scripts/operations/engine-test-registry.json`.

Use the same repository-root entrypoint for every engine:

```bash
make test-engines-check
make test-engines-list
make test-engine ENGINE=python-engine
```

`make test-engines-all` runs the complete registry sequentially. It is intended
for a prepared workstation: the polyglot route suite alone may take hours and
some engines require exact native toolchains.

## Result contract

Logs, temporary directories and Python environments are outside the repository
under `~/.cache/elmos-engine-tests` by default. Override this without placing it
inside the checkout:

```bash
make test-engine ENGINE=functional-assurance-engine \
  ENGINE_TEST_OUTPUT_ROOT=/tmp/elmos-engine-tests
```

Each run writes an owner-only `result.json`. Pytest results distinguish:

- `PASSED` and `PASSED_WITH_SKIPS`;
- `FAILED`;
- `COLLECTION_ERROR`, `PYTEST_INTERNAL_ERROR` and `NO_TESTS_COLLECTED`;
- `ENVIRONMENT`, `TIMEOUT` and `NO_SUMMARY`.

A zero exit code without a real pytest summary is not accepted. Collection
errors are not inferred from `FAILED` lines, and output is parsed as text even
when a tamper test writes NUL bytes.

## Why the registry is explicit

The engines do not share one dependency layout. Some use a locked uv dependency
group, some use an optional extra, some intentionally inject a pinned pytest,
and others use Maven, .NET, npm, pnpm or a delegated repository test root.
Auto-detecting a command from a `pyproject.toml` or `pom.xml` would silently
select the wrong contract for several engines.

For Python tests the runner keeps the repository as the current working
directory, uses `uv --project`, clears inherited pytest `addopts`, and removes
ambient Python/virtual-environment path injection. This prevents the recurring
false failures caused by:

- running a repository-aware test from an engine subdirectory;
- combining a command-line `-q` with a configured `-q` into `-qq`;
- reusing another engine's `UV_PROJECT_ENVIRONMENT`;
- treating pytest exit code 2 as an ordinary assertion failure.

## Evidence boundary

The unified entrypoint standardizes execution and result classification. It
does not turn an unlocked dependency resolution, missing toolchain, skipped
hardware test, local provider double or repository fixture into certification.
Independent and external evidence remains `NOT_RUN` until its own gate runs.
