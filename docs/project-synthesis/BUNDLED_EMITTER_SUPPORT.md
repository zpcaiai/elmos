# Bundled emitter support

The bundled Project Synthesis engine emits eight exact API profiles. The
machine-readable source of truth is `bundled-emitter-support.json`; code,
documentation, UI, and gates must agree with it.

`limited` means a bounded, real-toolchain profile is useful for engineering
work and has complete local build/startup/integration evidence for its declared
scope. `experimental` means generation exists but that exact local matrix is
incomplete. Neither state is production certification; independent and
external evidence is required before any certified claim.

All eight profiles currently meet the bounded `limited` definition. Their
replayable 16-case local evidence is
`docs/project-synthesis/local-production-profile-matrix.json`.

The request contract has two explicit generation profiles. `starter-v1`
supports ordinary multi-entity CRUD plus acyclic 1:1, 1:N and N:1 relations.
`relational-v2` additionally lowers M:N relations into a deterministic
association entity, two tenant-scoped foreign keys, pair uniqueness, cascade
cleanup and the normal generated CRUD/OpenAPI surface. The source-bound
16-case matrix replayed this profile for all eight languages and both auth
modes on PostgreSQL 17.5; this is `PASSED_LOCAL`, not external certification.

The eight-language emitter does not imply support for every framework,
database, identity provider, cloud, operating system, device, or reverse
migration route. Production persistence, authentication, tenancy, secrets,
observability, recovery, and deployment are separate exact profiles and must
fail closed when their evidence is absent.

All eight bundled languages implement the exact PostgreSQL 17.5 production
profile with JWT HS256 through an owner-only Secret file or OIDC through an
owner-only JWKS file. `scripts/run_production_matrix.py` runs all 16
language/auth-mode cases with real migrations, startup, authorization, CRUD,
negative token checks, and PostgreSQL RLS tenant isolation. All eight profiles
support the same multi-entity production request contract. External hosted
PostgreSQL/IdP operation, production rootless execution, delivery, restore/DR,
independent user acceptance, and certification remain `NOT_RUN` until run in
their exact environments.

Database support is exact rather than family-wide. PostgreSQL 17.5 is the only
8-language real-engine matrix. MySQL 8.0.41 and SQLite 3.45 are Python-only;
the MySQL real-engine replay is currently `NOT_RUN`. MariaDB, SQL Server,
Oracle, TiDB, OceanBase and DM8 remain version-unselected and
`NOT_IMPLEMENTED`, as recorded in `database-profile-support.json`. AWS RDS,
GCP Cloud SQL and Alibaba Cloud RDS PostgreSQL 17.5 exercises remain
`NOT_RUN` and cannot inherit the local PostgreSQL result.
