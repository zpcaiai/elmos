---
name: software-delivery-platform-engine-contract-and-worker
description: 实现软件交付与平台工程引擎、SCM和CI Provider、平台操作Worker及ELMOS统一契约。
---

# Platform Engineering Engine

## Capability

{
  "engine": "ELMOS_SOFTWARE_DELIVERY_PLATFORM",
  "engineVersion": "1.0.0",
  "capabilities": [
    "SCM_DISCOVERY",
    "SCM_MIGRATION",
    "PIPELINE_ANALYSIS",
    "PIPELINE_COMPONENTS",
    "ARTIFACT_REGISTRY",
    "ENVIRONMENT_LIFECYCLE",
    "GITOPS",
    "SOFTWARE_CATALOG",
    "GOLDEN_PATH",
    "SELF_SERVICE",
    "DEVEX",
    "DORA",
    "PLATFORM_PRODUCT"
  ]
}

## API

GET  /engine/v1/capabilities
POST /engine/v1/discover
POST /engine/v1/plan
POST /engine/v1/execute-step
POST /engine/v1/validate
POST /engine/v1/self-service
GET  /engine/v1/jobs/{jobId}
POST /engine/v1/jobs/{jobId}/cancel

## Worker职责

- 读取SCM和CI Metadata；
- 读取Artifact与Deployment；
- 建立Delivery Graph；
- 执行Repository Migration Sandbox；
- 验证Pipeline Component；
- 创建临时Environment；
- 执行Platform Acceptance Journey；
- 收集Evidence；
- 清理临时资源。

## Worker默认禁止

- 删除生产Repository；
- 重写生产Git历史；
- 删除Release Tag；
- 删除Production Artifact；
- 修改保护分支；
- 自动部署生产；
- 自动批准平台例外；
- 将团队强制迁入Golden Path。

## Provider权限

每个Provider：

- 短期Token；
- Organization绑定；
- Repository Scope；
- Operation Allowlist；
- Audit；
- Rate Limit；
- Revocation。

## 验收标准

- Engine独立部署；
- SCM和CI Provider可替换；
- Discovery默认只读；
- 所有写操作先Plan；
- Self-service受Policy约束；
- Evidence进入统一Contract。
