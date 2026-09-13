---
name: "elmos-multilang-project-generation"
description: "Generate complete, buildable projects from a unified Project Specification IR (PSIR) in Java/Spring Boot, Python/FastAPI, TypeScript/NestJS, C#/ASP.NET, and Go/Gin."
---

# ELMOS Multi-Language Project Generation

This skill translates a unified, language-agnostic Project Specification Intermediate Representation (PSIR) into fully functional, idiomatic project scaffolding across multiple languages and frameworks. It ensures that the generated projects are buildable, adhere to framework best practices, and include standard configurations.

## When to Use
- Scaffolding a new microservice based on a standardized architectural template.
- Migrating or replicating a service from one language ecosystem to another.
- Generating boilerplate code, domain models, controllers, and database access layers from an abstract specification.

## Capabilities
- **PSIR Processing:** Parses and validates the Project Specification IR containing domain models, API definitions, configurations, and dependencies.
- **Supported Frameworks:**
  - Java / Spring Boot
  - Python / FastAPI
  - TypeScript / NestJS
  - C# / ASP.NET Core
  - Go / Gin
- **Code Generation:** Outputs complete project contents, including:
  - Directory structure and build files (`pom.xml`, `requirements.txt`, `package.json`, `go.mod`)
  - Domain entities and DTOs
  - API Routes/Controllers
  - Service interfaces and implementations
  - Dockerfiles and CI/CD pipelines
- **Type Mapping:** Accurately maps conceptual data types (e.g., `DateTime`, `UUID`, `Decimal`) to language-specific primitives.
- **Project Verification:** Validates that the generated project compiles and passes basic linter checks.

## Usage
Use the `elmos-project-gen` CLI to interact with the engine.

```bash
elmos-project-gen validate --spec spec.json
elmos-project-gen generate --spec spec.json --lang go --framework gin --output ./new-service
```

## Engine Location
`engines/multilang-project-generation-engine/`

## Integration
Output can be verified using `elmos-cross-language-verification` to ensure that identical PSIR specs yield behaviorally equivalent microservices across different languages.
