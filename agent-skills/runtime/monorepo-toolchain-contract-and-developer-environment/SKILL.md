---
name: monorepo-toolchain-contract-and-developer-environment
description: "建立ELMOS参考实现Monorepo、版本锁、统一命令、本地环境和CI基线。"
---

# Requirements

- Gradle Multi-project；
- pnpm Workspace；
- Go Workspace；
- Docker Compose；
- 根目录统一命令；
- 全部依赖锁定；
- 全部OCI镜像绑定Digest。

## Local Development

make bootstrap
make compose-up
make migrate
make test
make e2e

## CI Stages

Validate Contracts
→ Java Check
→ Web Check
→ Go Check
→ Database Migration Test
→ Integration Test
→ Security Scan
→ Image Build
→ Provenance

## 验收标准

- 新开发者一天内启动本地环境；
- CI和本地使用相同命令；
- 依赖版本集中管理；
- 无浮动生产依赖；
- 数据库Migration可从零执行；
- Monorepo模块依赖无环。
