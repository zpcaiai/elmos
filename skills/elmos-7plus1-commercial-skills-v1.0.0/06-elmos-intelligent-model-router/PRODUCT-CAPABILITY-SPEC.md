# P06 产品能力规范：Elmos 智能模型、Provider 与成本路由

## 1. 产品定位

按任务、语言、框架、历史质量、上下文、工具、隐私、ZDR、预算、延迟、吞吐和可用性选择模型/Provider，并管理 fallback、hedging、shadow、cost 和 ETA。

**客户可感知价值：** 让不同环节使用最匹配的模型与 Provider，提升质量、稳定性和性价比，同时避免被单一供应商锁定。

## 2. 目标用户与场景

- 企业架构师与现代化负责人：需要大型仓库理解、迁移和可审计交付。
- 软件研发团队：需要从需求生成完整项目、自动验证与持续修复。
- 平台/DevOps/SRE：需要长任务恢复、资源治理、成本、SLA、灰度与回滚。
- 安全/合规/审计：需要最小权限、凭据隔离、证据链、SBOM 和数据治理。
- Elmos 内部能力团队：需要稳定公共合同、Benchmark、回归和知识复利。

## 3. 业务目标

- 构建实时模型/Provider Catalog：能力、价格、context、output、tool/schema/modalities、健康。
- 对任务进行 role/language/framework/repo-size/risk/context/privacy 分类。
- 实现硬约束过滤：数据政策、ZDR、BYOK、地区、预算、参数、量化、可用性。
- 引入 benchmark availability gate，验证榜单模型真实可路由且 Provider 可用。
- 利用 Elmos 历史 accuracy/completeness/test-pass/repair-rate/cost/latency 建立 task-fit。
- 实现多目标选择、fallback、circuit breaker、canary、shadow、hedging 和 model escalation。
- 提供长上下文 Global Completeness Auditor 与多模态 UI Verifier 专项路由。
- 对多轮工具调用聚合 token/cached/reasoning/cost，预测机器墙钟 ETA。

## 4. 非目标与产品边界

- 公开 benchmark 只作为先验，Elmos 自有任务历史与可用性 Gate 优先。
- 路由器不降低 P05 质量门；预算不足应阻断/降级范围而非偷偷降低验证。
- 隐私/ZDR/地区/数据政策是硬约束，不进入可被质量分数抵消的软排序。

## 5. 核心能力地图

| 组件 | 职责 | Capability ID |
| --- | --- | --- |
| Model/Provider Catalog | 模型、版本、能力、价格、上下文、模态、参数和 Provider endpoints。 | P06-C01 |
| Task Classifier | 角色、语言、框架、复杂度、规模、风险、时效、隐私与所需输出。 | P06-C02 |
| Hard Constraint Engine | ZDR、数据收集、地区、BYOK、max price、latency/throughput、参数。 | P06-C03 |
| Benchmark & Availability Gate | 外部榜单、模型 ID 解析、Provider 健康和实际可路由检查。 | P06-C04 |
| Historical Task-Fit Store | Elmos 真实任务质量、成本、修复、失败与置信区间。 | P06-C05 |
| Multi-objective Scorer | quality/completeness/reliability/cost/latency/cache/privacy risk。 | P06-C06 |
| Routing Execution Plane | order/fallback/circuit breaker/hedging/shadow/canary/escalation。 | P06-C07 |
| Long-context Audit Router | 把 Repository Graph/IR/Ledger/target/tests 送给大上下文审计角色。 | P06-C08 |
| Multimodal Router | 按 image/video/DOM/UI verification 能力选择模型。 | P06-C09 |
| Cost/Token/ETA Engine | 多轮总用量、缓存、价格、工具时间和机器 ETA。 | P06-C10 |
| Privacy & Data Policy Broker | 数据分类、redaction、provider policy、tenant opt-in/out。 | P06-C11 |
| Route Observability | 选择证据、健康、成本、质量反馈、fallback 和 drift。 | P06-C12 |

## 6. 关键用户旅程

### 6.1 新项目生成

1. 导入自然语言、多模态需求与商业约束。
2. 通过 P02/P03 建立需求、能力、架构与实施 DAG。
3. P04 调度专业 Agent，P01 负责可靠执行，P06 负责模型/Provider 路由。
4. P05 执行覆盖、差分、E2E、非功能与证据 Gate。
5. P00 返回系统墙钟 ETA、真实成本、交付物、风险、认证与回滚。
6. P07 只沉淀经过验证且授权的可复用知识。

### 6.2 跨语言/跨框架/跨库转换

1. 固定源仓库 revision 和运行环境，P02 扫描并建立 Repository Graph/IR/Ledger。
2. P03 选择规则、生成 Target IR、代码、迁移与双运行计划。
3. P04 分任务并行实施；Generator 与 Verifier 分权。
4. P05 在相同场景下比较源/目标行为，发现 gap 后进入 Repair Loop。
5. 只有 Evidence Gate 通过才允许切流、合并或认证。

## 7. 商业版本建议

| 版本 | 能力范围 | 限制 |
| --- | --- | --- |
| Community/Developer | 单用户、本地仓库、基础运行与报告 | 无企业 SLA；默认不含生产 cutover。 |
| Team | 团队项目、共享规则、并发、CI/PR、成本与质量 Dashboard | 组织内知识隔离。 |
| Enterprise | 多租户、SSO/RBAC、私有部署、BYOK/ZDR、审计、SLA、E1–E5 | 需客户安全与数据政策配置。 |
| Regulated | 金融/医疗/工业等专用基线、双人审批、WORM 证据、区域部署 | 按场景认证，不承诺无限通用。 |

## 8. 成功指标

- **结果指标：** Requirement coverage、Capability coverage、Behavioral equivalence、Critical unknown gaps、人工介入率。
- **运行指标：** 成功恢复率、重复副作用率、任务完成时长、模型/工具成本、缓存命中与 Provider fallback。
- **商业指标：** 项目毛利、交付周期、试点转付费、复购、SLA 违约、支持成本。
- **知识复利：** trusted rules 数量、复用率、规则命中后的质量/成本改善、bad-rule escape rate。

指标必须带 scenario/规模/版本/样本量/置信区间；不发布无上下文的统一“准确率”。

## 9. 硬不变量

- 先硬约束过滤，再质量/成本排序；无合格候选则明确失败。
- 路由决策记录候选、过滤理由、评分、策略版本、实时健康与最终选择。
- Provider fallback 不得改变数据保留/地区/参数/工具/Schema 要求。
- benchmark 结果必须绑定来源、日期、模型实体解析和当前可用性。
- 实验/stealth/preview 模型默认不可处理机密仓库，除非策略明确批准。
- 同一 run 中 prompt-cache 敏感的工具表与前缀保持稳定，动态开放工具而非反复重构。

## 10. 依赖与集成

- 上游依赖：P00, P01, P05。
- 外部 Harness/SDK 均通过 P01/P06 Adapter；上游实现细节不得成为本包持久数据格式。
- 任何完成/发布/认证均依赖 P05 GateDecision。
