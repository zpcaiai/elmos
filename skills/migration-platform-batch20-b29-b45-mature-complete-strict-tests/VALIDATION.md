# Validation report

Validation performed on 2026-07-21.

## Passed

- Go runner: `gofmt`, `go vet ./...`, `go test ./...`
- Python agent service: isolated virtual environment install, `ruff check`, `pytest` (2 tests)
- Next.js console: deterministic `npm ci`, production `next build`, TypeScript check, `npm audit --omit=dev` with 0 findings
- Java Maven engine: Java 21 `javac` compilation, execution against `samples/java-sample`, valid PSP JSON output
- Java control-plane source: all Java files parsed successfully with a Java grammar parser
- Gradle Kotlin DSL: all `.gradle.kts` files parsed successfully with a Kotlin grammar parser
- Contracts: OpenAPI 3.1 validation, JSON Schema meta-validation, AsyncAPI/YAML syntax validation
- Configuration: Docker Compose and Spring YAML syntax validation
- Maven POMs: XML parse validation
- Shell scripts: `bash -n`

## Environment limitations

The execution environment did not include Docker, Gradle, or Maven binaries. Therefore:

- the Spring Boot Gradle dependency build was not executed locally;
- the Maven lifecycle build was not executed locally, although the Maven engine's Java sources were compiled and run directly with Java 21;
- the complete Docker Compose stack was not started in this environment.

The repository includes pinned Docker build images and CI jobs for these remaining builds. Run `docker compose up --build` on a Docker host to validate the complete end-to-end stack.

## Codex Skill package regressions through Batch 37

- Batch 29–37 toolkits passed 52/52 tests.
- The repository contains 184 Codex skills.
- Batch 37 validates extension manifests, sandbox policy, publisher/release contracts, commercial policy, conservative certification, and negative privilege/network cases.
- These results validate the implementation packages and gates, not production certification of external extensions or marketplace infrastructure.
