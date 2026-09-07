---
name: control-tower-engine-contract-and-worker
description: "实现ELMOS最高控制塔、跨引擎任务契约、全局Worker和控制平面边界。"
---

# Control Tower Engine

## Capability

{
  "engine": "ELMOS_CONTROL_TOWER",
  "engineVersion": "1.0.0",
  "capabilities": [
    "KNOWLEDGE_GRAPH",
    "ENTERPRISE_TWIN",
    "CROSS_ENGINE_ORCHESTRATION",
    "AGENT_MESH",
    "POLICY_DECISION",
    "AUTONOMOUS_PLANNING",
    "SCENARIO_SIMULATION",
    "HUMAN_DECISION",
    "EXECUTION_CONTROL",
    "VALUE_FEEDBACK",
    "PRODUCTION_HARDENING"
  ]
}

## API

GET  /control/v1/capabilities
POST /control/v1/discover
POST /control/v1/twin/snapshot
POST /control/v1/plans
POST /control/v1/plans/{id}/simulate
POST /control/v1/plans/{id}/decide
POST /control/v1/plans/{id}/execute
POST /control/v1/executions/{id}/pause
POST /control/v1/executions/{id}/reconcile
GET  /control/v1/jobs/{jobId}
POST /control/v1/jobs/{jobId}/cancel

## Worker职责

- 获取跨引擎Capability；
- 固定协议和Schema版本；
- 创建Twin Snapshot；
- 生成Workflow；
- 请求Policy；
- 路由Agent和Engine；
- 汇总Evidence；
- 验证价值结果。

## 默认禁止

- 直接执行任意Shell；
- 使用共享生产管理员身份；
- 绕过Domain Engine；
- 修改本地Safety Policy；
- 自动批准高风险Plan；
- 自动接受业务收益；
- 自动扩大Agent权限；
- 删除审计历史。

## Job Lease

绑定：

Tenant
Plan
Workflow
Engine
Agent
Purpose
Scope
Budget
Policy
Expiry

## 验收标准

- 控制塔独立部署；
- 领域执行通过Adapter；
- Plan和Execution分离；
- 所有动作有Lease；
- 控制塔离线不破坏本地生产；
- Evidence统一。
