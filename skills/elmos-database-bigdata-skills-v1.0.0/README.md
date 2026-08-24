# Elmos Database Intelligence & Big Data Project Generator Skills

版本：**1.0.0**  
发布日期：**2026-08-19**  
技能数量：**46**  
用途：供 **Codex / Claude Code / Elmos Agent Runtime** 从需求出发，完成数据库类型选择、多模数据库组合设计、大数据架构选择、完整仓库生成、测试、自修复和证据化交付。

## 1. 这套 Skills 解决什么问题

Elmos 不应只根据“流行度”或模型记忆选择数据库，也不应为整个系统强行指定唯一数据库。该包把数据需求拆成不同角色：

- **权威事务存储（System of Record）**
- **缓存与低延迟 Serving**
- **全文检索与向量检索**
- **图关系、时序与宽列数据**
- **实时 OLAP、离线数仓和湖仓**
- **事件总线、CDC、批处理和流处理**
- **联邦查询、目录、血缘、质量和治理**

每个角色先经过硬约束过滤，再进行多目标排序、复杂度惩罚、敏感性分析、项目级基准验证和 ADR 记录。最终输出可以是单库方案，也可以是有明确权威来源、同步契约和重建能力的多模组合。

## 2. 对大数据分类的规范化

用户给出的分类被保留并扩展为 Elmos 可执行模型：

| 观察维度 | Elmos 中的可执行表示 |
|---|---|
| 数据价值流 | 采集 → 存储 → 处理 → 治理 → 服务 → 可视化 → 反馈 |
| 系统架构 | Batch、Streaming、Lambda、Kappa、Unified、Lakehouse、Federated |
| 业务场景 | 数仓、实时分析、画像、推荐、风控、IoT、日志、知识检索、治理、迁移 |
| 数据存储范式 | OLTP、OLAP、HTAP、Lake、Warehouse、Lakehouse、Search、Graph、Vector、Time-series |
| 组织与治理 | 集中平台、Data Mesh 领域所有权、Data Fabric 覆盖层 |

两个重要约束：

1. **Unified** 在本包中表示用同一数据流语义处理 bounded 与 unbounded 数据，但仍需分别验证运行模式、状态、checkpoint 和 sink 语义。
2. **Data Fabric** 不是一种单一数据库或存储格式，而是跨异构数据源的元数据、策略、发现、血缘、质量和自动化覆盖层。

## 3. 端到端架构

```mermaid
flowchart LR
    A[需求/PRD/代码/样例] --> B[Workload Requirement IR]
    B --> C[数据与查询画像]
    C --> D[技术能力注册表]
    D --> E[硬约束求解]
    E --> F[MCDA + Pareto + 敏感性]
    F --> G[多模数据库组合]
    G --> H[基准/容量/TCO]
    H --> I[ADR 与架构基线]
    I --> J[Batch/Stream/Lakehouse/OLAP/Fabric 生成器]
    J --> K[代码 + IaC + 测试 + 文档 + Dashboard]
    K --> L[质量/性能/安全/恢复验证]
    L --> M[自动修复与回归]
    M --> N[E1-E5 证据与生产认证]
```

## 4. 数据库选择算法

### 4.1 Requirement IR

Elmos 必须显式抽取：

- 数据量、峰值吞吐、增长、对象大小、保留周期和冷热分层；
- P50/P95/P99、freshness、可用性、RPO、RTO；
- 事务边界、一致性、隔离、顺序、幂等和重放；
- 查询形态、连接、聚合、全文、向量、图、时序和地理空间；
- 数据驻留、PII、审计、租户隔离、预算和团队运维成熟度。

未知信息必须保存为 `unknown`、范围或带置信度的假设，不能自动当作零。

### 4.2 Hard Constraint Solver

安全、合规、部署、许可证、事务、数据类型、容量、RPO/RTO 和连接器兼容性先做硬过滤。无解时生成最小冲突集合，不能为了得到结果而静默放宽约束。

### 4.3 Multi-Criteria Ranking

可行候选再按性能、可靠性、成本、生态、运维、迁移、锁定和团队能力进行多目标排序，同时执行：

- Pareto 前沿；
- 多模组合复杂度惩罚；
- 权重扰动和敏感性分析；
- 缺失证据的置信区间传播；
- 历史生产结果的版本化反馈。

### 4.4 Polyglot Persistence Guardrail

每个业务域只有一个权威写入来源。缓存、搜索、向量、图、OLAP 和湖仓必须被定义为派生角色，并具备 CDC/Outbox、Schema 契约、幂等、删除传播、重建和降级路径。不能因“技术先进”而无上限增加组件。

### 4.5 Evidence and Benchmark

通用产品排行榜不能替代项目基准。关键角色必须用接近真实的数据分布、热点、并发和查询进行测试，并记录环境、版本、配置、P95/P99、资源、恢复时间和单位成本。

## 5. 大数据项目生成能力

Elmos 可生成：

- 数据采集、CDC、消息、Schema Registry 和事件契约；
- Spark/Flink/Beam/dbt 批处理；
- Flink/Kafka Streams/Structured Streaming/Beam 流处理；
- Iceberg/Delta/Hudi 湖仓；
- Trino 联邦查询；
- ClickHouse/Doris/StarRocks/Druid/Pinot/云数仓 Serving；
- 维度建模、Data Vault、SCD、语义指标；
- OpenLineage、OpenMetadata/DataHub/Atlas 目录与血缘；
- Data Contract、质量测试、异常检测和 Data SLO；
- Airflow/Dagster 数据编排与 Temporal 的 Elmos 长任务控制；
- Feature Store、训练数据、在线特征和 point-in-time join；
- ECharts/Superset/Grafana/Tableau/Power BI 适配层；
- Docker、Kubernetes、Helm、Terraform、GitOps；
- 功能、数据、性能、压力、UI/API、安全、恢复和成本测试；
- 自动诊断、低风险修复、回归和 E1–E5 生产证据。

## 6. 内置项目模板

1. 离线企业数仓
2. 实时计算与实时分析
3. 实时用户画像 / Customer 360
4. 推荐系统
5. IoT / 工业时序
6. 实时风控与反欺诈
7. 日志、指标、Trace 与安全分析
8. 数据治理 / Data Catalog / Data Fabric
9. 向量检索与知识分析
10. CDC 迁移与旧平台现代化

## 7. 生成项目的标准目录

```text
generated-project/
├── apps/                    # API、管理端、大屏或业务应用
├── contracts/               # Avro/Protobuf/JSON Schema/Data Contract
├── pipelines/
│   ├── batch/
│   ├── stream/
│   ├── ingestion/
│   └── maintenance/
├── models/                  # 逻辑模型、维度模型、语义指标、特征
├── platform/                # Catalog、Lineage、Quality、Governance
├── infra/
│   ├── docker/
│   ├── helm/
│   ├── terraform/
│   └── policies/
├── observability/           # Metrics、Logs、Trace、Data SLO、Dashboards
├── tests/
│   ├── unit/
│   ├── contract/
│   ├── data-quality/
│   ├── integration/
│   ├── e2e/
│   ├── performance/
│   ├── chaos/
│   └── security/
├── docs/                    # ADR、架构、数据流、runbook、成本、ETA
└── evidence/                # E1-E5 证据与生产认证
```

## 8. 与 Elmos 现有基础设施的集成约束

- 每个任务绑定 `tenant_id`、`task_id`、`idempotency_key` 和不可变输入快照。
- 每个账号最多同时执行 **3 个任务**；其余进入公平调度队列。
- 任务节点的输入、输出、状态、日志、模型调用、成本和恢复点异步持久化。
- 客户端网络断开不终止服务端任务；服务端异常后从最近幂等节点恢复。
- 内容寻址缓存按租户隔离；原始敏感数据默认不进入缓存或模型上下文。
- 模型网关可按任务复杂度、质量和价格自动选择，也允许用户限定模型。
- ETA 必须分成：
  - 系统自主生成/转换的机器 wall-clock 时间；
  - 人类等价工作量；
  - 人工审批或 HITL 等待；
  - 不能把上述三项混成“开发周期”。

## 9. 安装

```bash
python3 scripts/install_skillpack.py install --target both --profile full
```

只安装数据库智能选型：

```bash
python3 scripts/install_skillpack.py install --target codex --profile database
```

只安装大数据核心：

```bash
python3 scripts/install_skillpack.py install --target claude --profile bigdata-core
```

冲突默认失败。只有明确使用 `--force` 才会原子替换由本包管理的同名技能。

## 10. 验证

```bash
python3 -m pip install -r requirements-validation.txt
python3 scripts/validate_skillpack.py
python3 -m unittest discover -s tests -v
python3 tools/database_selector.py examples/realtime-user-profile/requirements.json
python3 tools/architecture_selector.py examples/realtime-user-profile/requirements.json
```

## 11. 可运行样例

`examples/` 包含三套经过 Schema 校验且可由工具重新生成的决策结果：

- `realtime-user-profile`：实时画像、流式处理、湖仓与低延迟 Serving；
- `offline-lakehouse`：离线数仓、湖仓、联邦查询与 Data Fabric 覆盖层；
- `iot-realtime`：工业遥测、时序 Serving、流处理、历史湖仓与实时分析。

每个样例包括 `requirements.json`、`database-decision.json`、`architecture-decision.json` 和 `cost-and-eta.json`。

## 12. 可信声明边界

本包提供的是可执行的生成规范、选择器、Schema、样例和验证器。Catalog 中出现某项技术，不等于该技术的 provider integration 已在目标仓库实现或通过生产验证。只有经过目标仓库的连接、迁移、权限、性能、恢复和端到端测试，适配器状态才可从 `catalog-only` 升级为 `verified-adapter`。
