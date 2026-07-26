# Bundled emitter support

The bundled Project Synthesis engine emits eight exact API profiles. The
machine-readable source of truth is `bundled-emitter-support.json`; code,
documentation, UI, and gates must agree with it.

`limited` means a bounded, real-toolchain starter is useful for engineering
work. `experimental` means generation exists but the complete exact
build/startup matrix or independent evidence is incomplete. Neither state is
production certification.

The eight-language emitter does not imply support for every framework,
database, identity provider, cloud, operating system, device, or reverse
migration route. Production persistence, authentication, tenancy, secrets,
observability, recovery, and deployment are separate exact profiles and must
fail closed when their evidence is absent.

The one currently implemented production-oriented tuple is Python 3.12.12,
FastAPI 0.116.1, PostgreSQL 17.5, and either JWT HS256 through an owner-only
Secret file or OIDC through an owner-only JWKS file. Local acceptance runs
real migrations, startup, authorization, CRUD, and PostgreSQL RLS isolation.
External PostgreSQL/IdP operation, production delivery, restore/DR, and
independent certification remain `NOT_RUN` until run in their exact
environments.
