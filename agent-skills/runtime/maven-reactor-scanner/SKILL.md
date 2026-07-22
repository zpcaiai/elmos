---
name: maven-reactor-scanner
description: Analyze Maven reactor modules and declared dependency structure for ELMOS health checks. Use for pom.xml, parent/BOM properties, module graphs, plugin baselines, or unresolved Maven evidence.
---
# Maven Reactor Scanner

## Workflow
1. Parse POM XML with DTDs, external entities, XInclude and schema access disabled.
2. Resolve bounded local properties, parent coordinates, modules, dependency management and direct dependencies.
3. Preserve unresolved expressions instead of guessing versions.
4. Require an approved Workspace artifact for effective POM and transitive dependency claims.
5. Emit module paths, coordinates, edges, versions, scopes and descriptor hashes.

## Acceptance
- XXE and malformed POM tests fail closed.
- Duplicate coordinates and conflicting versions are findings.
- Static declarations are not labeled as a complete transitive graph.

