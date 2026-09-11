---
name: "elmos-project-structure-analysis"
description: "Analyze project architecture patterns, technology stacks, technical debt hotspots, code ownership, API surfaces, and dependency inventories."
---

# ELMOS Project Structure Analysis

This skill provides deep static and dynamic analysis of a codebase to extract meaningful structural insights. It powers architectural understanding, security assessments, and modernization planning by transforming raw source code into structured knowledge graphs.

## When to Use
- Discovering the architecture and patterns used in a legacy or undocumented codebase.
- Identifying technical debt, dead code, and high-complexity hotspots.
- Mapping out the API surface area and external system dependencies.
- Generating an inventory of third-party libraries and frameworks for a Software Bill of Materials (SBOM).
- Determining code ownership boundaries based on commit history and directory structures.

## Capabilities
- **Architecture Pattern Detection:** Identifies MVC, Hexagonal, Microkernel, and Event-Driven architectures.
- **Tech Stack Identification:** Detects languages, build systems, frameworks, and databases in use.
- **Tech Debt Heatmaps:** Correlates cyclomatic complexity, churn rate, and test coverage to highlight areas needing refactoring.
- **Ownership Analysis:** Maps code modules to specific teams or developers.
- **API Surface Extraction:** Catalogs REST, GraphQL, gRPC, and message queues exposed by the system.
- **SBOM Generation:** Produces a standardized Software Bill of Materials.
- **Dependency Inventory:** Tracks internal module coupling and external library usage.

## Usage
Analysis is typically triggered via the teaching subsystem or project intelligence engines.

```bash
elmos-teaching analyze tech-stack --target .
elmos-teaching analyze debt --output heatmap.json
elmos-teaching analyze api --format openapi
```

## Engine Location
`engines/project-intelligence-engine/` and `engines/teaching-subsystem-engine/`

## Integration
Serves as the foundational data provider for `elmos-diagram-generation`, `elmos-guided-project-tour`, and `elmos-spring-modernization`.
