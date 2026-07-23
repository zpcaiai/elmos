---
name: elmos-cross-service-operability-closure
description: Detect and repair ELMOS cross-service operability gaps across Compose, service discovery, environment configuration, health probes, production profiles and Web Console backend routing. Use when local pages always fall back, containerized services cannot reach each other, ports or application names drift, dependencies are missing, or production-readiness wiring must be verified without claiming external execution.
---

# ELMOS Cross-Service Operability Closure

## Objective

Verify that a valid in-repository user journey remains reachable after applications are containerized. Host loopback, Compose DNS, published host ports and container ports are different scopes; a configuration that works from the host may be broken inside a service.

## Inventory

Read:

- `deploy/compose/docker-compose.yml`
- `deploy/rootless-docker/`
- every included service `application.yml` and `application-prod.yml`;
- Web Console server-side API routes and environment lookups;
- `tooling/validate_runtime_operability.py` and its tests;
- Dockerfiles, health endpoints and dependency declarations.

Classify long-lived services separately from per-workspace resources. Do not turn the workspace-scoped egress proxy into a shared Compose service; Workspace Service must create it with an approved image digest and workspace binding.

## Workflow

1. Build an exact table of service name, application name, container port, published host port, health path, required dependencies, credentials/config sources and caller URLs.
2. Trace each server-side call from the caller's network namespace.
3. Require Compose callers to use service DNS names, not `127.0.0.1` or host-only published addresses, for sibling containers.
4. Confirm each configured service target exists in Compose and the caller declares an appropriate startup dependency.
5. Validate unique application names and default ports.
6. Require graceful shutdown, safe error responses, liveness/readiness probes and bounded externalized shutdown timeouts for Spring services.
7. Require production database URL, user and password with no default values.
8. Keep disabled local external capabilities explicit; do not invent image digests, credentials, GitHub Apps, Runners or providers.
9. Add a negative validator test for every repaired topology defect.

## Web Console contract

For containerized Web Console capability routes:

- set `CONTROL_PLANE_BASE_URL` to the Compose service URL;
- depend on `control-plane`;
- use a bounded timeout and `no-store` for capability reads;
- return `REPOSITORY_CONTRACT` when unavailable;
- return `LIVE_API` only after a successful compatible response;
- retain external execution evidence as `NOT_RUN` unless authoritative live evidence says otherwise and the contract permits it.

## Network boundaries

- `127.0.0.1` refers to the current container, not the host or a sibling service.
- Published ports serve host access and are not service-discovery identifiers.
- Compose service DNS names are local-development topology, not production DNS proof.
- Workspace egress remains default deny and digest-pinned.
- Never broaden egress, expose management endpoints, add plaintext production credentials or weaken tenant isolation to make connectivity pass.

## Validator contract

Extend `tooling/validate_runtime_operability.py` conservatively. The report must include:

- service and database-service counts;
- unique names and ports;
- Web-to-control-plane routing status;
- checked configuration artifacts with digests;
- machine-readable errors;
- `engineering_evidence_only: true`;
- `external_evidence_status: NOT_RUN`.

Static topology validation is not a startup, authenticated route, provider, customer or production result.

## Required tests

Include:

- valid repository topology passes;
- missing Web Console backend URL fails;
- loopback backend URL fails in Compose;
- unknown target service fails;
- missing dependency fails;
- readiness probe removal fails;
- defaulted production credential fails;
- duplicate port or application name fails.

## Verification

Run:

```bash
uv run --with pyyaml python tooling/validate_runtime_operability.py
uv run --with pyyaml python -m unittest discover -s tests/production-readiness -p 'test_*.py'
make production-readiness-check
```

If approved local containers are started, add real health and route probes as separate evidence. Do not treat static Compose parsing as proof that images started.

## Completion criteria

- All sibling-service URLs resolve in the declared topology.
- Required dependencies are explicit.
- Capability fallbacks disclose their source and never fabricate live state.
- Production secrets remain required and externalized.
- Negative topology regressions are enforced by the production-readiness test suite.
- External and production evidence remains `NOT_RUN` until real authorized execution.
