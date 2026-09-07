# 产品需求文档（PRD）

## 1. 产品名称

**Elmos Project Intelligence Studio（Elmos Insight Studio）**

## 2. 问题陈述

大型项目通常存在以下困难：

- 新成员无法快速理解项目边界、入口、核心流程和数据；
- 代码、架构文档、流程图和实际运行长期不一致；
- AI 讲解容易产生无法追踪的幻觉；
- 项目转换或翻新后，用户无法快速验证“改了什么、是否保持行为”；
- 文档、图表和 PPT 需要重复人工整理，代码变化后迅速过期；
- 大仓库分析耗时长，中断后重来，Token 与算力浪费；
- 企业无法放心把私有代码交给不透明工具。

## 3. 目标用户

| 角色 | 核心任务 | 首要输出 |
|---|---|---|
| 开发者 | 理解、定位、修改代码 | 代码阅读、调用链、讲解、影响分析 |
| 新人/学习者 | 通过真实执行理解项目 | 引导调试、Learning Mission、知识卡、学习进度 |
| 架构师 | 发现与治理架构 | C4、多视角架构、规则、漂移 |
| 产品经理 | 理解业务能力和流程 | 功能思维导图、业务流程、项目介绍 |
| 测试人员 | 找到关键路径与回归范围 | 流程、状态机、测试映射、影响报告 |
| 运维/SRE | 理解部署和运行 | 部署拓扑、Trace、SLO、Runbook |
| 安全人员 | 识别边界、敏感数据和攻击路径 | Threat Model、敏感 DFD、漏洞证据 |
| 管理者/客户 | 快速了解价值和风险 | 管理层 PPT、项目报告、路线图 |
| Elmos 转换工程师 | 验证源/目标等价与修复 | Source/IR/Target、映射、认证证据 |
| 审计人员 | 核验结论来源与审批 | Evidence Bundle、审计、签名报告 |

## 4. 核心功能需求

### 4.1 项目接入

- GitHub、GitLab、Gitee、Bitbucket、通用 Git；
- ZIP、本地目录、Elmos 暂存项目；
- 单仓库、Monorepo、多仓库 System Workspace；
- 分支、Tag、Commit、子模块、LFS；
- include/exclude、生成代码、Vendor、二进制和敏感文件策略；
- 内容寻址存储、revision manifest、删除与保留策略。

### 4.2 在线代码阅读

- 虚拟化文件树、搜索、高亮、折叠、大纲、面包屑；
- 多标签、分屏、大文件、Markdown/图片/配置预览；
- Git blame、文件历史、Commit Diff；
- Source/Target/IR 对比；
- 深链、书签、笔记、评论、最近阅读；
- 只读默认，编辑能力单独授权。

### 4.3 语义导航与讲解

- Definition、References、Implementations、Call/Type Hierarchy；
- 页面→API→Service→Repository→Table 双向追踪；
- Topic→Producer/Consumer、Test→Target、Config→Reader；
- 行/块/函数/类/模块/服务/项目讲解；
- 输入、输出、依赖、副作用、异常、事务、并发、安全、测试；
- 管理、产品、架构、开发、测试、运维、安全不同受众；
- Confirmed/Inferred/Unknown/Recommended 与证据链接。

### 4.4 架构与流程

- 业务、应用、技术、数据、部署、安全、运维架构；
- C4 L1–L4、分层、六边形、插件、微服务、多仓库；
- 业务能力地图、功能思维导图；
- HTTP/RPC/Message/Cron/CLI/Webhook/Agent 流程；
- Happy/Error/Retry/Compensation；
- BPMN、泳道、时序、状态机、决策树；
- 静态架构与运行架构对比。

### 4.5 数据、API 与集成

- DDL、迁移、ORM、SQL、表字段、索引、约束；
- ER、DFD、字段级血缘、CRUD、生命周期；
- 缓存、搜索、文件、ETL/ELT；
- REST、GraphQL、gRPC、WebSocket、Webhook；
- Topic/Queue、Schema、Producer/Consumer、DLQ；
- Breaking change、未鉴权、未测试、未文档风险。

### 4.6 图表、文档、PPT 和报告

- 统一 Diagram Spec；
- Mermaid、PlantUML、Structurizr、Graphviz、BPMN XML、Markmap；
- SVG、PNG、PDF、可编辑 Web Canvas；
- 项目概览、架构、模块、流程、API、数据、安全、部署、测试、运维；
- 新人指南、尽调、交接、迁移和认证文档；
- 管理、技术评审、培训、售前、尽调、迁移、认证 PPTX；
- 人工锁定、三方合并、增量更新、Git PR。

### 4.7 智能分析

- 符号/文本/结构/图谱/向量混合搜索；
- 证据化问答；
- 代码/API/Schema/事件/配置变更影响；
- 架构规则与豁免；
- 设计—静态—运行漂移；
- 复杂度、耦合、热点、覆盖、漏洞和业务关键度风险；
- 威胁模型和攻击路径。

### 4.8 在线调试与调试学习

- 固定 revision、Runtime Profile、一次性沙箱和 adapter capability negotiation；
- 行/条件/日志/异常断点，以及运行时支持时的函数/数据断点；
- Continue/Pause/Step、线程/协程、调用栈、变量、Watch、只读 Evaluate；
- HTTP、SQL、事务、缓存、消息、文件、外部调用和并发副作用时间线；
- 当前 Frame 与代码、架构、流程、数据、测试双向联动；
- Observe、Guided、Challenge、Free、Compare 学习模式；
- R0–R3 记录/回放等级和 Source/Target 同场景对照；
- 非生产默认、生产 attach 禁用、脱敏数据、Secrets Broker、资源配额和完整清理。

### 4.9 生产能力

- 内容寻址缓存与依赖失效；
- 暂停、恢复、重试、取消、检查点、幂等；
- SSO、SCIM、MFA、RBAC/ABAC、审计；
- Prompt Injection、Secret、敏感数据和租户隔离；
- 大型仓库分片、优先索引、公平调度；
- SLO、日志、指标、Trace、成本和 ETA；
- SaaS、私有云、内网、离线部署；
- E1–E5 生产认证。

## 5. 范围外（P0）

- 完整 VS Code 插件市场；
- 任意命令终端；
- Remote SSH；
- P0 不含全功能调试器；受控在线调试由 Batch 14 独立交付；
- 任意 Dev Container 执行；
- 多人 Google Docs 式实时协同；
- 自动修改生产环境；
- 无人工门禁的高风险自动重构。

## 6. 关键质量指标

- 代码打开 p95；
- 解析成功率；
- Definition/Reference 准确率；
- 图谱证据覆盖率；
- 问答引用正确率和正确拒答率；
- 流程步骤召回率；
- 人工锁定保留率；
- 增量重算比例；
- 恢复成功率和重复副作用数；
- 权限/租户泄漏事件数；
- ETA P50/P90 校准误差；
- Artifact stale 率；
- E2E 用户旅程通过率。
