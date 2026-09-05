# Bundled emitter support

The bundled Project Synthesis engine emits eight exact API profiles. The
machine-readable source of truth is `bundled-emitter-support.json`; code,
documentation, UI, and gates must agree with it.

The first-release boundary is frozen separately in
`p0-launch-scope-v1.json`: `project_kind=api`, eight request-runtime selectors
and their exact qualification toolchain tuples, the disposable local PostgreSQL
17.5 profile, and JWT HS256
or OIDC RS256 with owner-only file inputs. PostgreSQL 17.5 is not a managed
provider claim. A managed service version (including a separately observed
17.11 server) must be recorded in its own digest-bound provider receipt and
cannot substitute for the 17.5 local-runtime evidence. Managed-provider
migration writes and production qualification remain `NOT_RUN` here. The
separate 2026-09-04 operator report has no raw provider receipt: Neon reported
17.11 and Better Auth exposed one `OKP`/`EdDSA` JWK. That is an explicit
`ALGORITHM_MISMATCH` against the frozen `RSA`/`RS256` OIDC contract and blocks
that managed OIDC profile. It does not block the independent local JWT HS256
profile.

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

All eight bundled languages implement the exact local PostgreSQL 17.5 production
profile with JWT HS256 through an owner-only Secret file or OIDC through an
owner-only JWKS file. `scripts/run_production_matrix.py` runs all 16
language/auth-mode cases with real migrations, startup, authorization, CRUD,
negative token checks, and PostgreSQL RLS tenant isolation. Java, Python, C#,
TypeScript, Go, Kotlin, PHP, and Rust now all accept multi-entity production
requests. The committed July local matrix ran multi-entity cases only for Java
and Python and single-entity cases for the other six; it remains valid for the
cases it actually ran, but it is not current-SHA multi-entity evidence for those
six targets. A fresh receipt must retain `NOT_RUN` until replayed.

Every generated workspace now contains a CycloneDX 1.6 dependency SBOM and a
Generation Manifest binding for its digest and P0 scope. The initial SBOM keeps
transitive-inventory and artifact-integrity status separate and says
`INCOMPLETE` wherever native lock or hash evidence is absent. Its dependency
edges are explicitly `INCOMPLETE_FLATTENED`, never a complete-graph claim.
After a native build, `collect-native-artifact-hashes` hashes actual
Maven/Gradle cache artifacts into request-bound local evidence.
`elmos-project-synthesis supply-chain` then rescans the workspace and emits an
unsigned Release Manifest. Release remains blocked unless the inventory and
artifact-integrity inputs are complete, native verification is bound to the exact Generation
Manifest, the source commit/tree is clean and exact, and an Ed25519 signature
verifies against an explicit active trust root. Signature success can yield at
most `READY_FOR_EXTERNAL_GATE`; it never certifies or deploys.

External PostgreSQL/IdP operation, production
rootless execution, delivery, restore/DR, independent user acceptance, and
certification remain `NOT_RUN` until run in their exact environments.
