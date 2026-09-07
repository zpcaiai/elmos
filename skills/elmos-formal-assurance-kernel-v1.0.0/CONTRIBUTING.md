# Contributing

Every new or changed Skill must update all five Skill files, schemas/examples where applicable, tests, documentation and release counts.

## Required for a new verifier adapter

- exact supported logic/feature profile;
- conservative status mapping;
- malformed/timeout/crash/resource fixtures;
- sandbox controls;
- license review flag;
- TCB and release-pin integration;
- an independent result-parser review.

## Required for a new proof status or assurance level

Changing status semantics is a breaking contract change. Update schemas, database enum/migration, Rego, reference kernel, UI/reporting policy, API, evidence format and replay tests.

## Pull-request gates

```bash
python3 scripts/generate_catalog.py
python3 scripts/validate_package.py
PYTHONPATH=reference-kernel python3 -m unittest discover -s reference-kernel/tests -v
python3 scripts/check_release_pins.py
```

Production releases additionally require strict release pins, PostgreSQL/OPA/external verifier tests, SBOM/signatures, P05 and applicable E1–E5 Golden Route evidence.
