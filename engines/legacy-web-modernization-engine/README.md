# ELMOS Legacy Web Modernization Engine

This repository-owned engine binds all 55 exact Skills from
`elmos.java-legacy-web.repository-modernization` v1.0.0 to deterministic,
bounded handlers. It statically recovers Struts 1/2, Servlet/JSP, build,
route, state, security, transaction, dependency, and effect facts from a
symlink-safe immutable snapshot, projects them into the package's semantic
contracts, generates staged IR-driven target candidates, and evaluates caller-
supplied observations with strict differential oracles.

The local runtime never executes repository content, Maven/Gradle plugins,
source-package scripts, browser/device code, production databases, providers,
Git, deployment, or cutover. It persists tenant/project/job-scoped state in
SQLite and content-addressed artifacts locally. Unknowns, missing authority,
missing runtime evidence, and critical mismatches fail closed. Local results
are engineering evidence only; external evidence remains `NOT_RUN` and
certification remains `NOT_CERTIFIED`.

Useful commands from the repository root:

```sh
make legacy-web-modernization-skills
PYTHONPATH=engines/legacy-web-modernization-engine/src python3 -m elmos_legacy_web_modernization.cli validate

# When separately authorized evidence exists, verify it without promoting
# local state or issuing production certification:
PYTHONPATH=engines/legacy-web-modernization-engine/src python3 -m elmos_legacy_web_modernization.cli external-preflight \
  --intake /approved/evidence/legacy-web-intake.json \
  --expected-binding /approved/evidence/legacy-web-binding.json \
  --evidence-root /approved/evidence \
  --trust-store /approved/evidence/trust-store.json
```

The preflight requires content-addressed evidence and dedicated Ed25519 trust
keys for every source/target build and runtime, behavioral, security,
performance, operability, SBOM, rollback, independent-review, customer-
acceptance, and external-certification role. A valid intake is reported as
`READY_FOR_EXTERNAL_GATE_REVIEW`; this engine never changes the package state
and never emits `CERTIFIED`. Until such an intake is supplied, the explicit
state remains `NOT_RUN` / `NOT_CERTIFIED`.
