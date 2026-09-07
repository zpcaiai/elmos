# Batch 18：Complete Project Generation Standard

## 总体目标

保证输出不是代码片段或半成品，而是具备源码、构建、配置、依赖、数据、消息、部署、验证、安全、运维、文档和回滚闭包的真实可交付项目。

## 建议仓库结构

```text
complete-project-ir/
template-registry/
project-generators/
build-generators/
infrastructure-generators/
deployment-generators/
validation-generators/
operations-generators/
documentation-generators/
completeness-engine/
```

## 1. Complete Project Manifest

- Repositories、Modules、Services、Libraries、CLI、Workers、Jobs、Data、Messaging、API、Deployment、Config、Tests、Operations、Docs
- Source Traceability、Assumptions、Risks、Owners、Artifacts、Certificates
## 2. Template Registry 与 10-language Generators

- Repository/Language/Framework/Domain/Infrastructure/Deployment/Validation/Documentation Templates
- Java、Python、C#、Rust、Go、TypeScript、Node、C++、Objective-C、Swift 完整项目生成
## 3. Build/Dependency/Config Closure

- Toolchain Bootstrap、Clean/Reproducible/Offline Build
- Lockfiles、SBOM、License、Native Assets、Private Registry
- Typed Config、Safe Defaults、Secret References、Drift Detection
## 4. Infrastructure 与 Deployment

- Database Schema/Migrations/Seed/Backup/Restore/Reconciliation
- Messaging Producer/Consumer/Schema/Retry/DLQ/Outbox/Inbox
- Cache/Search/Object、API/Gateway/Mesh、Docker/K8s/Serverless/Edge/Air-gapped
## 5. Validation/Operations/Docs

- CI/CD、Unit/Integration/Contract/Journey/E2E
- Fuzz、Mutation、Fault、Performance、Security、Formal Projects
- Observability、SLO、Alerts、Runbooks、Security/Operations/Migration Documentation
## 6. One-click 与 Completeness

- project doctor/bootstrap/build/start/test/fuzz/mutate/prove/deploy/rollback/restore/verify
- Functional/Build/Dependency/Config/Data/Deployment/Security/Operations/Docs/Evidence Completeness Score
- Clean Environment Full Lifecycle Acceptance

## 认证体系：CP1–CP5 Complete Project

CP1–CP5 Complete Project 必须绑定精确 Scope、Artifact Hash、环境、版本、Assumptions、Evidence 与有效期。证书必须支持 Expiry、Downgrade、Suspension、Revocation 和 Independent Renewal。

## 主要输出

- Complete Project Manifest
- Complete Repositories
- Build/Lock/SBOM/Config Assets
- Database/Messaging/API/Gateway/Mesh/Deployment
- CI/CD and Validation Projects
- Observability/Security/Runbooks/Docs
- One-click Lifecycle
- Completeness Score
- Delivery Bundle
- CP1–CP5 Certificates

## 硬性原则

- Repository 可以 Build 不代表项目可运行
- 本地可运行不代表生产可部署
- Backup 成功不代表可 Restore
- Rollback 不能只恢复应用镜像
- 文档示例必须实际执行
- Completeness 高分不能抵消关键 Hard Floor

## Definition of Done

```yaml
manifest: complete
clean_build: pass
one_click_start: pass
one_click_test: pass
one_click_deploy: pass
one_click_rollback: pass
database_backup_restore: pass
messaging_closure: pass
ci_cd: pass
fuzz_mutation_formal: pass
observability_security_runbooks_docs: pass
critical_placeholders: 0
cp1_to_cp5: pass
```
