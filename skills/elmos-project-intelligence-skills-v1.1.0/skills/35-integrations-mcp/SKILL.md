---
name: elmos-integrations-mcp
description: 设计 Git、文档、Issue、CI/CD、Observability、制品库和企业知识系统连接器，并可通过 MCP/Adapter 暴露受控工具。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: enterprise
  title_zh: 外部系统、连接器与 MCP 集成
  batch: BATCH-09-collaboration-and-connectors
  owner: elmos-project-intelligence
---

# 外部系统、连接器与 MCP 集成

## 目标

让 Elmos 接入外部系统而不把供应商逻辑耦合到分析核心。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- integration target
- capabilities
- auth method
- tenant policy

## 必须输出

- connector contract
- MCP tools/resources
- sync jobs
- audit/health

## 执行流程

1. 定义 Repository、Issue、Docs、CI、Trace、Artifact Registry 等 Port。
2. 为供应商实现 Adapter 和能力发现。
3. 使用 OAuth/OIDC/service account/short-lived token。
4. 为读取、搜索、写入、回调定义精确工具 Schema。
5. 实现限流、重试、幂等、游标同步和健康检查。
6. 为连接器建立权限、审计、数据驻留和故障降级。

## 实施要求

- 连接器能力在运行时发现，不假设所有供应商支持相同写操作。
- MCP 工具命名、输入和输出稳定且最小化。
- 写操作与读操作分权。
- 连接器失败不得破坏本地已冻结 revision。
- Webhook 需验签和防重放。

## 安全与可信度约束

- 不得将长期 token 传给模型。
- 不得用 web scraping 替代可用官方 API 作为生产默认。
- 不得在工具描述中暴露秘密或内部地址。

## 依赖技能

- `elmos-repository-ingestion`
- `elmos-collaboration-governance`

## 预期交付物

- `connector-sdk.md`
- `mcp-tool-catalog.yaml`
- `connector-contract-tests.md`

## 完成定义

- [ ] 至少一个 Git 和一个 Trace 连接器端到端通过。
- [ ] 限流/过期 token/部分失败可恢复。
- [ ] 工具 Schema 通过契约测试。
- [ ] 写操作幂等。
- [ ] 连接器可替换而不改分析核心。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
