# ELMOS runtime chart

This repository-owned chart deploys the production-runtime control plane as
separate scheduler, billing, and projector Deployments and deploys workers as a
StatefulSet behind a headless Service. A worker ordinal therefore has a stable,
exact address and a dedicated persistent journal volume.

The chart is fail-closed when `validation.enforceProductionValues=true`. It
requires separately reviewed digest-pinned control-plane and worker images,
distinct database roles and Secret keys, exact provider/model and worker-route
catalogs, object-storage encryption, transactional outbox delivery, HA replica
counts, PDBs, topology spread, persistent worker journals, service-mesh
protection for internal plaintext HTTP, Prometheus Operator scraping and
low-cardinality alerts, and exact egress CIDRs. Candidate gates
also set `fullnameOverride` so rollout, Chaos, worker-kill, and rollback commands
address the same resources without Helm name inference.

## Environment-owned prerequisites

The chart deliberately does not create or rotate credentials, grant database
roles, provision PostgreSQL/Redis/object storage, authorize external Provider
traffic, or authorize a deployment. Before installation, the target environment
must provide:

- the database Secret with distinct scheduler, billing, projector, and migration
  URL/username/password keys, after applying
  `deploy/production/postgres/production_runtime_roles.sql` through an approved
  database-administration workflow;
- the runtime, dedicated top-up authority, Gate, outbox, Provider, and
  object-storage credentials through pre-existing Secrets with distinct keys;
- Prometheus Operator `PodMonitor` and `PrometheusRule` CRDs, plus an
  observability namespace/pod selector that is exact and non-empty;
- a tokenless, least-privileged migration ServiceAccount;
- a namespace-level default-deny policy plus migration DNS/database egress that
  is already effective before Helm pre-install hooks run; the release-owned
  migration NetworkPolicy maintains that boundary after installation;
- exact database, Provider, object-storage, worker-engine, and outbox CIDRs,
  approved service-mesh policy, a multi-zone topology, and an exact worker
  storage class.

The migration hook starts the control-plane image in a migration-only mode. It
runs Flyway with a dedicated history table and exits; scheduler loops, HTTP
adapters, workload credentials, and Provider adapters are not started or
mounted in that process.

## Qualification and execution boundary

For local structural qualification:

```sh
helm lint deploy/helm/elmos-runtime --strict
helm lint deploy/helm/elmos-runtime --strict \
  --values tests/production-runtime/helm-production-values.yaml
```

The checked-in production fixture is non-secret and non-deployable; it proves
schema and template behavior only. An external run must use a separately
authorized, digest-bound values file, a public cosign key whose digest matches
the plan, and signed image/SBOM/SLSA provenance attestations through
`scripts/production-runtime/run_external_gate.py`. Local lint/render results do
not constitute target-cluster execution, deployment, independent verification,
or production certification.
