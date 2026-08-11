# Project Generation Qualification

Date: 2026-08-10

## Scope

This qualification covers the one-click project-generation flow from simple
description, TXT, Markdown, Word `.docx`, HTML, text-bearing PDF, repository
Skill, repository workspace, or public HTTPS HTML through:

- source extraction and provenance binding;
- review and approval;
- deterministic project generation;
- native build, test, startup, health, file-tree, and archive checks;
- a browser-only preview governed by a server-issued 600-second production
  lease, with exact health confirmation, countdown, expiry, and cleanup;
- complete repository ZIP download;
- explicit creation of a new private GitHub repository from the exact
  artifact-bound file set, with remote Branch and Tree readback;
- local software/hardware and run documentation;
- cloud deployment guidance and the exact evidence boundary.

## Executed evidence

| Area | Command or evidence | Result |
|---|---|---|
| Source parser/security | `playwright test --project=chromium e2e/generation-source-ingestion.spec.ts` | 10 passed |
| Deterministic fuzzing | seed `1592594996`, 256 bounded cases | passed |
| Mutation negative controls | allow-all-IPv4 and allow-loopback-IPv6 | 2/2 killed |
| Independent stored corpora | negative, holdout, representative engineering workloads | passed locally |
| Web checks | `pnpm check` | durable-lease tests 4/4, TypeScript, and Next.js 16.2.12 production build passed |
| Production dependency audit | `pnpm audit --prod --audit-level high` | no known vulnerabilities |
| Browser/accessibility matrix | Chromium, Firefox, WebKit, mobile Chromium, mobile WebKit | 21 passed, 19 intentionally skipped |
| Browser skip boundary | heavy format/Runner representatives run once in Chromium; common rendering, keyboard, axe, failure-close, production profile, and both mobile layouts run on their declared projects | expected |
| Full 600-second browser lease | `ELMOS_E2E_FULL_RUNTIME_TTL=true ... --grep '需求分析、完整代码下载'` | 1 passed in 11.4 minutes; health remained `UP`, server expiry produced `STOPPED`, and port 8082 was closed |
| GitHub positive browser journey | local protocol-faithful GitHub mock | 1 passed in 1.6 minutes; downloaded ZIP bytes matched the response and job SHA-256, blobs were byte-read back, and the private Branch/Tree/Commit were verified |
| GitHub negative/reconciliation/concurrency | bounded mock fault injection | 1 passed in 2.5 minutes plus focused chunked-auth and hosted-fail-closed cases; no automatic repository DELETE occurs |
| Project Synthesis Engine | `.venv/bin/python -m pytest tests -q` | 98 passed |
| Runtime reaper | `test_generation_runtime_reaper` | 14 passed |
| Rootless lease controller | `test_rootless_project_runner` | 16 passed |
| Backup and storage GC | `test_generation_runner_operations` | 9 passed |
| Runtime/operations combined replay | three suites above | 39/39 passed |
| Python quality | Ruff and strict MyPy | passed; MyPy checked 32 source files |
| Batch 35 pack | validator and conservative gate | `PASS`, status `limited`, decision `NOT_CERTIFIED` |
| Batch 33 Cloud pack | validator and conservative gate through `uv --with jsonschema` | `PASS`, status `experimental` |
| Current production rootless execution | real Linux systemd, same-UID rootless engine, restart and 600-second cleanup | `NOT_RUN` on this Darwin host |

The browser run intentionally executes expensive multi-format parsing,
repository handoff, task recovery, GitHub side effects, and the full runtime
representative once in Chromium. Cross-browser rendering, keyboard focus, axe
accessibility, failure closure, production-profile controls, and mobile
overflow/action reachability are exercised on the applicable Chromium,
Firefox, WebKit, Pixel, and iPhone projects. Side-effecting Runner journeys are
serialized because `HOST_DEVELOPMENT` uses fixed language ports; production
uses the rootless path with dynamic loopback publication.

Long native generation pipelines emit a persisted heartbeat every 30 seconds
and remain bounded by the Runner's 20-minute pipeline limit. Each native build
or analysis command has a bounded 600-second default, configurable only from 30
through 900 seconds. Browser qualification observes the pipeline for 21 minutes
inside a 25-minute journey limit, so it records either the file tree or an
explicit `BLOCKED` state after the product boundary; absence of output is never
treated as success.

Locked Python dependency synchronization retries exactly once only when a
completed command returns an allowlisted transient network/fetch failure. A
hard command timeout never retries because it has already consumed the entire
step budget. Build, test, type, security, lock-integrity, and all other failures
remain immediate fail-closed results, and retry evidence is retained in the
verification output.

The Runner uses a service-owned persistent uv cache. On this host, the first
PostgreSQL/JWT representative populated a cold cache and completed in 8.7
minutes; the following PostgreSQL/OIDC representative reused it and completed
in 1.8 minutes. Production operators must prewarm the exact locked dependencies
or approved offline images before advertising low-latency generation. Cache
reuse is a performance optimization, not verification evidence.

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
- GitHub publication rejects non-HTTPS production endpoints, invalid or reused
  job/artifact identities, existing repositories, non-private creation,
  malicious repository URLs, malformed Git objects, truncated or mismatched
  remote Trees, and credentials that cannot perform the requested operation.
  Token values are absent from browser storage, persisted job state, generated
  files, and logs.
- Every remote blob is streamed back as raw bytes and matched to the local size
  and SHA-256; JSON and raw responses are independently byte-bounded. Creation
  uncertainty persists a reconciliation-required receipt and never adopts a
  repository based on a client marker. After any confirmed creation failure,
  the repository is retained for explicit manual cleanup: the service performs
  no owner/name DELETE that could race a same-name replacement.
- Direct publication admits at most one in-memory snapshot per Node process and
  one per tenant. The local Runner identity is one exact configured tenant.
  A production direct-publisher configuration additionally requires an exact
  tenant-to-owner allowlist binding; it is not a multi-tenant GitHub contract.
- Hosted execution returns `GITHUB_PUBLISH_HOSTED_EXECUTION_NOT_RUN` before body
  consumption or provider access. A hosted control-plane publisher remains
  `NOT_RUN` until a separately governed provider contract is implemented.

## Prior local container evidence (dated)

The following Docker handoff was recorded on 2026-08-08. It is useful prior
engineering evidence, but it is not digest-bound to the final code in this
qualification and is not substituted for a current production rootless run.

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

## Storage and retention boundary

The Runner now applies tenant job-count and byte reservations, bounded growth
monitoring, source/review expiry cleanup, symlink-safe size accounting, and an
offline backup-bound retention/GC state machine. Its 9 operation tests include
fault injection, interrupted recovery, strict backup-manifest verification,
legal-hold fail-closed behavior, and deletion receipts. A real production
schedule, external backup target, restore drill, legal-hold authority, and
retention-policy approval remain `NOT_RUN`; the offline operator procedure must
be installed and monitored before commercial retention claims are made.

## External cloud boundary

Google Cloud Run remains `NOT_RUN`, not failed and not certified:

- `gcloud` is not installed;
- no approved isolated Google Cloud project, billing/data-residency owner, or
  short-lived credential was provided;
- remote plan/apply, immutable Artifact Registry digest, authenticated runtime
  probe, revision rollback, destroy/orphan cleanup, drift, cost, and
  production-representative evidence do not exist.

Generated projects now contain a locally tested, plan-first
`deploy/cloud-run-control.py`. It refuses provider mutations by default,
requires exact expiring authorizations for deploy/rollback/destroy, stages a
no-traffic candidate, checks the private health contract, and only then moves
traffic. This closes the code-generation and control-flow gap; without an
approved project and `gcloud`, it does not close the provider-evidence gap.

Azure CLI is installed but not logged in. AWS CLI has incomplete credentials.
Neither is an authorized substitute for the exact Google Cloud Run route.

Public GitHub publication also remains `NOT_RUN`: no user credential or
authorized non-production GitHub organization was supplied. The local browser
journey executes the same REST request sequence against a bounded mock and
proves application control flow, credential rejection, exact object graph,
readback, and UI behavior; it is not GitHub availability, organization policy,
branch-protection, billing, abuse-limit, or external-provider evidence.

Hosted-execution GitHub publication is deliberately blocked before request-body
consumption or provider access with
`GITHUB_PUBLISH_HOSTED_EXECUTION_NOT_RUN`. The current control plane has no
durable hosted publication/receipt endpoint, so the Web BFF does not pretend the
local publisher can update a remotely stored job. Direct production publication
is restricted to one explicitly bound tenant and owner allowlist; this is not a
multi-tenant GitHub integration claim.

The generated project still includes detailed local and cloud requirements,
exact configuration obligations, least-privilege identity guidance, immutable
image and Secret requirements, health validation, rollback, and cleanup steps.
The Batch 33 pack records the missing external prerequisites and fails closed.

The console action is deliberately labelled **one-click local deploy/run**. It
starts only an allowlisted generated target on loopback, waits for the exact
`/health` response before reporting `RUNNING`, and exposes an explicit stop
action. It does not call a cloud provider and must not be described as one-click
Cloud Run deployment.

## Remaining certification limits

The browser-local `HOST_DEVELOPMENT` Python journey is exercised end to end,
including a real wall-clock 600-second healthy lease, download digest binding,
automatic stop, and local protocol-mock GitHub publication. The production
`ROOTLESS_CONTAINER` implementation has unit and fault-injection evidence, but
real Linux systemd installation, same-UID Docker/Podman socket access, service
restart, a real rootless 600-second run, and verified container/network/volume/
image/secret cleanup remain `NOT_RUN`. Cleanup begins at lease expiry and is not
claimed to make every engine resource disappear at exactly 600.000 seconds.

The Web runtime adapter is not real-runtime-qualified across all eight target
languages; current end-to-end browser evidence is the Python representative.
Hosted GitHub, public GitHub/GHES, Cloud Run apply/rollback/destroy, production
storage scheduling, independent holdout review, controlled public
DNS-rebinding, and production-derived workloads remain `NOT_RUN`. The Batch 35
source-ingestion pack remains `limited / NOT_CERTIFIED`, and the Batch 33 cloud
pack remains `experimental`. None of these local results is independent
certification or production-cloud evidence.
