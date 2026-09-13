---
name: "elmos-spring-modernization"
description: "Modernize Spring Boot projects through version upgrades (Boot 2→3→4), namespace migration (javax→jakarta), security config modernization, and automated fix-retry loops."
---

# ELMOS Spring Modernization

This skill automates the complex, multi-step process of upgrading legacy Spring applications to modern Spring Boot versions. It provides a structured, rule-based approach to handling breaking changes, deprecated APIs, and ecosystem shifts (such as the javax to jakarta transition).

## When to Use
- Upgrading a Spring Boot 2.x application to 3.x or 4.x.
- Migrating Java EE namespaces (`javax.*`) to Jakarta EE (`jakarta.*`).
- Modernizing deprecated `WebSecurityConfigurerAdapter` configurations to the new component-based SecurityFilterChain.
- Fixing cascading compilation or runtime issues after a major dependency bump.

## Capabilities
- **Project Scanning and Profiling:** Analyzes the `pom.xml` / `build.gradle`, Spring configuration files, and codebase to assess upgrade readiness and complexity.
- **Migration Planning:** 
  - Determines version targets.
  - Performs risk assessment.
  - Generates wave planning for phased migrations.
- **Rules Catalog:** Applies 50+ deterministic migration rules covering common deprecations and structural changes.
- **Rule Application:** Supports dry-run execution to preview changes before applying them to the source tree.
- **Semantic IR Extraction:** Parses the Spring application context into an intermediate representation (bean graph, security chains, transaction boundaries) to safely manipulate configuration.
- **Differential HTTP Oracle:** Verifies that API endpoints behave identically before and after the migration.
- **Repair Agent:** Automated fix-retry loops that parse compiler errors and apply patches iteratively.

## Usage
Use the `elmos-spring-modernize` CLI to orchestrate the upgrade.

```bash
elmos-spring-modernize analyze --target ./legacy-app
elmos-spring-modernize plan --target-version 3.2.0
elmos-spring-modernize apply --dry-run
elmos-spring-modernize repair-loop --max-iterations 5
```

## Engine Location
`engines/spring-modernization-engine/`

## Integration
Often used in conjunction with `elmos-project-structure-analysis` to map out the application boundaries before migration.
