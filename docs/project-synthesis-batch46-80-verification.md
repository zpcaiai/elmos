# Project Synthesis Batch 46–80 verification

## Integrated scope

- PG001–PG170: canonical Batch 46–60 Project Synthesis specifications.
- PG171–PG222: canonical Batch 61–65 change, runtime, evaluation, Domain Pack, and Requirement Studio specifications.
- PG223–PG417: 195 canonical Batch 66–80 polyglot language and engineering-asset Skills.
- Repository master Skill: `.agents/skills/elmos-project-synthesis/`.
- Installed Batch 66–80 Runtime Skills: `agent-skills/runtime/b66-*` through `agent-skills/runtime/b80-*`, each digest-equal to its canonical source and carrying `agents/openai.yaml`.

The combined structural inventory is 417 contiguous PG specifications across Batch 46–80 and 27 Schemas including the repository request contract.

## Runnable boundary

The bundled `engines/project-synthesis-engine` has a real acceptance path for eight conservative API starter profiles:

- Java 21 / Spring Boot 3.5.3
- Python 3.12 / FastAPI 0.116.1
- .NET 10 / ASP.NET Core
- TypeScript / Node 26 / NestJS-Fastify
- Go 1.25 / net-http
- Kotlin 2.2.20 / Ktor
- PHP 8.4.12 / native HTTP
- Rust 1.89 / Axum

It generates a bounded CRUD API profile with configuration, tests, OpenAPI, CI, a non-root container, Kubernetes assets, traceability, and a content-addressed manifest. All eight emitters are admitted to the exact PostgreSQL plus JWT/OIDC production profile; each profile still requires its own native integration evidence. Batch 66–80 does not silently extend the emitter beyond these eight targets. C/C++, Flutter/Dart, Swift, shell, SQL/API, build/proxy, container, IaC/Kubernetes/Helm, CI/CD, and polyglot operations route through the exact installed Runtime Skill and require their actual target toolchain and environment.

Generated workspaces include `requirements/project-structure.json`, `requirements/declared-dependency-graph.json`, and `requirements/project-insights.json`, plus `docs/PROJECT_INSIGHTS.md`. The report renders actual generated roots and applications, declared runtime/framework/build/provider edges, requirements-to-target mapping, per-target native verification, and the complete selected-target source/target matrix. Direct pairwise semantic and behavioral cells remain `NOT_RUN` unless that exact comparison ran.

## Reproducible checks

```bash
make batch66-80-skills
make project-synthesis
uv --directory engines/project-synthesis-engine run --locked python scripts/run_acceptance.py --require-all-toolchains
```

`make batch66-80-skills` verifies every immutable source-package file hash, all 195 Skill IDs/names/headings, PG223–PG417 continuity, installed source equality, Codex interfaces, Schemas, and the combined PG001–PG417 integration. `make project-synthesis` executes the pinned starter-engine tests, Ruff, mypy, available-toolchain generation/build/test/startup probes, production-profile checks, and safe-regeneration checks. The explicit `--require-all-toolchains` command fails if any of the eight exact toolchains is missing. `make toolchains-check` validates the separate exact runtime prerequisites without upgrading certification state.

## Retained local snapshot — 2026-07-22

- Source package: 195/195 Skills valid, PG223–PG417 continuous; 3 installer/package regression tests passed.
- Official `skill-creator` quick validation: 195/195 installed Runtime Skills passed; the master `$elmos-project-synthesis` Skill passed separately.
- Combined integration: 417 Project Synthesis specifications and 27 Schemas passed.
- Starter engine: 5 unit tests passed; Ruff and mypy passed; acceptance generated 60 files and completed 7 build/analysis checks.
- Startup in this retained snapshot covered Java, Python, and C# only; it is not evidence for the five subsequently bundled targets.
- `production_delivery_status` and `external_certification_status` remained `NOT_RUN`.

## Evidence boundary

Package validation, runtime discovery, and local starter acceptance are engineering evidence. They are not proof that proprietary SDKs, mobile/device targets, C/C++ routes, external databases, containers, Kubernetes clusters, Terraform providers/backends, cloud accounts, signing identities, protected runners, GitHub/GitLab/Jenkins providers, customer environments, or production controls ran.

Those checks remain `NOT_RUN` until executed for an exact approved profile with immutable commands/logs/artifacts, environment and source digests, authorization, deterministic replay, cleanup, and independent verification where required. No local command in this integration can issue a production or certification decision.
