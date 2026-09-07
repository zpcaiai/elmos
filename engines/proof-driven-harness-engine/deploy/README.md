# Deployment boundary

The image and Helm assets are production-shaped but intentionally unpinned in
source control. A release pipeline must supply an approved base-image digest,
the built image digest, SBOM, signature, provenance, database migration
receipt, and exact release-manifest digest. Placeholder tags and mutable image
references are rejected by policy.

The runtime image build also invokes the installed release-contract verifier
with `RELEASE_MANIFEST_SHA256`. It rejects an unpinned manifest, any digest
drift, symlink or special-file member, and every unmanifested runtime or asset
file (including native extensions, `__pycache__` directories, and `.pyc`
bytecode). The image installs with `pip --no-compile`; the verifier reopens
anchored pathnames and repeats file-digest and exact-tree scans before passing.
This is a local byte-integrity gate only; it does not provide a signature,
deployment evidence, or certification.

Example build shape (values are supplied by the release system):

```bash
docker build -f deploy/Dockerfile \
  --build-arg PYTHON_BASE="registry.example/python@sha256:<approved>" \
  --build-arg SOURCE_REVISION="<git-sha>" \
  --build-arg RELEASE_MANIFEST_SHA256="sha256:<manifest>" \
  --tag "registry.example/elmos/proof-harness:<version>" .
```

The chart requires `image.repository`, `image.digest`,
`config.existingSecret`, `postgresql.existingSecret`, the distinct
`postgresql.authorityExistingSecret`, and an exact `runtimeAssurance.factory`
value in `module.path:factory` syntax. Helm injects
that value as `ELMOS_RUNTIME_ASSURANCE_FACTORY`; the callable receives the same
`PostgresStore` used by the durable control plane and must return a fully
configured `RuntimeAssuranceControlPlane` bound to that exact store. Empty or
malformed references, failed imports/calls, wrong return types, store swaps,
and unready configured providers fail closed. The image deliberately contains
an empty factory default, so direct `docker run` also refuses production
startup until the orchestrator supplies the reviewed deployment module:

```bash
docker run --rm \
  -e ELMOS_RUNTIME_ASSURANCE_FACTORY='company.proof_harness.runtime:create_control_plane' \
  'registry.example/elmos/proof-harness@sha256:<image-digest>'
```

For Helm, bind the same reviewed module explicitly (alongside the other
required production values):

```yaml
runtimeAssurance:
  factory: company.proof_harness.runtime:create_control_plane
postgresql:
  existingSecret: proof-harness-postgresql-app
  dsnKey: postgres-dsn
  authorityExistingSecret: proof-harness-postgresql-authority
  authorityDsnKey: postgres-authority-dsn
```

The deployment-owned callable has the contract
`create_control_plane(store: PostgresStore) -> RuntimeAssuranceControlPlane`.
It must configure the trusted authority provider, evidence service, exact
permission/protocol profiles, producer and model allowlists, signature
verification, interceptors, and event validators/upgraders required by the
deployment; the repository supplies no empty-provider fallback.

The PostgreSQL secrets must contain the application DSN under
`postgresql.dsnKey` and the distinct authority-writer DSN under
`postgresql.authorityDsnKey`. The chart never creates a database, embeds a
password, or falls back to a pod-local SQLite file. The application identity
is read-only for Host authority and budget-reservation receipts; only the
separately authenticated, migration-constrained authority writer may create
them. The two default replicas share one externally managed PostgreSQL service.
Startup/readiness call `/readyz`, whose durable-store probe validates both
identities, the driver, PostgreSQL 17 server, migrations, exact grants, safe
roles, and forced RLS, while runtime-assurance readiness validates every
configured dependency. Network policy is default-deny except cluster DNS and
the exact PostgreSQL CIDR/port; all other ingress/dependency egress is explicit.

## PostgreSQL role, migration, and grant runbook

Run these steps with a DBA-controlled session against the intended empty
database. Role credentials are provisioned by the platform/secret manager and
must not appear in shell history or repository files.

1. Create a non-login owner plus separately authenticated application and
   authority-writer roles:

   ```sql
   CREATE ROLE proof_harness_owner NOLOGIN NOSUPERUSER NOCREATEDB
     NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
   CREATE ROLE proof_harness_app LOGIN NOSUPERUSER NOCREATEDB
     NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
   CREATE ROLE proof_harness_authority_writer LOGIN NOSUPERUSER NOCREATEDB
     NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
   GRANT CREATE ON DATABASE proof_harness TO proof_harness_owner;
   ```

2. In one audited migration session, connect as the exact owner through the
   repository-owned `tools/apply_postgres_migration.py` single-FD applicator,
   then apply the v3.1 delta with `tools/apply_delta_migration.py`. The delta
   applicator refuses an absent or drifted base ledger entry. Both applicators
   reject service roles, verify the PostgreSQL 17 driver, execute pinned bytes
   transactionally, and record detached digests in the migration ledger. Then
   revoke `CREATE` on the database and record the
   database identity outside this repository. Do not use an ad-hoc `psql -f`
   path, because it bypasses the source-byte and owner-role checks.

3. Grant the application only `USAGE` on `proof_harness` and
   `proof_harness_runtime`; `SELECT` on `schema_migrations`; `SELECT, INSERT`
   on append-only/runtime input tables; `SELECT, INSERT, UPDATE` only on
   `runs`, `external_effects`, and `control_plane_receipts`; and `DELETE` only
   on incomplete `control_plane_receipts`. Keep the application read-only for
   Host authority and budget-reservation receipt relations. Grant the
   authority writer only the migration-declared receipt privileges and grant
   `EXECUTE` only on the exact allowlisted helper functions. Neither role may
   receive schema ownership, DDL, `TRUNCATE`, role creation, superuser,
   `BYPASSRLS`, or a path to assume the owner role.

4. Before rollout, query `pg_roles` to prove both login roles have
   `rolsuper=false` and `rolbypassrls=false`, prove their identities differ,
   and run `PostgresStore.readiness()` using both DSNs. Readiness verifies the
   exact relation and helper ACL matrix, including that the application cannot
   forge Host receipts. A failed probe blocks every replica.

The composite artifact version is 3.1.0; its base declarative material remains
version 3.0.0 and its runtime-assurance delta material is version 3.1.0. No
deployment was performed by repository integration. PostgreSQL, artifact
storage, policy decision point, event bus, external verifiers, signatures,
backup/restore, Kubernetes recovery and customer Golden Route evidence remain
`NOT_RUN` until an authorized environment records them.
