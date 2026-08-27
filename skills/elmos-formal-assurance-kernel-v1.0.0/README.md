# Elmos Formal Assurance Kernel v1.0.0

Commercial production-grade Skills Package for adding formal verification, proof, model checking, translation validation and auditable assurance to every Elmos business line.

## What is included

| Area | Count |
|---|---:|
| Skills | 60 |
| Per-Skill contract files | 300 |
| JSON Schemas / valid examples | 17 / 16 |
| Verifier adapter contracts | 17 |
| Durable workflows | 10 |
| PostgreSQL 17 migrations | 4 |
| Rego modules / tests | 6 / 6 |
| OpenAPI / AsyncAPI contracts | 4 / 1 |
| Golden Routes | 5 |
| Install profiles | 7 |

Each Skill contains exactly:

```text
SKILL.md
manifest.yaml
acceptance.yaml
implementation.yaml
runbook.md
```

See the complete [Skills Index](SKILLS_INDEX.md).

## Business-line coverage

### 1. Spring legacy modernization

Formal coverage for Struts 1, Struts 2, Servlet and mixed legacy repositories migrating to Spring Boot 4:

- route-language coverage, overlap and precedence;
- request binding and validation equivalence;
- Security FilterChain and authorization dominance;
- Filter/Interceptor/AOP order and proxy bypass;
- Session state refinement;
- exception and transaction refinement;
- JML verification of critical Java domain logic;
- source/target observable trace validation;
- ORM/schema/data migration refinement.

### 2. Full-repository cross-language conversion

- versioned language Semantic Profiles;
- executable formal Semantic IR;
- rule-level semantic preservation;
- product-program relational verification;
- integer/null/Unicode/floating/time semantic-gap obligations;
- concurrency/async and effect/exception refinement;
- repository-level Assume–Guarantee composition;
- reflection/FFI proof boundaries;
- proof-carrying conversion bundles.

### 3. Multi-language project generation

- requirements → Data/API/Workflow/Security/Resource specifications;
- architecture constraints;
- TLA+/state-machine workflow safety and liveness;
- tenant noninterference;
- verified core / tested shell generation;
- API and data invariant verification;
- termination and token/credit resource bounds.

### 4. SQL dialect and SQL Routine conversion

- Bag/Set/order, NULL and three-valued logic Semantic IR;
- query equivalence;
- lossless schema mapping;
- DDL constraint preservation;
- DML state equivalence;
- Routine CFG/SSA contracts;
- Trigger trace and termination;
- precision/collation/time semantics;
- dynamic SQL proof boundary;
- transaction, isolation and exception refinement.

### 5. Elmos platform assurance

- task concurrency `<= 3` per account;
- pause/resume/cancel/recovery safety;
- lease ownership and fencing;
- credit reservation, consumption and refund conservation;
- immutable evidence;
- anti-status-inflation release gates;
- Counterexample-to-Test;
- drift invalidation, waivers, reports and SLOs.

## Canonical result semantics

The kernel never collapses results into a misleading boolean. Canonical statuses include:

```text
PROVED_CERTIFIED
PROVED_INDUCTIVE
PROVED_SOLVER_TRUSTED
PROVED_FOR_SUPPORTED_FRAGMENT
BOUNDED_NO_COUNTEREXAMPLE
REFUTED_WITH_COUNTEREXAMPLE
UNKNOWN_TIMEOUT
UNKNOWN_RESOURCE_LIMIT
UNSUPPORTED
ASSUMPTION_REQUIRED
RUNTIME_MONITORED
WAIVED_BY_APPROVER
```

`BOUNDED_NO_COUNTEREXAMPLE` is never displayed or gated as an unbounded proof.

## Verifier portfolio

The package contains fail-closed adapter contracts for:

```text
Z3, cvc5, Lean 4, Boogie, Dafny, TLC, Apalache, Alloy,
OpenJML, KeY, Java PathFinder, K Framework, Alive2,
SQLSolver, VeriEQL, Kani, Frama-C
```

Third-party tools are **not bundled**. Production enablement requires exact version/image digest, license review, SBOM, signature/provenance, sandbox validation and conformance fixtures.

## Directory structure

```text
elmos-formal-assurance-kernel-v1.0.0/
├── PACKAGE_MANIFEST.yaml
├── SKILLS_INDEX.md
├── skills/P0|P1|P2/
├── contracts/
│   ├── schemas/
│   ├── examples/
│   ├── openapi/
│   └── events/
├── workflows/
├── policies/rego/
├── verifier-adapters/
├── db/migration/
├── reference-kernel/
├── examples/
├── golden-routes/
├── profiles/
├── docs/
├── deploy/
└── scripts/
```

## Validate

```bash
cd elmos-formal-assurance-kernel-v1.0.0
python3 -m pip install -r requirements-dev.txt
python3 scripts/generate_catalog.py
python3 scripts/validate_package.py
PYTHONPATH=reference-kernel python3 -m unittest discover -s reference-kernel/tests -v
python3 scripts/run_reference_kernel_demo.py
```

## Install into Elmos

No-overwrite by default:

```bash
./scripts/install.sh /path/to/elmos --profile full
```

Available profiles:

```text
core
spring
cross-language
project-generation
sql
platform
full
```

Dry run and forced backup/replace:

```bash
./scripts/install.sh /path/to/elmos --profile spring --dry-run
./scripts/install.sh /path/to/elmos --profile spring --force
```

Hash-aware uninstall:

```bash
./scripts/uninstall.sh /path/to/elmos
```

Files modified after installation are preserved.

## Release process

1. Replace every release-time image/tool placeholder with exact signed digests.
2. Apply and test PostgreSQL migrations.
3. Execute OPA tests.
4. Run every enabled verifier adapter conformance suite.
5. Build SBOM, scan, sign and attest images.
6. Deploy and pass `/livez`, `/readyz`, `/metrics`, `/version`.
7. Complete P05.
8. Complete E1–E5 for the selected Golden Route.
9. Generate a signed evidence bundle and release report.

Read [Release Gates](docs/RELEASE_GATES.md), [Commercial Certification](docs/COMMERCIAL_CERTIFICATION.md), [Toolchain Policy](docs/TOOLCHAIN.md), and [Honest Limitations](docs/LIMITATIONS.md).

## Honest boundary

This artifact is a commercial-grade implementation specification package plus executable reference kernel. Package validation does not mean the capabilities are already integrated into Elmos, external proof tools have run, PostgreSQL/OPA/Kubernetes have been validated, or customer Golden Routes have passed. Those claims require target-environment evidence through P05 and E1–E5.
