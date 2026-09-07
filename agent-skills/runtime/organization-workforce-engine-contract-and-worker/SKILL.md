---
name: organization-workforce-engine-contract-and-worker
description: "实现组织能力、技术人才和劳动力现代化引擎、敏感数据边界、Provider Adapter及统一任务契约。"
---

# Organization Workforce Engine

## Capability

{
  "engine": "ELMOS_ORGANIZATION_WORKFORCE",
  "engineVersion": "1.0.0",
  "capabilities": [
    "ORGANIZATION_DISCOVERY",
    "PRODUCT_OPERATING_MODEL",
    "TEAM_TOPOLOGY",
    "SKILL_GRAPH",
    "WORK_ARCHITECTURE",
    "JOB_ARCHITECTURE",
    "CAREER_FRAMEWORK",
    "WORKFORCE_PLANNING",
    "AI_AUGMENTED_WORK",
    "LEARNING",
    "CREDENTIAL",
    "TALENT_MARKET",
    "SUCCESSION",
    "KEY_PERSON_RISK",
    "VENDOR_WORKFORCE",
    "ORGANIZATION_CHANGE"
  ]
}

## API

GET  /engine/v1/capabilities
POST /engine/v1/discover
POST /engine/v1/model
POST /engine/v1/assess
POST /engine/v1/plan
POST /engine/v1/simulate
POST /engine/v1/validate
GET  /engine/v1/jobs/{jobId}
POST /engine/v1/jobs/{jobId}/cancel

## Worker职责

- 读取批准的组织数据；
- 建立组织、工作和技能模型；
- 聚合团队级Evidence；
- 执行供需和组织Scenario；
- 验证学习及Credential；
- 输出组织设计候选；
- 保存隐私和Audit Evidence。

## 默认禁止

- 自动招聘；
- 自动晋升或降级；
- 自动调整薪酬；
- 自动裁员；
- 自动确认继任人；
- 根据Commit对个人排名；
- 分析私人消息情绪；
- 推断敏感个人属性；
- 输出不透明的个人离职概率。

## Provider

HRIS
LMS
ATS
DIRECTORY
PORTFOLIO
SERVICE_CATALOG
SCM
ITSM
FINANCE
VENDOR_MANAGEMENT
CREDENTIAL_PROVIDER

## 验收标准

- Engine独立部署；
- 个人数据与普通资产数据隔离；
- Provider最小权限；
- 所有高影响决定由授权人员完成；
- 数据用途和保留期明确；
- Evidence进入统一Contract。
