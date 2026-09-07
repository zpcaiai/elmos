# Elmos Project Intelligence Studio — 实施总览

## 1. 建设目标

将 Elmos 从项目生成与语言转换平台扩展为“可读取、理解、解释、可视化、记录、改造和持续维护整个软件项目”的软件智能平台。

核心闭环：

```text
导入项目
→ 冻结 Revision
→ 项目指纹
→ 多语言解析
→ Code Graph
→ Project Intelligence Graph
→ Evidence Graph
→ 在线阅读 / 架构 / 流程 / 数据 / API / 安全
→ 图表 / 文档 / PPT / 报告
→ 问答 / 影响分析 / 架构规则 / 风险
→ Git PR / 转换联动 / 生产认证
```

## 2. 产品原则

1. **统一语义底座**：所有输出来自同一 Project Intelligence Graph。
2. **证据优先**：每个关键结论必须可回源。
3. **增量优先**：按 revision diff 重建最小范围。
4. **人工可控**：自动内容与人工 override 分层。
5. **长任务可靠**：暂停、恢复、重试、取消、检查点、幂等。
6. **安全默认拒绝**：代码、凭据、图谱、搜索和导出均按最小权限。
7. **模型可替换**：模型只负责适合的推理与表达，不垄断解析和事实存储。
8. **生产可验证**：功能、质量、安全、恢复与 SLO 形成 E1–E5 证据。

## 3. 能力域

```text
Read      在线代码阅读、Diff、语义导航
Explain   代码、模块、服务、项目讲解
Explore   依赖、调用、功能、API、数据、部署、安全探索
Flow      业务流程、技术调用、状态、异常、补偿
Diagram   C4、BPMN、Sequence、ER、DFD、Mindmap 等
Document  架构、API、数据、安全、开发、运维、尽调文档
Present   项目介绍、技术评审、培训、售前、迁移、认证 PPT
Impact    变更影响、规则、漂移、风险、技术债、安全
Operate   缓存、恢复、SLO、ETA、部署、认证、商业计量
```

## 4. Epic 总览

| Epic | 名称 | 分类 | 优先级 | 批次 |
|---|---|---|---|---|
| `EPIC-00` | Project Intelligence Studio 总编排 | orchestration | P0 | `BATCH-00-product-and-reference-architecture` |
| `EPIC-01` | 产品范围与需求基线 | foundation | P0 | `BATCH-00-product-and-reference-architecture` |
| `EPIC-02` | 参考架构与服务边界 | foundation | P0 | `BATCH-00-product-and-reference-architecture` |
| `EPIC-03` | 仓库接入与修订冻结 | ingestion | P0 | `BATCH-01-ingestion-and-parsing` |
| `EPIC-04` | 项目指纹与技术栈识别 | ingestion | P0 | `BATCH-01-ingestion-and-parsing` |
| `EPIC-05` | 多语言解析与标准化 Code IR | analysis-core | P0 | `BATCH-01-ingestion-and-parsing` |
| `EPIC-06` | 符号、引用与调用图 | analysis-core | P0 | `BATCH-02-graphs-and-evidence` |
| `EPIC-07` | 统一 Project Intelligence Graph | analysis-core | P0 | `BATCH-02-graphs-and-evidence` |
| `EPIC-08` | 证据图、可信度与来源追踪 | analysis-core | P0 | `BATCH-02-graphs-and-evidence` |
| `EPIC-09` | 在线代码阅读器 | experience | P0 | `BATCH-03-code-reader-and-explanation` |
| `EPIC-10` | 语义导航与跨层追踪 | experience | P0 | `BATCH-03-code-reader-and-explanation` |
| `EPIC-11` | 证据化代码与模块讲解 | experience | P1 | `BATCH-03-code-reader-and-explanation` |
| `EPIC-12` | 项目介绍与新人学习路径 | experience | P1 | `BATCH-03-code-reader-and-explanation` |
| `EPIC-13` | 架构自动发现与多视角讲解 | architecture | P1 | `BATCH-04-architecture-flow-data` |
| `EPIC-14` | 功能思维导图与业务能力地图 | architecture | P1 | `BATCH-04-architecture-flow-data` |
| `EPIC-15` | 业务与技术流程发现 | architecture | P1 | `BATCH-04-architecture-flow-data` |
| `EPIC-16` | 数据架构、ER、DFD 与血缘 | architecture | P1 | `BATCH-04-architecture-flow-data` |
| `EPIC-17` | API、消息与集成拓扑 | architecture | P1 | `BATCH-04-architecture-flow-data` |
| `EPIC-18` | 运行时 Trace、日志与静态图谱融合 | architecture | P1 | `BATCH-04-architecture-flow-data` |
| `EPIC-19` | 统一图表语义规范 | artifacts | P1 | `BATCH-05-diagram-platform` |
| `EPIC-20` | 多格式图表生成与渲染 | artifacts | P1 | `BATCH-05-diagram-platform` |
| `EPIC-21` | 在线图表编辑与人工锁定 | artifacts | P1 | `BATCH-05-diagram-platform` |
| `EPIC-22` | 架构与项目文档生成 | artifacts | P1 | `BATCH-06-documents-presentations-reports` |
| `EPIC-23` | 项目介绍与技术汇报 PPT 生成 | artifacts | P1 | `BATCH-06-documents-presentations-reports` |
| `EPIC-24` | 项目全景报告与交付证据包 | artifacts | P1 | `BATCH-06-documents-presentations-reports` |
| `EPIC-25` | 项目全局搜索与证据化问答 | intelligence | P2 | `BATCH-07-search-impact-governance-analysis` |
| `EPIC-26` | 变更影响与回归范围分析 | intelligence | P2 | `BATCH-07-search-impact-governance-analysis` |
| `EPIC-27` | 架构规则与策略引擎 | intelligence | P2 | `BATCH-07-search-impact-governance-analysis` |
| `EPIC-28` | 设计—代码—运行架构漂移检测 | intelligence | P2 | `BATCH-07-search-impact-governance-analysis` |
| `EPIC-29` | 风险、热点与技术债分析 | intelligence | P2 | `BATCH-07-search-impact-governance-analysis` |
| `EPIC-30` | 代码与架构安全分析及威胁建模 | intelligence | P2 | `BATCH-07-search-impact-governance-analysis` |
| `EPIC-31` | 增量分析、缓存与检查点 | platform | P2 | `BATCH-08-cache-versioning-git` |
| `EPIC-32` | Artifact 版本与人工内容保护 | platform | P2 | `BATCH-08-cache-versioning-git` |
| `EPIC-33` | Git、文档 PR 与变更交付自动化 | platform | P2 | `BATCH-08-cache-versioning-git` |
| `EPIC-34` | 协作、RBAC、审批与审计 | enterprise | P2 | `BATCH-09-collaboration-and-connectors` |
| `EPIC-35` | 外部系统、连接器与 MCP 集成 | enterprise | P2 | `BATCH-09-collaboration-and-connectors` |
| `EPIC-36` | 大型仓库与多仓库系统扩展 | platform | P2 | `BATCH-10-scale-and-observability` |
| `EPIC-37` | 可观测性、SLO 与运营指标 | operations | P2 | `BATCH-10-scale-and-observability` |
| `EPIC-38` | 测试、评测与数据质量 | quality | P2 | `BATCH-11-testing-conversion-estimation` |
| `EPIC-39` | 与 Elmos 生成、转换、翻新引擎集成 | integration | P3 | `BATCH-11-testing-conversion-estimation` |
| `EPIC-40` | 系统运行 ETA、Token 与成本估算 | operations | P3 | `BATCH-11-testing-conversion-estimation` |
| `EPIC-41` | SaaS、私有化与离线部署 | operations | P3 | `BATCH-12-deployment-and-certification` |
| `EPIC-42` | 生产验收与 E1–E5 认证 | quality | P3 | `BATCH-12-deployment-and-certification` |
| `EPIC-43` | 商业版本、计量与交付套餐 | product | P3 | `BATCH-13-commercialization` |
| `EPIC-44` | 调试适配器网关与能力协商 | debug-platform | P1 | `BATCH-14-online-debug-and-learning` |
| `EPIC-45` | 调试沙箱、运行环境与会话编排 | debug-platform | P1 | `BATCH-14-online-debug-and-learning` |
| `EPIC-46` | 在线调试工作台 | debug-experience | P1 | `BATCH-14-online-debug-and-learning` |
| `EPIC-47` | 调试学习 Copilot 与互动实验 | debug-learning | P1 | `BATCH-14-online-debug-and-learning` |
| `EPIC-48` | 调试记录、检查点与运行回放 | debug-runtime | P2 | `BATCH-14-online-debug-and-learning` |
| `EPIC-49` | 分布式调试、异步因果与源目标对照 | debug-integration | P2 | `BATCH-14-online-debug-and-learning` |

## 5. P0 最小商业闭环

P0 不做完整在线 IDE，而完成：

- Git/ZIP 导入与 revision 冻结；
- 多语言基础解析、符号索引、Code Graph；
- Evidence Graph；
- 在线代码阅读、定义/引用/调用层级；
- 项目概览与基础架构发现；
- 系统上下文图、模块图、类/调用图；
- 基础架构文档；
- 项目证据化问答；
- 增量缓存、任务恢复；
- 权限、安全与自动化验收。

## 6. P0 验收用户旅程

### Journey A：开发者理解陌生项目

1. 导入固定 commit。
2. 5 分钟内看到技术栈、入口和分析覆盖。
3. 在代码阅读器搜索退款功能。
4. 从页面/API 跳到 Service、Repository 和数据表。
5. 请求讲解并查看证据。
6. 保存阅读路径和笔记。

### Journey B：架构师评审

1. 打开系统上下文与容器图。
2. 下钻到组件、调用、事件和数据。
3. 查看循环依赖、共享数据库、未鉴权接口。
4. 对错误聚合进行人工修正并锁定。
5. 导出架构文档和技术评审 PPT。

### Journey C：Elmos 语言转换

1. 同时打开 Source、Semantic IR、Target。
2. 查看映射、规则命中、低置信度和失败。
3. 从测试失败跳到目标代码与源代码。
4. 接受修复 Patch 并重新验证。
5. 生成迁移对比文档、图表和 PPT。

## 7. v1.1 在线调试扩展

```text
Debug     在线断点、单步、栈、变量、Watch 和副作用时间线
Learn     Observe/Guided/Challenge/Free/Compare 调试学习
Replay    R0 事件回看、R1 输入重放、R2 检查点、R3 原生反向调试
Correlate 前后端、微服务、消息与 Source/Target 因果对照
```

新增 Epic：`EPIC-44`–`EPIC-49`，由 `BATCH-14-online-debug-and-learning` 实施。调试是受控运行能力，不改变 P0“阅读优先、不做通用云 IDE”的边界。
