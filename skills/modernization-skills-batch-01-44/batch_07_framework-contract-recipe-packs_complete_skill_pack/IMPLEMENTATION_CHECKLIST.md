# Implementation Checklist — Batch 07: Framework Contract Model and Framework Migration Recipe Packs

## Contracts and Architecture

- [ ] 上游兼容协议、证书、Digest 与失效规则已实现
- [ ] Domain Model、Schema、Migration 和 Unknown Field Preservation 已实现
- [ ] CapabilityPackage、Dependency 和 Evidence 绑定已实现
- [ ] 状态机、幂等、Lease、Checkpoint、Cancel 和 Compensation 已实现

## Domain Capabilities

- [ ] Framework Contract Model
- [ ] 精确源目标版本指纹
- [ ] REST/RPC 路由与绑定
- [ ] DTO、Validation 与 Serialization
- [ ] DI 容器与 Scope
- [ ] Authentication/Authorization
- [ ] ORM、事务与迁移
- [ ] 配置与 Secret 引用
- [ ] Logging/Tracing/Metrics
- [ ] Cache、Messaging、Scheduler
- [ ] OpenAPI 与测试契约
- [ ] Coexistence/Strangler/Adapter

## Safety and Governance

- [ ] 默认拒绝网络、文件、Secret、Tool 和 Agent 权限
- [ ] Tenant Isolation、RBAC/ABAC、职责分离和审计已测试
- [ ] SBOM、签名、Provenance、许可证和漏洞策略已实现
- [ ] Human Approval、Exception、Expiry、Revocation 已实现

## Tests and Evidence

- [ ] Schema valid/invalid/compatibility tests
- [ ] Unit/Integration/E2E tests
- [ ] Determinism with 1/4/16 workers where applicable
- [ ] Retry/Timeout/Cancel/Rollback/Recovery tests
- [ ] Security negative and prompt-injection tests
- [ ] Holdout and representative corpus
- [ ] Performance/capacity/cost metrics with denominators
- [ ] Conservative fake-certification rejection
- [ ] Certificate invalidation and recertification tests

## Delivery

- [ ] README/API/Runbook/Architecture Decision records
- [ ] One-command local validation
- [ ] Real Validation Report with exact commands/results
- [ ] Known limitations and unresolved risks
- [ ] DownstreamCompatibilityManifest
