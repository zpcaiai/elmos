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

The eight-language emitter does not imply support for every framework,
database, identity provider, cloud, operating system, device, or reverse
migration route. Production persistence, authentication, tenancy, secrets,
observability, recovery, and deployment are separate exact profiles and must
fail closed when their evidence is absent.

All eight bundled languages implement the exact PostgreSQL 17.5 production
profile with JWT HS256 through an owner-only Secret file or OIDC through an
owner-only JWKS file. `scripts/run_production_matrix.py` runs all 16
language/auth-mode cases with real migrations, startup, authorization, CRUD,
negative token checks, and PostgreSQL RLS tenant isolation. Java and Python
support multi-entity production requests; the other six targets enforce an
explicit single-entity boundary. External PostgreSQL/IdP operation, production
rootless execution, delivery, restore/DR, independent user acceptance, and
certification remain `NOT_RUN` until run in their exact environments.
