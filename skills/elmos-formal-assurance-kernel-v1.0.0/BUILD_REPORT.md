# Build and Validation Report

Package: `elmos-formal-assurance-kernel-v1.0.0`  
Version: `1.0.0`  
Release date: `2026-08-27`  
Status: **PASS WITH RELEASE-TIME TOOLCHAIN PINS AND TARGET-ENVIRONMENT CERTIFICATION REQUIRED**

## Coverage

| Item | Count |
|---|---:|
| Skills | 60 |
| P0 / P1 / P2 | 48 / 10 / 2 |
| Per-Skill contract files | 300 |
| JSON Schemas / schema-valid examples | 17 / 16 |
| Verifier adapter contracts | 17 |
| Durable workflows | 10 |
| PostgreSQL migrations | 4 |
| Rego modules / tests | 6 / 6 |
| OpenAPI / AsyncAPI contracts | 4 / 1 |
| Golden Routes | 5 |
| Install profiles | 7 |
| Reference-kernel unit tests | 40 |
| Documentation files at validation time | 182+ |

## Executed and passed

- Package/YAML/JSON/Skill/dependency/required-section validation.
- Helm template contract presence checks.
- JSON Schema Draft 2020-12 meta-validation.
- Sixteen examples validated against their matching schemas.
- Verifier adapter contracts validated against the adapter schema.
- Workflow and Skill DAG cycle/reference checks.
- Generated catalog consistency.
- PostgreSQL migration static invariants: RLS, immutable artifacts, status guards and fencing.
- Rego policy contract presence and anti-status-inflation assertions.
- Python compile.
- Reference-kernel tests: **40/40 passed**.
- Reference gate demo: solver-proved A2 → `ALLOW`; bounded A1 for A2 requirement → `DENY`.
- Installer/uninstaller round trip: no-overwrite manifest and hash-aware removal passed.
- Local Markdown links: zero broken.
- JML example compiled successfully as ordinary Java with `javac`; JML proof was not executed.

## Release-time placeholders

The package intentionally contains one base-image placeholder and seventeen external verifier image placeholders. They prevent an unearned claim that approved production images already exist. Before production, replace them with exact signed digests and run `python3 scripts/check_release_pins.py --strict`.

## Checks not executed in this build environment

The environment did not provide OPA, Helm, Kubernetes, PostgreSQL client/server, Docker/Podman or the declared formal verifiers. Therefore this build does **not** claim:

- OPA compilation or Rego test execution;
- application of migrations to live PostgreSQL 17;
- Helm rendering/server-side Kubernetes validation or NetworkPolicy enforcement;
- image build, SBOM, vulnerability scan, signature or provenance;
- TLA+, Alloy, SMT, JML, Dafny, Lean, Boogie, K, Alive2, SQLSolver, VeriEQL, Kani or Frama-C execution;
- real source/target runtime differential validation;
- E1–E5 customer Golden Route certification;
- large-repository commercial certification.

## Product completeness statement

This is a **commercial-grade implementation specification package plus executable reference kernel**. It is ready to merge as a structured implementation backlog and contract layer. Production completion still requires wiring ports to Elmos services, pinning and certifying enabled verifiers, applying database/policy/deployment artifacts in the target environment, and passing P05 plus the selected E1–E5 Golden Route.
