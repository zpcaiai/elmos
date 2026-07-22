---
name: polyglot-project-detector
description: Detect Java, Python, C#, JavaScript and TypeScript projects, build systems, frameworks, modules and mixed-language boundaries from an immutable ELMOS snapshot.
---

# Polyglot Project Detector

## Preconditions

Require a valid Repository Snapshot. Do not scan a mutable checkout whose content hash differs from the snapshot.

## Workflow

1. Combine source extensions with build-descriptor and source-root evidence; extensions alone are insufficient.
2. Detect Maven/Gradle modules, Python `src` layouts, `.sln`/`.csproj`, npm/pnpm/yarn workspaces, TypeScript configs, Nx and Turborepo markers.
3. Count production language files and logical lines after excluding generated/vendor/binary/secret-like content.
4. Keep every detected language. Select a primary language by evidence-weighted production LOC, not by repository label.
5. Detect Spring Boot, FastAPI, ASP.NET Core, NestJS and Express from parsed declared dependencies.
6. Emit evidence paths and confidence for each language, framework and project candidate.
7. Treat notebooks as resources unless application-package evidence exists.
8. Mark mixed-language boundaries for Batch 2 semantic analysis.

## Hard boundaries

- Do not collapse a mixed repository to one language.
- Do not claim TypeScript solely because a dependency exists; require TypeScript source/config evidence.
- Do not include generated code in core complexity.
- Unknown or ambiguous values remain `unresolved`.

## Acceptance

The output explains why every language, framework, build system, and module was selected and preserves evidence paths in deterministic order.
