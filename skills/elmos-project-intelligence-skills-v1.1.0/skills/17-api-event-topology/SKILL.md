---
name: elmos-api-event-topology
description: 抽取 REST/GraphQL/gRPC/WebSocket/Webhook、消息 Topic、生产者消费者和第三方集成，生成契约目录、拓扑和兼容性风险。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: architecture
  title_zh: API、消息与集成拓扑
  batch: BATCH-04-architecture-flow-data
  owner: elmos-project-intelligence
---

# API、消息与集成拓扑

## 目标

把系统所有外部与内部接口统一为可版本化、可回源、可影响分析的 Integration Graph。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- OpenAPI/Proto/GraphQL
- 路由和客户端代码
- 消息 Schema
- 配置与 Trace

## 必须输出

- API catalog
- event catalog
- integration topology
- compatibility report

## 执行流程

1. 抽取端点、方法、请求响应、认证、错误和版本。
2. 抽取 Topic/Queue、事件 Schema、生产者、消费者、重试和死信。
3. 识别 HTTP/RPC 客户端、SDK、Webhook 和第三方服务。
4. 关联接口到功能、服务、数据和测试。
5. 检测未文档接口、Schema 漂移、废弃版本和消费者风险。
6. 生成 API 拓扑、事件拓扑、时序和版本兼容图。

## 实施要求

- 声明契约与实现路由需对账。
- 运行时观察仅作为活跃度证据。
- 敏感参数和样例必须脱敏。
- 支持契约 diff 和 breaking-change 规则。
- 每个接口有 owner、SLA、auth、idempotency 等元数据入口。

## 安全与可信度约束

- 不得把内部方法误标为公网 API。
- 无 Schema 的消息必须标记治理风险。
- 不得公开第三方凭据或真实回调地址。

## 依赖技能

- `elmos-project-intelligence-graph`
- `elmos-evidence-provenance`

## 预期交付物

- `api-catalog.json`
- `event-catalog.json`
- `integration-topology.json`

## 完成定义

- [ ] 已声明接口与实现映射覆盖率可量化。
- [ ] Breaking change 检测有正反例测试。
- [ ] Topic 生产者/消费者链可追踪。
- [ ] 未鉴权和未测试接口可筛选。
- [ ] 拓扑节点可回到契约与代码。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
