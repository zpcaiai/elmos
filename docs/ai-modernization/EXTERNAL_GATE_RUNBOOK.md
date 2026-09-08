# AI External Execution and Production Certification Gate

## Purpose

This gate separates four facts that must not be collapsed:

1. a provider is configured;
2. a real operation was executed;
3. a different actor verified immutable evidence from that operation;
4. an independently trusted certifier signed the exact complete evidence set.

Local tests can validate the contract, but cannot manufacture any of those
external facts. `UNKNOWN`, `FAIL`, `NOT_RUN`, and `NOT_CONFIGURED` all block
production certification.

## Safe preflight

The checked-in plan contains environment-variable names only. It does not
contain credentials and the preflight performs no network or provider action:

```sh
make ai-external-gate-preflight
```

The repository template is expected to report `BLOCKED` until all exact
provider, corpus, deployment, and certifier bindings are supplied. The Make
target treats that expected fail-closed result as a successfully validated
template; remove `--expect-blocked` when an operator needs readiness to be a
hard gate.

Control Plane and Runner configuration has a separate, network-free preflight:

```sh
make ai-runtime-preflight
```

Its checked-in contract is
`packages/repository-orchestrator/config/ai-runtime-plan.json`. It requires the
exact Control Plane URL, short-lived tenant-bound operations identity, expected
Runner node/pool/capabilities/version, digest-pinned agent and workload images,
and allowlist version. Missing or mutable values remain `BLOCKED`.

## Elasticsearch provisioning and execution

Use Elasticsearch as a disposable projection; PostgreSQL and repository
artifacts remain authoritative. Provision one exact Elasticsearch 8.19.3
deployment (or deliberately update the pinned client and expected version in
one reviewed change), then create an API key limited to the versioned index.
Do not grant cluster administration to the runtime key.

Copy `deploy/production/env/ai-integrations.env.example` into the deployment's
secret manager and set:

- the HTTPS endpoint, restricted API key, versioned index name, exact server
  version, and embedding dimension;
- a mounted CA file only when the deployment uses a private CA;
- a fresh synthetic request derived from
  `packages/repository-orchestrator/config/ai-external-execution-request.example.json`.

The adapter validates the exact server version and existing mapping, writes a
tenant/project/revision/ACL-bound bulk projection, refreshes it, performs
BM25+kNN+RRF retrieval with the same mandatory filters, deletes the synthetic
revision, and verifies deletion. It does not retry ambiguous provider results.

## Dify provisioning and execution

Create one Workflow application for qualification or bind an existing reviewed
Workflow. Its input contract must accept the application inputs plus the three
reserved trusted fields injected by ELMOS:
`_elmos_tenant_id`, `_elmos_project_id`, and `_elmos_purpose`. Browser input is
never allowed to set those fields. Create an application-scoped API key, record
the exact Workflow identity and deployed Dify version, and keep policy,
authorization, approval, and certification decisions in ELMOS.

The adapter reads `/v1/info`, calls `/v1/workflows/run` in blocking mode with a
unique idempotency key, accepts only `data.status=succeeded`, and stores only
digests and provider run identifiers in its receipt. Dify currently does not
expose a server-version assertion through that application endpoint, so the
version is configuration-bound and remains explicitly unverified by this
probe; bind it to the deployment artifact receipt during external verification.

After an operator has approved the exact synthetic request, set
`ELMOS_EXTERNAL_EXECUTION_ACK` equal to its `authorization_id` and execute once:

```sh
PYTHONPATH=packages/repository-orchestrator/src \
uv run --project packages/repository-orchestrator --locked --group test \
elmos-repository-orchestrator external-execute \
  --input /secure/path/ai-external-execution-request.json \
  --execute
```

Remove the acknowledgment after the run. Store stdout as the sanitized
producer receipt and preserve provider-native logs separately. Any timeout,
transport ambiguity, or HTTP failure is `UNKNOWN`; reconcile it by provider
run/request ID before issuing a new authorization.

## Control Plane and Runner deployment

The Control Plane is the existing Spring Boot service in `apps/control-plane`.
Deploy its immutable image with managed PostgreSQL, Flyway, OIDC/JWKS, object
storage secret files, exact digest-pinned workload images, and a short-lived
operations credential. Expose health and the tenant-bound fleet projection over
HTTPS; do not expose Runner enrollment or node credentials to Vercel or a
browser.

The Runner is the existing Java agent in `apps/runner-agent`. Render
`apps/runner-agent/deploy/runner-agent.yaml` once per node with a unique stable
node ID, dedicated PVC and enrollment Secret, exact agent image digest, exact
pool/capabilities and allowlist version. The workload sandbox remains rootless,
read-only-source, capability-dropped, and default-deny-network. Register the
node, have a distinct operator verify attestation, then wait for `READY` and a
fresh heartbeat. Do not scale one node identity with `replicas > 1`.

Put the server-side probe bindings from
`deploy/production/env/ai-runtime-probe.env.example` in the release operator's
secret manager. Once DNS/TLS, Control Plane and the exact Runner are live, run:

```sh
PYTHONPATH=packages/repository-orchestrator/src \
uv run --project packages/repository-orchestrator --locked --group test \
elmos-repository-orchestrator runtime-probe \
  --plan packages/repository-orchestrator/config/ai-runtime-plan.json \
  --execute
```

The probe verifies liveness, readiness, lease reaper activity, tenant-bound
fleet access, exact node/pool/agent version/capability/allowlist, independent
attestation state, and heartbeat freshness. It emits no operations credential.
The configured image digests are recorded as configuration-bound, not falsely
reported as runtime-observed; image provenance must be supplied by deployment
and attestation evidence.

Only after the Control Plane has a stable public HTTPS origin should the
Vercel server environment receive `ELMOS_CONTROL_PLANE_BASE_URL`. Keep
`ELMOS_OPERATIONS_API_KEY` server-only and short-lived. A local OrbStack or
Docker run is staging engineering evidence, not production deployment evidence.

## Evidence report

Every required operation must record one of `PASS`, `FAIL`, `UNKNOWN`,
`NOT_RUN`, or `NOT_CONFIGURED`. A `PASS` additionally requires:

- a non-synthetic evidence file below the selected evidence root;
- the exact SHA-256 of that file;
- distinct executor and verifier actors;
- the authorization identifier for that exact operation;
- the evidence role declared in the plan.

Evidence paths are repository-relative POSIX paths below the evidence root.
Absolute paths, traversal, symlinks, missing files, and digest mismatches fail
closed.

Validate a report and show its blockers without a certificate:

```sh
PYTHONPATH=packages/repository-orchestrator/src \
uv run --project packages/repository-orchestrator --locked --group test \
elmos-repository-orchestrator external-certify \
  --plan packages/repository-orchestrator/config/ai-external-gate-plan.json \
  --report docs/ai-modernization/external-execution-report-20260908.json \
  --evidence-root docs/ai-modernization
```

An uncertain provider result is never retried blindly. Reconcile it using the
provider's operation/request identifier, then append new evidence under a new
authorized execution record.

## Independent certificate

Certification is possible only when all ten operations are `PASS` and an
independent certificate binds all of the following:

- gate ID, exact repository revision, and artifact digest;
- canonical report digest and canonical evidence-set digest;
- certifier actor and organization;
- fresh certification and expiry timestamps;
- the public-key digest pinned in the plan;
- a valid detached `SHA256_WITH_PEM_KEY` signature.

Run the same `external-certify` command with `--certificate` and
`--public-key`. The producer cannot predeclare certification, the certifier
cannot equal the producer, and a placeholder trust root is rejected.

## Current external result

The 2026-09-08 bounded live run found no exact Elasticsearch or Dify Vercel
integration or configured binding. OpenAI model inventory returned HTTP 200,
but the single authorized generation attempt returned HTTP 429 and remains
`UNKNOWN`. Gemini inventory and generation returned HTTP 400 and are `FAIL`.
No Elasticsearch, Dify, collector, multimodal, representative production
workload, deployment, or independent-certifier execution was available.

Therefore the current report is valid evidence of a blocked gate, not evidence
of completion: external operations are not all `PASS`, and production remains
`NOT_CERTIFIED`.
