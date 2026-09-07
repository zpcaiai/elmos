---
name: gradle-project-scanner
description: Inventory Gradle multi-project metadata without evaluating untrusted build logic. Use for settings.gradle, build.gradle, Kotlin DSL, toolchains, dependency declarations, or Gradle health evidence.
---
# Gradle Project Scanner

## Workflow
1. Read settings, build and gradle.properties files as bounded text.
2. Inventory declared projects, plugins, repositories, dependencies and Java compatibility hints.
3. Do not run Gradle during static discovery.
4. Attach approved Gradle model/build artifacts separately when execution is authorized.
5. Mark dynamic DSL, custom plugins and unresolved providers `INCONCLUSIVE`.

## Acceptance
- Script content cannot execute in the scanner.
- Mixed Maven/Gradle roots remain explicit.
- Every conclusion cites a file digest or build artifact.

