# Deployment boundary

The image and Helm assets are production-shaped but intentionally unpinned in
source control. A release pipeline must supply an approved base-image digest,
the built image digest, SBOM, signature, provenance, database migration
receipt, and exact release-manifest digest. Placeholder tags and mutable image
references are rejected by policy.

Example build shape (values are supplied by the release system):

```bash
docker build -f deploy/Dockerfile \
  --build-arg PYTHON_BASE="registry.example/python@sha256:<approved>" \
  --build-arg SOURCE_REVISION="<git-sha>" \
  --build-arg RELEASE_MANIFEST_SHA256="sha256:<manifest>" \
  --tag "registry.example/elmos/proof-harness:<version>" .
```

The chart requires `image.repository`, `image.digest`,
`config.existingSecret`, and a separate `postgresql.existingSecret`. The latter
must contain the DSN under `postgresql.dsnKey`; the chart never creates a
database, embeds a password, or falls back to a pod-local SQLite file. The two
default replicas therefore share one externally managed PostgreSQL service.
Startup/readiness call `/readyz`, whose durable-store probe must validate the
driver, connection, PostgreSQL 17 server, migration, safe role, and forced RLS.
Network policy is default-deny except cluster DNS and the exact PostgreSQL
CIDR/port; all other ingress/dependency egress is explicit.

## PostgreSQL role, migration, and grant runbook

Run these steps with a DBA-controlled session against the intended empty
database. Role credentials are provisioned by the platform/secret manager and
must not appear in shell history or repository files.

1. Create a non-login owner and a separately authenticated application role:

   ```sql
   CREATE ROLE proof_harness_owner NOLOGIN NOSUPERUSER NOCREATEDB
     NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
   CREATE ROLE proof_harness_app LOGIN NOSUPERUSER NOCREATEDB
     NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
   GRANT CREATE ON DATABASE proof_harness TO proof_harness_owner;
   ```

2. In one audited migration session, connect as the exact owner through the
   repository-owned `tools/apply_postgres_migration.py` single-FD applicator.
   It rejects service roles, verifies the PostgreSQL 17 driver, executes the
   pinned bytes transactionally, and records the detached digest in the
   migration ledger. Then revoke `CREATE` on the database and record the
   database identity outside this repository. Do not use an ad-hoc `psql -f`
   path, because it bypasses the source-byte and owner-role checks.

3. Grant the application only `USAGE` on `proof_harness` and
   `proof_harness_runtime`; `SELECT` on `schema_migrations`; `SELECT, INSERT`
   on append-only/runtime input tables; `SELECT, INSERT, UPDATE` only on
   `runs`, `external_effects`, and `control_plane_receipts`; and `DELETE` only
   on incomplete `control_plane_receipts`. Grant `EXECUTE` only on
   `current_tenant_key()` and `current_project_key()`. Do not grant schema
   ownership, DDL, `TRUNCATE`, role creation, superuser, or `BYPASSRLS`.

4. Before rollout, query `pg_roles` to prove both `rolsuper=false` and
   `rolbypassrls=false`, and run `PostgresStore.readiness()` using the
   application DSN. A failed probe blocks every replica.

No deployment was performed by repository integration. PostgreSQL, artifact
storage, policy decision point, event bus, external verifiers, signatures,
backup/restore, Kubernetes recovery and customer Golden Route evidence remain
`NOT_RUN` until an authorized environment records them.
