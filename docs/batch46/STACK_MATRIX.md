# Batch 46 — Stack and entry matrix

## Detection

| Language | Detected from | Frameworks | Default port | Readiness |
| --- | --- | --- | --- | --- |
| Python | `requirements*.txt`, `pyproject.toml`, `setup.py`, `Pipfile` | FastAPI, Flask, Django, Starlette | 8000 / 5000 / 8000 | `/health`, `/health/` |
| TypeScript / JavaScript | `package.json` (+ `tsconfig.json`) | NestJS, Express, Fastify, Next, React, Vue, Angular, Svelte | 3000 / 5173 / 4200 | `/health`, `/` |
| Java | `pom.xml`, `build.gradle[.kts]` | Spring Boot, Quarkus, Micronaut, Jakarta | 8080 | `/actuator/health`, `/q/health/ready`, `/health` |
| C# | `*.csproj`, `*.fsproj` | ASP.NET Core | 5000 | `/health` |
| Dart | Flutter `pubspec.yaml`, `lib/main.dart`, `web/index.html` | Flutter web-server | 5173 | `/` |
| JavaScript | WeChat `project.config.json`, `app.json`, generated bounded runner | WeChat Mini Program | allocated | `/health`, `/counter` |
| ArkTS | ArkUI build/module profiles, generated bounded runner | HarmonyOS ArkUI | allocated | `/health`, `/counter` |

The listed ports are discovery defaults, not shared runtime allocations. Each
run receives an ephemeral loopback port through `SMOKE_PORT`, `PORT`, and the
applicable framework variables (`SERVER_PORT`, `QUARKUS_HTTP_PORT`,
`MICRONAUT_SERVER_PORT`, `ASPNETCORE_URLS`, or `FLASK_RUN_PORT`). This prevents
parallel projects from racing for ports such as 5000/8080. A legacy application
that cannot consume a runtime port may explicitly set
`ELMOS_SMOKE_PREFER_DEFAULT_PORT=true`; the normal fail-closed readiness gate
still applies.

Datastores are detected from connection markers in env, YAML, JSON, properties
and XML files, plus any `*.sql` schema and migration directories: PostgreSQL,
MySQL/MariaDB, SQL Server, Oracle, SQLite, MongoDB, Redis, Kafka, RabbitMQ.

A repository containing more than one stack is marked `polyglot`. The first
detected stack becomes `primary` and owns the entry; the others are declared as
`secondary` and share the lease.

## Entries

| Entry | Command | Available when | Trade-off |
| --- | --- | --- | --- |
| `script` | `./run-smoke.sh` | the primary stack has a start command | closest to how the recipient will actually run it; needs the toolchain installed |
| `compose` | `./run-smoke.sh --entry compose` | a Dockerfile or a containerisable datastore exists | closest to the real topology; needs a running Docker daemon |
| `make` | `make -f Makefile.smoke smoke` | same as `script` | CI-friendly wrapper, identical semantics |
| `zero-dep` | `./run-smoke.sh --entry zero-dep` | every datastore has an approved embedded substitute | fastest path to green; **not the declared engine**, so results are downgraded to `limited` |

Windows recipients get `run-smoke.ps1` with the same arguments.

## Embedded substitutes for the zero-dependency entry

| Declared engine | Python | Node | Java | .NET |
| --- | --- | --- | --- | --- |
| PostgreSQL | SQLite | SQLite | H2 | SQLite |
| MySQL | SQLite | SQLite | H2 | SQLite |
| SQL Server | — | — | H2 | SQLite |
| SQLite | SQLite | SQLite | SQLite | SQLite |
| Oracle | — | — | — | — |
| MongoDB / Redis / Kafka / RabbitMQ | — | — | — | — |

An empty cell means the `zero-dep` entry is emitted as `unavailable` with that
reason. Substituting an engine a project does not declare support for changes
semantics — dialect, transaction behaviour, type coercion — and a smoke run that
hides that change is worse than no smoke run.

## Per-family notes

**B29 language routes.** Both directions of a route are separate projects and
get separate smoke packs. A route's smoke pack proves the target artifact starts
and answers; it says nothing about equivalence with the source.

**B30 framework packs.** The readiness path is framework-specific and comes from
the framework's own contract, not a guess. Dependency install is part of the run
(`--no-install` skips it when the recipient has already installed).

**B31 database packs.** Tables are seeded in foreign-key dependency order derived
from the DDL. A dependency cycle keeps declaration order and is flagged. Seeded
rows are asserted through the running service where possible; direct row counts
are only read from the ephemeral zero-dep datastore, never from a shared engine.

**B32 client packs.** A client cannot render seeded data without an upstream, so
the pack includes a deterministic in-process API stub built from the project's
own API contract. The readiness check targets the dev server root; a functional
check requires a declared route. Flutter uses the real web-server device. WeChat
and ArkUI are only considered runnable when the generator supplies the bounded
DevTools or hvigor/hdc launcher; missing native tooling remains `NOT_RUN`.

**Polyglot repositories.** One lease covers the whole run. Secondary stacks are
declared and their absence from the assertions is explicit — a polyglot pack that
silently smoke-tests only its primary stack is reported as limited coverage, not
as a pass.
