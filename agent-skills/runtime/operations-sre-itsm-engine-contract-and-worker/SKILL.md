---
name: operations-sre-itsm-engine-contract-and-worker
description: 实现运维、SRE与ITSM引擎、Provider Adapter、事件Worker和受控运维执行契约。
---

# Operations Engine

## Capability

{
  "engine": "ELMOS_OPERATIONS_SRE_ITSM",
  "engineVersion": "1.0.0",
  "capabilities": [
    "CMDB",
    "SERVICE_TOPOLOGY",
    "EVENT_MANAGEMENT",
    "INCIDENT",
    "PROBLEM",
    "CHANGE",
    "SLO",
    "ONCALL",
    "RUNBOOK",
    "AIOPS",
    "AUTO_REMEDIATION",
    "CAPACITY",
    "BUSINESS_CONTINUITY",
    "OPERATIONS_COCKPIT"
  ]
}

## API

GET  /engine/v1/capabilities
POST /engine/v1/discover
POST /engine/v1/events
POST /engine/v1/incidents
POST /engine/v1/changes
POST /engine/v1/remediate
POST /engine/v1/validate
GET  /engine/v1/jobs/{jobId}
POST /engine/v1/jobs/{jobId}/cancel

## Worker职责

- 拉取CMDB和Service Catalog；
- 读取Telemetry；
- 标准化Event；
- 创建Incident候选；
- 执行只读诊断；
- 运行受控Runbook；
- 收集恢复Evidence；
- 输出Operational Decision。

## 默认禁止

- 自动关闭Major Incident；
- 自动确认Root Cause；
- 无限制执行生产命令；
- 自动批准High-risk Change；
- 删除Incident Timeline；
- 修改SLO掩盖失败；
- 自动关闭Postmortem Action；
- 自动停止业务服务。

## Provider

ITSM
CMDB
Observability
Pager
Chat
Status Page
Deployment
Cloud
Security
Business KPI

## 验收标准

- Engine独立部署；
- Provider可替换；
- Event接口幂等；
- 生产操作使用短期Lease；
- 自动化受Policy限制；
- Evidence进入统一Contract。
