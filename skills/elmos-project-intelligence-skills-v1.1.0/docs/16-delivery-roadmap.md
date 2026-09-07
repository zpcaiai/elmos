# 交付路线图

## 原则

- 每个批次完成可运行垂直切片，不只提交接口；
- 每批均有 Schema、API/事件、实现、测试、SLO、权限和证据；
- 后续批次不得以重写替代前批次可升级设计；
- 任一批次可通过检查点继续；
- 实际机器执行 ETA 由 `elmos-runtime-cost-estimator` 根据仓库与环境估算，不把人工人日冒充系统时间。

## 批次

| 批次 | 目标 | Skills |
|---|---|---|
| `BATCH-00-product-and-reference-architecture` | 产品基线与参考架构 | `elmos-insight-orchestrator`<br>`elmos-product-scope`<br>`elmos-reference-architecture` |
| `BATCH-01-ingestion-and-parsing` | 仓库接入、指纹与解析 | `elmos-repository-ingestion`<br>`elmos-project-fingerprinting`<br>`elmos-multilanguage-parsing` |
| `BATCH-02-graphs-and-evidence` | Code Graph、Intelligence Graph 与 Evidence | `elmos-symbol-code-graph`<br>`elmos-project-intelligence-graph`<br>`elmos-evidence-provenance` |
| `BATCH-03-code-reader-and-explanation` | 在线代码阅读、导航、讲解与新人路径 | `elmos-online-code-reader`<br>`elmos-semantic-navigation`<br>`elmos-code-explanation`<br>`elmos-onboarding-learning-path` |
| `BATCH-04-architecture-flow-data` | 架构、功能、流程、数据、API 与运行融合 | `elmos-architecture-discovery`<br>`elmos-business-capability-map`<br>`elmos-flow-discovery`<br>`elmos-data-architecture-lineage`<br>`elmos-api-event-topology`<br>`elmos-runtime-trace-fusion` |
| `BATCH-05-diagram-platform` | Artifact 版本底座、统一图表规范、渲染与在线编辑 | `elmos-diagram-spec-engine`<br>`elmos-diagram-rendering`<br>`elmos-artifact-versioning-human-lock`<br>`elmos-diagram-editor` |
| `BATCH-06-documents-presentations-reports` | 架构文档、PPT 与全景报告 | `elmos-architecture-documentation`<br>`elmos-presentation-generation`<br>`elmos-project-report-bundle` |
| `BATCH-07-search-impact-governance-analysis` | 搜索问答、影响、规则、漂移、风险与安全 | `elmos-project-search-qa`<br>`elmos-impact-analysis`<br>`elmos-architecture-rules`<br>`elmos-architecture-drift`<br>`elmos-risk-technical-debt`<br>`elmos-security-threat-model` |
| `BATCH-08-cache-versioning-git` | 增量缓存、失效传播与 Git PR | `elmos-incremental-analysis-cache`<br>`elmos-git-pr-automation` |
| `BATCH-09-collaboration-and-connectors` | 协作治理与连接器/MCP | `elmos-collaboration-governance`<br>`elmos-integrations-mcp` |
| `BATCH-10-scale-and-observability` | 大型仓库、SLO 与可观测 | `elmos-large-repository-scaling`<br>`elmos-observability-slo` |
| `BATCH-11-testing-conversion-estimation` | 测试评测、转换集成与 ETA/成本 | `elmos-testing-evaluation`<br>`elmos-conversion-integration`<br>`elmos-runtime-cost-estimator` |
| `BATCH-12-deployment-and-certification` | 生产部署与 E1–E5 认证 | `elmos-deployment-private-cloud`<br>`elmos-release-certification` |
| `BATCH-13-commercialization` | 商业版本、计量与交付 | `elmos-commercial-packaging` |
| `BATCH-14-online-debug-and-learning` | Adapter、沙箱、在线调试、学习、回放与分布式对照 | `elmos-debug-adapter-gateway`<br>`elmos-debug-sandbox-orchestration`<br>`elmos-online-debug-workbench`<br>`elmos-debug-learning-copilot`<br>`elmos-debug-record-replay`<br>`elmos-distributed-debug-correlation` |

## 里程碑

### M1：Evidence-backed Reader

- 导入与固定 revision；
- 多语言基础索引；
- Definition/References/Call；
- 在线代码阅读；
- 项目概览；
- 证据化讲解。

### M2：Architecture & Flow Intelligence

- C4 与多视角；
- 功能思维导图；
- 业务/技术流程；
- ER/DFD/血缘；
- API/事件；
- Runtime Trace 融合。

### M3：Artifact Factory

- Diagram Spec；
- 多渲染器；
- 在线编辑；
- 架构文档；
- PPTX；
- 报告证据包。

### M4：Continuous Intelligence

- 问答；
- 影响分析；
- 架构规则和漂移；
- 风险/技术债/安全；
- 增量更新；
- Git PR。

### M5：Elmos Production Integration

- Source/IR/Target；
- 生成/转换/翻新；
- 行为与性能证据；
- 机器 ETA/成本；
- 私有化；
- E1–E5 认证；
- 商业版本。


### M6：Debug-to-Learn

- 固定 revision 与安全一次性沙箱；
- P0 Runtime Adapter 合规；
- 在线断点、单步、栈、变量和副作用；
- 调试学习 Mission/Lab；
- R0–R3 回放；
- 前后端/微服务因果和 Source/Target 对照。
