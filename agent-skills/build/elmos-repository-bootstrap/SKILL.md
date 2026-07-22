---
name: elmos-repository-bootstrap
description: Create or refactor the ELMOS Java 21 Maven modular monolith, Spring Boot applications, Next.js console, local dependencies, module boundaries, locked versions, and architecture tests. Use for repository initialization, module creation, build-system changes, or local development setup.
---

# ELMOS Repository Bootstrap

## 适用与禁止

Use only on the ELMOS platform repository. Do not execute migration work against customer code.

## 目标结构

Maintain apps/control-plane, apps/java-engine-worker, apps/web-console, modules/domain, modules/application, modules/workflow, modules/evidence, modules/persistence, modules/security, modules/integrations, contracts, recipes, sandbox, deploy, agent-skills, and docs/adr.

## 依赖规则

- Keep domain free of Spring, persistence, SCM, model-provider, and worker dependencies.
- Let application orchestrate use cases and declare Ports.
- Implement database, engine HTTP, SCM, object storage, and quality adapters outside application.
- Keep control-plane HTTP thin and free of customer command execution.
- Keep java-engine-worker free of control-plane database access.
- Pin every dependency and container tag; require digests for executable sandbox images.
- Append Flyway migrations; never rewrite an applied migration.

## 执行步骤

1. Inspect status, POMs, package manifests, existing source, and ADRs.
2. Protect unrelated changes and choose the smallest valid module.
3. Add code and tests along the allowed dependency direction.
4. Add ArchUnit rules for every new boundary.
5. Update Compose, health checks, and environment examples when runtime topology changes.
6. Run backend unit/architecture/contract tests and frontend type/build checks.
7. Scan for secrets, dynamic versions, TODO templates, and skipped validations.

## 验收与失败处理

Require root Maven verify, web check, valid Compose config, working health endpoints, locked versions, no plaintext production secret, and no forbidden dependency. If Docker is unavailable, mark container-backed tests as skipped with explicit evidence; never claim the container path passed.

