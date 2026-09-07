# Batch 46 — Runnable smoke packs: implementation contract

## Purpose

Every project ELMOS converts or generates must be runnable by its recipient with
one command, against data ELMOS supplies, without the recipient owning a
database, filling in a `.env`, or reading a wiki first.

Batch 46 is the capability that makes that true. For each generated or converted
project it derives the minimal data the project needs in order to start,
synthesizes that data as disposable fixtures, emits one-click entries, runs a
functional smoke test, and reclaims everything when the free runtime lease
expires.

## Scope

In scope: getting a generated artifact to start, answer, and shut down cleanly on
someone else's machine.

Out of scope, permanently: route or dialect equivalence, framework behavioural
parity, performance, security, accessibility, and every certification claim.
Those belong to Batches 29-45 and a passing smoke run never substitutes for
them. A Batch 46 `runnable` status is a precondition for a reviewer being able
to look at the artifact at all — not evidence that the artifact is correct.

## Covered stacks

| Family | Source | What Batch 46 adds |
| --- | --- | --- |
| B29 | directed language routes (Java, C#, Python, TypeScript) | start command, port, readiness probe, seeded functional call on the target |
| B30 | framework packs (Spring Boot, Quarkus, Micronaut, Jakarta, ASP.NET, Django, FastAPI, Flask, Express, NestJS) | framework-aware readiness path, dependency install, framework config seeding |
| B31 | database and data-platform packs | DDL-derived minimal rows in dependency order, ephemeral engine, reconciliation-safe teardown |
| B32 | client modernization packs | deterministic API stub, minimal page data, dev-server entry |
| polyglot | any combination of the above in one repository | one primary entry, declared secondary stacks, shared lease |

## Pipeline

Four stages, each with a typed artifact under `<project>/smoke/`:

1. **detect** → `profile.json`. Stacks, datastores, contract files, ports.
   Every claim carries file-and-marker evidence. What cannot be resolved goes to
   `unknown`.
2. **derive** → `minimal-data-requirements.json`. The smallest environment,
   dataset and stub set required to reach readiness and serve one request.
3. **synthesize** → `seed/` + `seed-manifest.json`. Disposable fixtures with a
   recorded data-source class per artifact.
4. **emit** → `run-smoke.sh`, `run-smoke.ps1`, `Makefile.smoke`,
   `docker-compose.smoke.yml`, `smoke/tools/`, `assertions.json`,
   `runner-manifest.json`.

`scripts/batch46/scaffold_smoke_pack.py` runs all four.

## Hard requirements

- **Self-contained.** The runner is vendored into `smoke/tools/` and uses only
  the Python standard library. A recipient with the project and Python 3 can run
  it. Nothing resolves back to the ELMOS repository at run time.
- **Minimal means minimal.** A nullable column with no constraint gets no value.
  Seed one row per table unless a declared constraint demands more. A smoke pack
  that ships a test corpus has failed its own definition.
- **Deterministic.** The same pack produces the same seed values. The seed is
  the requirements digest unless overridden.
- **Recognisably fake.** Generated values carry a `SMOKE-`, `smoke-` or
  `smoke.invalid` marker; primary keys come from the reserved range at or above
  900,000,000 so a fixture row can never collide with an application row.
- **Honest entries.** An entry that cannot be supported is emitted as
  `unavailable` with a reason. It is never faked, and never made to look
  available by weakening what it checks.
- **No silent engine swaps.** The zero-dependency entry exists only where an
  approved embedded substitute is declared, and it always carries its semantic
  warning. Substituting an engine the project does not declare support for is a
  correctness change wearing a convenience costume.
- **Leased, not deployed.** Every run is bounded by the runtime lease in
  `RUNTIME_LEASE_POLICY.md`. Expiry stops every started service and deletes
  every byte of smoke data.
- **NOT_RUN never passes.** An entry that could not execute — no Docker daemon,
  no toolchain, no start command — is recorded as `NOT_RUN` and blocks the gate.

## Repository layout

```
scripts/batch46/     detect / derive / synthesize / emit / run / validate / gate
templates/batch46/   JSON templates and per-stack runner templates
docs/batch46/        this contract, quality gates, data policy, lease policy, matrix
tests/batch46/       unit and real-execution tests
.agents/skills/b46-* repository-scoped Codex skills
```

Inside a generated project:

```
run-smoke.sh · run-smoke.ps1 · Makefile.smoke · docker-compose.smoke.yml
smoke/
  pack.json  profile.json  minimal-data-requirements.json
  assertions.json  runner-manifest.json  seed-manifest.json  README.md
  seed/     seed.sql  api-fixtures.json  env.smoke  runtime-overrides.json
  tools/    run_smoke.py  smoke_lease.py  smoke_common.py
  runtime/  lease.json  lease-result.json  result.json  gate-*.{json,md}  logs/
```

`smoke/runtime/` is disposable output. Everything above it is pack content and
belongs in version control.

## Interaction with other batches

- Batch 46 consumes the outputs of Batches 29-33 generators; it never modifies
  target source code. If a project needs source changes to start, that is a
  generator defect, and it is reported as one rather than patched in `smoke/`.
- `tst-generated-project-build-run-shutdown` (X006) remains the strict lifecycle
  test. Batch 46 supplies the runnable artifact that test exercises; it does not
  replace it.
- Batch 44 owns the economics of extension time beyond the free quota. Batch 46
  only records `billable_seconds`.
