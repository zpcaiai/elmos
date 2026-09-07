# Large repository database design integration

This integration preserves `elmos-large-repository-database-design-v1.0.0`
as an immutable, standalone PostgreSQL reference package. It does not silently
merge the attached SQL into the repository's authoritative Flyway history or
wire a second tenant authority into application persistence.

## Immutable source and installed Skill

| Property | Value |
|---|---|
| Trusted archive | `skills/subskills/elmos-large-repository-database-design-v1.0.0.zip` |
| Archive SHA-256 | `624de461a0a7a3a295b6c3ebcd1ffd6e3a45f80bdf33aad0d7e3cb0d8c430e88` |
| Canonical extracted source | `skills/elmos-large-repository-database-design-v1.0.0/` |
| Installed Skill | `large-repository-run-persistence` |
| Installed roots | `.agents/skills/` and `agent-skills/runtime/` |
| PostgreSQL scope exercised by CI | exact `postgres:16.9` and `postgres:17.5` service tags |

The importer validates the pinned archive and its internal checksums before it
publishes the canonical source and byte-bound installed Skill. Package Markdown,
SQL, Python, Docker, and workflow files are treated as source payloads. The
importer does not execute them, and the extracted source remains byte-identical
to the archive rather than being repaired in place.

Invoke `$large-repository-run-persistence` for design, implementation, review,
or operation work inside this package's exact PostgreSQL persistence scope. A
directional migration or support-status decision must additionally use the
narrowest applicable `$b31-*` Skill and the conservative Batch 31 gate. Merely
invoking or installing the Skill does not run SQL and does not certify a route.

## Repository commands

Write or refresh the immutable integration, then perform its read-only check:

```bash
python3 tooling/integrate_large_repository_database_design.py --write
python3 tooling/integrate_large_repository_database_design.py --check
```

Run the focused integration test and the immutable source's static validator:

```bash
python3 -m unittest discover \
  -s tests/large-repository-database-design \
  -p 'test_integration.py'
python3 skills/elmos-large-repository-database-design-v1.0.0/scripts/validate_database_design.py
```

The repository target combines the bounded integration checks:

```bash
make large-repository-database-design-skills
```

Real PostgreSQL validation is deliberately opt-in and destructive cleanup is
not part of the runner. Supply a newly created, disposable database using an
administrator able to install extensions and create the package's `NOLOGIN`
roles:

```bash
ELMOS_LARGE_REPOSITORY_DB_DISPOSABLE_CONFIRMED=true \
ELMOS_LARGE_REPOSITORY_DB_URL='postgresql://user:password@127.0.0.1:5432/disposable_db' \
bash scripts/large_repository_database_design/run_postgres_validation.sh
```

The runner refuses any confirmation other than the exact string `true`,
requires the database URL and `psql`, accepts only PostgreSQL major 16 or 17,
and fails if a canonical package schema already exists. It applies the exact 11
canonical migrations in sorted order with `--no-psqlrc` and
`ON_ERROR_STOP=1`, then executes role hardening, the package role check, all SQL
invariants, and exact schema, 136-parent-table, 31-function, and eight-view
inventory assertions. It also runs a rollback-only transactional fixture for
three-slot admission, stale fencing, append-only event chains, unresolved
side-effect P05 rejection, and two-tenant RLS. These scenarios prove bounded
behavior on one connection; they are not a substitute for concurrent-worker,
failover, restore, or representative-load evidence. The runner never cleans or
drops the database.

## Why the bundled workflow is not used

The immutable package's `.github/workflows/database-ci.yml` is retained as
source evidence, not copied into the repository workflow namespace or called by
CI. It references `scripts/validate_bundle.py`, `deploy/helm/elmos/**`, and
`deploy/local/docker-compose.yml`, none of which exists in the archive. The
validation report nevertheless claims Helm, Compose, and bundle validation.
The source workflow also uses broad PostgreSQL/Flyway tags and unpinned actions.

The repository-owned
`.github/workflows/large-repository-database-design.yml` instead runs the
importer check, focused unittest, source static validator, and isolated database
runner. Action revisions are commit-pinned. PostgreSQL uses exact version tags,
but those tags are not immutable image digests, so the resolved image identity
remains run-scoped engineering evidence rather than certification evidence. Raw
runner logs and a run-scoped status file are retained even on failure; the
status file continues to report external evidence as `NOT_RUN` and
certification as `NOT_CERTIFIED`.

## Integration blockers and collision boundary

### Flyway version collision

The package owns `V001`, `V010`, `V020`, `V030`, `V040`, `V045`, `V050`,
`V060`, `V070`, `V080`, and `V090`. Flyway normalizes leading zeroes, so at
least package versions 1, 10, 20, 30, 40, 45, 50, and 60 collide with the
authoritative migrations already present under
`modules/persistence/src/main/resources/db/migration/`. Versions 70, 80, and 90
would also reserve unrelated positions in that same global ledger.

Consequently, these files must not be copied into `modules/persistence` or run
against its Flyway schema history. Current CI exercises them only as a parallel
standalone migration line in a new disposable database. Production adoption
requires an explicit re-versioned expand/contract plan, prior-version upgrade
tests, rollback/restore evidence, and an approved ownership decision.

### Parallel tenant identities

The package creates `core.tenant(id uuid)` and scopes RLS through
`app.tenant_id`. The existing application and persistence modules treat
`public.organizations(organization_id varchar)` and transaction-local
`app.organization_id` as authoritative. Those identities are not equivalent,
and neither a cast nor an undocumented dual write is an acceptable mapping.

Until an identity owner approves one authority and a durable mapping/backfill
contract, `core.tenant` remains isolated reference data. No application module
may infer a tenant UUID from an organization string, accept caller-supplied
tenant context, or make both tables independently authoritative.

### Extension relocation and privileged function owner

`V001` installs `pgcrypto`, `citext`, and `pg_trgm` into an `extensions` schema
and relocates an existing copy with `ALTER EXTENSION ... SET SCHEMA`. On a
shared database that can change qualified object names and `search_path`
behavior for existing consumers. It requires dependency inventory, rehearsed
upgrade/rollback, and database-owner approval before use outside the isolated
matrix.

The role hardening file also creates a `NOLOGIN BYPASSRLS`
`elmos_runtime_definer` and transfers vetted `SECURITY DEFINER` functions to it.
That design is materially different from the repository's normal
`NOBYPASSRLS` runtime-role posture. The isolated check proves the declared owner
and ACL shape only. Production use requires a database-security review of exact
function bodies and digests, fixed `search_path`, grants, membership, audit,
and revocation; the definer role must never be granted to a login role.

## Package metadata drift

The archive name, root README, package manifest, and Skill metadata identify
version `1.0.0`. `VALIDATION-REPORT.md` calls the delivery `v1.1.0`, and the
static validator also embeds `v1.1.0` in one count error. The importer preserves
that contradiction as source truth and continues to identify this archive only
as `1.0.0`. A corrected upstream archive with a new digest is required before
claiming a `1.1.0` package.

## Evidence and application boundary

### PostgreSQL 16/17 compatibility overlay

Real PostgreSQL 17.5 execution exposed a source migration defect that the
package's static validator does not detect. `V020` partitions `exec.run_event`
by `run_id` and `exec.session_event` by `session_id`, but both also declare
`UNIQUE (tenant_id, event_id)`. PostgreSQL 16/17 reject those definitions
because every unique key on a partitioned table must contain its partition
column.

The immutable package remains unchanged. The isolated validation runner invokes
`render_runtime_migrations.py`, which verifies the pinned checksum manifest and
V020 digest, requires each exact defect anchor once, and produces a temporary
copy with both event tables partitioned by `tenant_id`. This preserves the
declared tenant-scoped event-ID uniqueness instead of weakening or removing it;
all other migration bytes remain exact. The repaired V020 output digest is
`sha256:4cc21c57b6fe81039b752669fb1d9246f68f4e06568f07104db8f92c1f0dd139`.

That overlay is bounded PostgreSQL 16/17 engineering evidence only. It changes
the source package's documented run/session partition-placement strategy, so it
is not an approved production migration. Upstream must publish a corrected,
versioned migration and choose the production partition/uniqueness contract
before application integration or deployment.

Checked-in archive identity, checksum verification, static validation, file
equality, and focused tests are engineering evidence. Before an exact workflow
run, PostgreSQL 16.9 and 17.5 execution remain `NOT_RUN`; a successful matrix
job records only run-scoped engine execution. Provider, production, upgrade,
rollback, recovery, true concurrent-worker races, representative-workload,
security-review, and independent external evidence remain `NOT_RUN`.
Certification remains
`NOT_CERTIFIED`.

The package is therefore not wired into `modules/persistence` or any Java
application store. Besides the migration and identity collisions, it supplies
no reconciled application adapter, no authoritative organization mapping, no
safe shared-database extension plan, no accepted `BYPASSRLS` review, no
previous-schema upgrade route, and no Helm or Compose deployment assets.
Installing a reference Skill and validating its isolated SQL do not authorize
those production changes.
