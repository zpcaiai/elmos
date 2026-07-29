# Project Generation Qualification

Date: 2026-07-29

## Scope

This qualification covers the one-click project-generation flow from simple
description, TXT, Markdown, Word `.docx`, HTML, text-bearing PDF, repository
Skill, repository workspace, or public HTTPS HTML through:

- source extraction and provenance binding;
- review and approval;
- deterministic project generation;
- native build, test, startup, health, file-tree, and archive checks;
- local software/hardware and run documentation;
- cloud deployment guidance and the exact evidence boundary.

## Executed evidence

| Area | Command or evidence | Result |
|---|---|---|
| Source parser/security | `playwright test --project=chromium e2e/generation-source-ingestion.spec.ts` | 9 passed |
| Deterministic fuzzing | seed `1592594996`, 256 bounded cases | passed |
| Mutation negative controls | allow-all-IPv4 and allow-loopback-IPv6 | 2/2 killed |
| Independent stored corpora | negative, holdout, representative engineering workloads | passed locally |
| Web type/build | `pnpm check` | passed |
| Production dependency audit | `pnpm audit --prod --audit-level high` | no known vulnerabilities |
| Browser/accessibility matrix | Chromium, Firefox, WebKit, mobile Chromium, mobile WebKit | 23 passed, 27 intentionally skipped |
| Browser skip boundary | heavy format/Runner representatives run once in Chromium; common rendering, keyboard, axe, failure-close, production profile, and both mobile layouts run on their declared projects | expected |
| Project Synthesis Engine | `pytest -q` | 67 passed |
| Python quality | Ruff and strict MyPy over 30 source files | passed |
| Real one-click Runner | `generation-runner.spec.ts` | 5 passed in 9.0 minutes |
| Batch 35 pack | validator and conservative gate | structurally passed, `NOT_CERTIFIED` |
| Local container handoff | Docker 29.4.0 build/start/health/stop/remove | passed |
| Batch 33 Cloud pack | validator and conservative gate | structurally passed, `experimental` |

The browser run intentionally executes the expensive multi-format parsing,
repository handoff, task recovery, and full runtime representatives once in
Chromium. Cross-browser rendering, keyboard focus, axe accessibility, failure
closure, production-profile controls, and mobile overflow/action reachability
are exercised on the applicable Chromium, Firefox, WebKit, Pixel, and iPhone
projects.

## Security boundaries exercised

- anonymous session discovery returns an explicit anonymous representation
  without generating a browser-level 401 resource error;
- protected generation actions still reject invalid credentials and prevent
  approval or generation;
- file count, file size, declared/actual size, UTF-8, empty content, legacy
  `.doc`, and unsupported extension failures;
- script/style removal from uploaded HTML;
- loopback, private, link-local, carrier-grade NAT, documentation, multicast,
  reserved, and IPv4-mapped IPv6 address rejection;
- credential, query, and fragment removal from recorded online origins;
- source count, text truncation, SHA-256 provenance, and deterministic bundle
  digest behavior;
- Skill-name traversal rejection, real-path containment, symlink rejection,
  and imported-Skill non-execution warning.

## Local container evidence

The generated Python 3.12 FastAPI target used the pinned base:

`python:3.12.12-slim@sha256:f3fa41d74a768c2fce8016b98c191ae8c1bacd8f1152870a3f9f87d350920b7c`

The built image ran with:

- user `10001:10001`;
- read-only root filesystem;
- all Linux capabilities dropped;
- `no-new-privileges`;
- loopback-only host publication;
- `/health` response `{"status":"UP","service":"cloud-handoff-service"}`.

The container, test image, and temporary generation workspace were removed
after the probe.

## External cloud boundary

Google Cloud Run remains `NOT_RUN`, not failed and not certified:

- `gcloud` is not installed;
- no approved isolated Google Cloud project, billing/data-residency owner, or
  short-lived credential was provided;
- remote plan/apply, immutable Artifact Registry digest, authenticated runtime
  probe, revision rollback, destroy/orphan cleanup, drift, cost, and
  production-representative evidence do not exist.

Azure CLI is installed but not logged in. AWS CLI has incomplete credentials.
Neither is an authorized substitute for the exact Google Cloud Run route.

The generated project still includes detailed local and cloud requirements,
exact configuration obligations, least-privilege identity guidance, immutable
image and Secret requirements, health validation, rollback, and cleanup steps.
The Batch 33 pack records the missing external prerequisites and fails closed.

## Remaining certification limits

The feature is complete and runnable within the verified local scope. It is not
independently certified and must not be presented as production-cloud proven
until the exact Cloud Run route is executed in an approved isolated project
with independent evidence. Controlled public DNS-rebinding tests, independent
holdout review, and production-derived workloads also remain `NOT_RUN`.
