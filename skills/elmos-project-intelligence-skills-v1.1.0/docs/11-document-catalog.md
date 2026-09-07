# 文档目录与生成规范

## 文档目录

| # | 文档 | 受众 | 核心内容 |
|---:|---|---|---|
| 1 | 项目一页纸 | 管理/新人 | 使命、边界、能力、技术栈、入口、风险 |
| 2 | 项目概览 README | 开发 | 启动、目录、构建、测试、核心链接 |
| 3 | 业务能力文档 | 产品/管理 | 业务域、能力、功能、角色、价值流 |
| 4 | 系统架构文档 | 架构 | C4、多视角、依赖、权衡、未知 |
| 5 | 模块目录 | 开发/架构 | 职责、接口、依赖、数据、测试、owner |
| 6 | 业务流程文档 | 产品/测试 | 前置、步骤、分支、状态、异常、补偿 |
| 7 | API 手册 | 开发/集成 | 端点、Schema、Auth、错误、示例、版本 |
| 8 | 事件目录 | 开发/集成 | Topic、Schema、Producer、Consumer、DLQ |
| 9 | 数据架构与字典 | 数据/开发 | 表、字段、约束、敏感级别、血缘 |
| 10 | 安全架构文档 | 安全/审计 | 身份、边界、威胁、控制、残余风险 |
| 11 | 部署架构文档 | 运维 | 环境、拓扑、配置、网络、依赖 |
| 12 | 可观测性文档 | SRE | SLI/SLO、Trace、日志、指标、告警 |
| 13 | 测试策略 | 测试/开发 | 测试层、覆盖、Fixture、门禁 |
| 14 | 本地开发指南 | 开发 | 依赖、启动、调试、数据和常见问题 |
| 15 | 运维 Runbook | SRE | 告警、诊断、恢复、升级、回滚 |
| 16 | 灾难恢复手册 | SRE/审计 | RPO/RTO、备份、恢复和演练 |
| 17 | 架构决策 ADR | 架构 | 上下文、选择、替代、后果 |
| 18 | 技术债与风险报告 | 管理/架构 | 证据、优先级、成本、收益 |
| 19 | 技术尽调报告 | 投资/并购 | 质量、安全、扩展、团队依赖、成本 |
| 20 | 项目交接文档 | 团队 | 资产、权限、环境、流程、未决事项 |
| 21 | 现代化路线图 | 管理/架构 | 当前、目标、批次、风险、回滚 |
| 22 | 语言转换说明 | Elmos | Source/IR/Target、规则、差异、限制 |
| 23 | 生产认证报告 | 审计/客户 | E1–E5、证据、残余风险、签名 |

## 生成规则

1. 先形成事实大纲和 claim 列表，再生成自然语言。
2. 每个章节绑定 revision、analysis run、template 和 generator version。
3. 关键结论有 evidence refs。
4. 当前事实、推断、未知和建议分栏或标识。
5. 章节拥有 stable block ID。
6. 自动区和人工区分层，支持锁定和三方合并。
7. 代码变化时只更新受影响章节。
8. Markdown 是 docs-as-code 默认源；可导出 DOCX/PDF/HTML。
9. 链接、引用、敏感信息、无障碍和格式均有自动验证。
10. 文档可创建 Draft PR，由人工审核合并。

## 推荐输出树

```text
docs/generated/
├── 00-project-overview.md
├── 01-business-capabilities.md
├── 02-system-architecture.md
├── 03-module-catalog/
├── 04-business-flows/
├── 05-api-catalog.md
├── 06-event-catalog.md
├── 07-data-architecture.md
├── 08-security-architecture.md
├── 09-deployment-architecture.md
├── 10-observability.md
├── 11-testing-strategy.md
├── 12-development-guide.md
├── 13-operations-runbook.md
├── 14-risks-and-debt.md
├── 15-modernization-roadmap.md
└── evidence-manifest.json
```
