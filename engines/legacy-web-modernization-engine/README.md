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
```
