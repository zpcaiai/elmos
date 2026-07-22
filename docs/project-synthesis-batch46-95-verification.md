# Project Synthesis and Language Packs Batch 46–95 verification

## Integrated scope

- Global PG001–PG170: canonical Batch 46–60 Project Synthesis specifications.
- Global PG171–PG222: canonical Batch 61–65 change, runtime, evaluation, Domain Pack, and Requirement Studio specifications.
- Global PG223–PG417: 195 canonical Batch 66–80 polyglot language and engineering-asset Skills.
- Package-local PG223–PG402: 180 canonical Batch 81–95 specialized Language Pack Skills.
- Repository master Skill: `.agents/skills/elmos-project-synthesis/`.
- Installed Language Pack aliases: `agent-skills/runtime/b81-*` through `agent-skills/runtime/b95-*`, each with official Codex frontmatter and `agents/openai.yaml`.

The integrated inventory contains 417 globally numbered Project Synthesis specifications, 180 package-local Language Pack specifications, and 42 Schemas including the repository request contract. The Language Pack IDs deliberately remain in the `elmos.language-packs` package-local namespace: their PG223–PG402 values overlap the global Batch 66–80 range and are never renumbered or presented as global PG418 onward. The normalized install manifest binds every `$b81-*`–`$b95-*` alias to its original package ID, name, Batch, status, source digest, installed digest, and interface digest.

## Runnable boundary

The bundled `engines/project-synthesis-engine` has a real acceptance path for three conservative starter profiles only:

- Java 21 / Spring Boot 3.5.3
- Python 3.12 / FastAPI 0.116.1
- .NET 10 / ASP.NET Core

It generates one primary CRUD aggregate with in-memory persistence plus configuration, tests, OpenAPI, CI, a non-root container, Kubernetes assets, traceability, and a content-addressed manifest. Batch 66–95 expands governed Skill routing and evidence contracts; it does not silently expand the emitter.

COBOL/mainframe, SAP ABAP, database procedure languages, IEC 61131-3 PLC, MATLAB/Simulink, Modelica/FMI, VB/Office, IBM i RPG, R, SAS, Salesforce, Objective-C/Swift, Delphi/Object Pascal, BEAM, and Lua/OpenResty requests route through the smallest exact installed alias. Their results must preserve dialect, encoding, numeric, transaction, timing, vendor, runtime, safety, and authorization boundaries.

## Reproducible checks

```bash
make language-packs-batch81-95
make project-synthesis
```

`make language-packs-batch81-95` verifies the immutable source package, all 180 package-local specifications, 15 Schemas and examples, normalized installed identities and interfaces, collision declaration, and the combined Project Synthesis integration. `make project-synthesis` additionally executes the pinned Java/Python/C# starter-engine unit, static, generation, build, test, startup, and safe-regeneration checks.

## Local result — 2026-07-22

- Source package: 180/180 Skills and 15/15 Schemas passed its structural validator; package-local IDs remained PG223–PG402.
- Normalized installation: 180 aliases and 180 Codex interfaces matched the digest-bound install manifest.
- Official `skill-creator` quick validation passed all 180 installed aliases and the master `$elmos-project-synthesis` Skill.
- Draft-compatible JSON Schema validation passed all 15 source Schema/example pairs.
- Combined integration: 417 global specifications, 180 package-local Language Pack specifications, and 42 Schemas passed.
- Starter engine: 5 unit tests, Ruff, and mypy passed; acceptance generated 60 files and completed 7 build/analysis checks.
- Startup probes passed for Java, Python, and C# on ports 8081, 8082, and 8083.
- Native/vendor/physical Language Pack execution remained `NOT_RUN`; no certification, cutover, safety, or production approval was issued.

## Evidence boundary

Package validation, Codex interface validation, JSON Schema checks, generated test design, and the local Java/Python/C# starter acceptance are engineering evidence only. They are not proof that a mainframe, SAP system, production database, PLC or safety controller, MATLAB/Simulink or Modelica toolchain, IBM i, SAS, Salesforce org, Apple or Windows vendor runtime, BEAM cluster, Lua/OpenResty host, representative parallel-run environment, or target hardware ran.

Those checks remain `NOT_RUN` until executed for an exact approved profile with immutable commands, logs, artifacts, environment and source digests, authorization, deterministic replay, cleanup, and independent qualified verification. Static text and generated fixtures cannot satisfy native parser/compiler/simulator/runtime, transaction, numerical, timing, safety, or vendor evidence.
