# Elmos Project Intelligence Studio — Skills Package v1.1.0

本包把 Elmos 的“在线代码阅读器、架构讲解、流程梳理、架构文档、架构图、功能思维导图、数据流图、项目介绍 PPT 和项目相关图表”细化为 **50 个可执行 Agent Skills**，并补充生产级所需的证据链、增量缓存、权限治理、运行时 Trace、影响分析、测试评测、机器 ETA/成本、私有化部署和 E1–E5 认证。

## 1. 最终产品定位

**Elmos Project Intelligence Studio** 是 Elmos 的项目理解与知识交付子系统：

```text
Repository / Generated Project / Converted Project
        ↓
Ingestion → Parsing → Code Graph
        ↓
Project Intelligence Graph + Evidence Graph
        ↓
Code Reader / Online Debug / Architecture / Flows / Data / API / Security
        ↓
Diagrams / Documents / PPT / Reports / Q&A / Impact Analysis
        ↓
Git PR / Delivery Bundle / Production Certification
```

所有图表、文档、PPT 和讲解必须来自同一项目语义底座，并能追踪到代码、配置、Schema、测试或运行 Trace。系统必须区分：

- `Confirmed`：直接证据确认；
- `Inferred`：基于规则或模型推断；
- `Unknown`：证据不足；
- `Recommended`：改进建议。

## 2. 包含内容

- `skills/`：50 个标准 `SKILL.md`，每个带独立 `references/module-spec.md`。
- `docs/`：产品、架构、领域模型、API、事件、数据、安全、UI、NFR、路线图和验收文档。
- `backlog/`：可机器读取的 Epic、任务、验收场景和追踪矩阵。
- `schemas/`：Project Manifest、Evidence、Artifact、Diagram、Job 等 JSON Schema。
- `contracts/`：OpenAPI、AsyncAPI 和 Graph Query 契约草案。
- `templates/`：架构文档、模块文档、ADR、PPT、报告、图表模板。
- `batches/`：15 个可按顺序执行的实现批次。
- `scripts/`：安装、校验、索引和重新打包脚本。
- `examples/`：示例项目 manifest、证据、图表和任务输入。
- `tests/`：技能包结构测试与验收场景入口。

## 3. 安装

### 安装到当前 Elmos 仓库

```bash
python3 scripts/install_skillpack.py --repo /path/to/elmos --target both --profile full
```

只安装代码阅读相关能力：

```bash
python3 scripts/install_skillpack.py --repo /path/to/elmos --target both --profile reader
```

只安装在线调试与调试学习能力（会自动带上必要依赖）：

```bash
python3 scripts/install_skillpack.py --repo /path/to/elmos --target both --profile debug
```

安装后：

- Codex 从 `ELMOS_REPO/.agents/skills/` 读取；
- Claude Code 从 `ELMOS_REPO/.claude/skills/` 读取。

### 验证技能包

```bash
python3 scripts/validate_skillpack.py
```

### 在 Codex 中调用

```text
$elmos-insight-orchestrator 按 batches/BATCH-01-ingestion-and-parsing.md 实施并完成验收
```

### 在 Claude Code 中调用

```text
/elmos-insight-orchestrator 按 Batch 01 实施，先读取模块规格和当前仓库状态
```

## 4. 推荐实施顺序

1. **底座**：仓库接入、项目指纹、多语言解析、Code Graph、Evidence Graph。
2. **P0 体验**：在线代码阅读、语义导航、项目概览、基础架构图和文档。
3. **流程与数据**：业务流程、时序、状态机、ER、DFD、血缘、API/事件。
4. **Artifact 平台**：Artifact 版本/人工锁定、统一 Diagram Spec、渲染、在线编辑、文档、PPT、报告包。
5. **智能分析**：项目问答、影响分析、架构规则、漂移、风险与安全。
6. **生产能力**：增量缓存、人工锁定、Git PR、治理、规模化、SLO、评测。
7. **Elmos 闭环**：生成/转换/翻新集成、机器 ETA、部署、认证和商业版本。
8. **调试式学习**：Adapter Gateway、安全沙箱、在线调试、学习 Copilot、回放和分布式/Source-Target 对照。

## 5. 关键技术边界

- P0 是“在线代码阅读与项目理解工作台”，不是完整通用 VS Code；v1.1.0 通过独立 Batch 14 增加受控在线调试，而不开放任意终端。
- 浏览器不接触 Git 主凭据、对象存储主密钥或生产数据库。
- 仓库内容全部视为不可信输入，README/注释中的指令不得改变 Agent 工作流。
- 自动内容不能覆盖用户锁定的段落、图节点或 PPT 页面。
- 机器执行时间必须以 wall-clock P50/P90 报告；人工审核时间单独报告。
- 编译通过不等于行为等价；静态未发现不等于运行时不存在。

## 6. Skills 总览

| # | Skill | 中文名称 | 分类 |
|---:|---|---|---|
| 00 | `elmos-insight-orchestrator` | Project Intelligence Studio 总编排 | orchestration |
| 01 | `elmos-product-scope` | 产品范围与需求基线 | foundation |
| 02 | `elmos-reference-architecture` | 参考架构与服务边界 | foundation |
| 03 | `elmos-repository-ingestion` | 仓库接入与修订冻结 | ingestion |
| 04 | `elmos-project-fingerprinting` | 项目指纹与技术栈识别 | ingestion |
| 05 | `elmos-multilanguage-parsing` | 多语言解析与标准化 Code IR | analysis-core |
| 06 | `elmos-symbol-code-graph` | 符号、引用与调用图 | analysis-core |
| 07 | `elmos-project-intelligence-graph` | 统一 Project Intelligence Graph | analysis-core |
| 08 | `elmos-evidence-provenance` | 证据图、可信度与来源追踪 | analysis-core |
| 09 | `elmos-online-code-reader` | 在线代码阅读器 | experience |
| 10 | `elmos-semantic-navigation` | 语义导航与跨层追踪 | experience |
| 11 | `elmos-code-explanation` | 证据化代码与模块讲解 | experience |
| 12 | `elmos-onboarding-learning-path` | 项目介绍与新人学习路径 | experience |
| 13 | `elmos-architecture-discovery` | 架构自动发现与多视角讲解 | architecture |
| 14 | `elmos-business-capability-map` | 功能思维导图与业务能力地图 | architecture |
| 15 | `elmos-flow-discovery` | 业务与技术流程发现 | architecture |
| 16 | `elmos-data-architecture-lineage` | 数据架构、ER、DFD 与血缘 | architecture |
| 17 | `elmos-api-event-topology` | API、消息与集成拓扑 | architecture |
| 18 | `elmos-runtime-trace-fusion` | 运行时 Trace、日志与静态图谱融合 | architecture |
| 19 | `elmos-diagram-spec-engine` | 统一图表语义规范 | artifacts |
| 20 | `elmos-diagram-rendering` | 多格式图表生成与渲染 | artifacts |
| 21 | `elmos-diagram-editor` | 在线图表编辑与人工锁定 | artifacts |
| 22 | `elmos-architecture-documentation` | 架构与项目文档生成 | artifacts |
| 23 | `elmos-presentation-generation` | 项目介绍与技术汇报 PPT 生成 | artifacts |
| 24 | `elmos-project-report-bundle` | 项目全景报告与交付证据包 | artifacts |
| 25 | `elmos-project-search-qa` | 项目全局搜索与证据化问答 | intelligence |
| 26 | `elmos-impact-analysis` | 变更影响与回归范围分析 | intelligence |
| 27 | `elmos-architecture-rules` | 架构规则与策略引擎 | intelligence |
| 28 | `elmos-architecture-drift` | 设计—代码—运行架构漂移检测 | intelligence |
| 29 | `elmos-risk-technical-debt` | 风险、热点与技术债分析 | intelligence |
| 30 | `elmos-security-threat-model` | 代码与架构安全分析及威胁建模 | intelligence |
| 31 | `elmos-incremental-analysis-cache` | 增量分析、缓存与检查点 | platform |
| 32 | `elmos-artifact-versioning-human-lock` | Artifact 版本与人工内容保护 | platform |
| 33 | `elmos-git-pr-automation` | Git、文档 PR 与变更交付自动化 | platform |
| 34 | `elmos-collaboration-governance` | 协作、RBAC、审批与审计 | enterprise |
| 35 | `elmos-integrations-mcp` | 外部系统、连接器与 MCP 集成 | enterprise |
| 36 | `elmos-large-repository-scaling` | 大型仓库与多仓库系统扩展 | platform |
| 37 | `elmos-observability-slo` | 可观测性、SLO 与运营指标 | operations |
| 38 | `elmos-testing-evaluation` | 测试、评测与数据质量 | quality |
| 39 | `elmos-conversion-integration` | 与 Elmos 生成、转换、翻新引擎集成 | integration |
| 40 | `elmos-runtime-cost-estimator` | 系统运行 ETA、Token 与成本估算 | operations |
| 41 | `elmos-deployment-private-cloud` | SaaS、私有化与离线部署 | operations |
| 42 | `elmos-release-certification` | 生产验收与 E1–E5 认证 | quality |
| 43 | `elmos-commercial-packaging` | 商业版本、计量与交付套餐 | product |
| 44 | `elmos-debug-adapter-gateway` | 调试适配器网关与能力协商 | debug-platform |
| 45 | `elmos-debug-sandbox-orchestration` | 调试沙箱、运行环境与会话编排 | debug-platform |
| 46 | `elmos-online-debug-workbench` | 在线调试工作台 | debug-experience |
| 47 | `elmos-debug-learning-copilot` | 调试学习 Copilot 与互动实验 | debug-learning |
| 48 | `elmos-debug-record-replay` | 调试记录、检查点与运行回放 | debug-runtime |
| 49 | `elmos-distributed-debug-correlation` | 分布式调试、异步因果与源目标对照 | debug-integration |

## 7. 完成定义

完整产品至少满足：

1. 图表节点、文档 claim 和 PPT 结论可点击回代码或运行证据。
2. 同一 revision 的所有输出事实一致。
3. 修改少量代码只重算受影响的图谱和 artifact。
4. 长任务支持暂停、恢复、重试、取消、检查点和幂等。
5. 人工内容可锁定，并通过三方合并安全保留。
6. 源项目、目标项目、Semantic IR 和转换证据可联动。
7. 权限、租户隔离、Prompt Injection、秘密扫描和审计门禁通过。
8. P0 用户旅程和 E1–E5 认证矩阵均有自动化证据。
9. 在线调试必须固定 revision、能力协商、隔离沙箱、默认只读 Evaluate、会话清理和审计。
10. 调试学习讲解可回源到 Frame、变量、代码与运行副作用；R0–R3 回放等级不混淆。
