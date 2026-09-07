---
name: build-manifest-inspector
description: Parse Maven, Gradle, Python, NuGet and npm-family build metadata into the ELMOS language-neutral Build Model without executing repository code.
---

# Build Manifest Inspector

## Workflow

1. Parse Maven and MSBuild XML with DTD/external-entity access disabled.
2. Parse `package.json` as JSON and preserve runtime/dev/peer/optional scopes.
3. Parse `pyproject.toml` as TOML and preserve PEP 621 dependencies, extras and Poetry metadata.
4. Parse central NuGet package versions from `Directory.Packages.props`.
5. Recognize Gradle roots/composite builds but never evaluate Groovy/Kotlin DSL during intake; require an approved Tooling API export for unresolved values.
6. Treat `setup.py` as executable input; never import it. Prefer PEP 621 or resolve it in the sandbox.
7. Record source/test/resource/generated roots, direct dependencies, plugins, repositories, compiler options and commands as argv arrays.
8. Mark private sources, network requirements, lifecycle/code-execution risk and unresolved inheritance.

## Hard boundaries

- Do not replace a real format parser with regular-expression-only extraction.
- Do not run Gradle, Maven, npm, pip, Poetry, uv, dotnet, or project code here.
- Never guess inherited, computed, central, dynamic, or environment-derived versions.
- Commands are plans; only `baseline-build-test` may execute them in an approved sandbox.

## Acceptance

Each project has deterministic source roots and a dependency record with ecosystem, name, version, scope, source, directness and resolution status. Opaque values are explicit `unresolved` entries.
