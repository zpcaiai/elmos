# Stable Task Checklist

Task IDs are stable within major version 1. They can be persisted in Elmos task-node tables for progress, recovery, cost and evidence.

## elmos-data-requirement-intake

- [ ] **REQ-001** — 识别业务域、数据生产者、消费者、实体、事件、数据所有权和租户边界。
- [ ] **REQ-002** — 量化 Volume、Velocity、Variety、Veracity、Value，记录当前值、峰值、增长率和置信区间。
- [ ] **REQ-003** — 提取读写模式、事务边界、查询形态、热点、保留、归档和删除要求。
- [ ] **REQ-004** — 显式记录 P50/P95/P99、吞吐、可用性、RPO、RTO、freshness、一致性和隔离级别。
- [ ] **REQ-005** — 识别 PII、驻留、审计、预算、部署和运维约束；未知值标为 unknown/range/assumption。
- [ ] **REQ-006** — 按 JSON Schema 输出 IR、冲突、缺口、保守假设和下一阶段输入。
- [ ] **REQ-007** — 固化输入和授权范围。
- [ ] **REQ-008** — 验证机器可读输出。
- [ ] **REQ-009** — 记录证据、成本、风险和回退。
- [ ] **REQ-010** — 运行对应测试并更新完成状态。
- [ ] **REQ-011** — 生成交付与未覆盖项。

## elmos-workload-profiler

- [ ] **PROF-001** — 建立只读、最小权限、限流、超时和抽样边界，禁止破坏性生产访问。
- [ ] **PROF-002** — 计算行数、字节、增长、基数、空值、重复、分位数、分布和字段相关性。
- [ ] **PROF-003** — 识别分区倾斜、热键、热点租户、宽行、超大对象、小文件和高基数字段。
- [ ] **PROF-004** — 分析查询过滤、连接、排序、聚合、扫描量、并发、缓存命中和慢查询。
- [ ] **PROF-005** — 分析事件时间、乱序、迟到、水位、重放范围和状态大小。
- [ ] **PROF-006** — 区分样本推断与真实监控值，输出脱敏画像、时间窗和置信度。
- [ ] **PROF-007** — 固化输入和授权范围。
- [ ] **PROF-008** — 验证机器可读输出。
- [ ] **PROF-009** — 记录证据、成本、风险和回退。
- [ ] **PROF-010** — 运行对应测试并更新完成状态。
- [ ] **PROF-011** — 生成交付与未覆盖项。

## elmos-database-capability-registry

- [ ] **REG-001** — 按 technology_kind、storage_model、workload_role、deployment_model 建立规范条目。
- [ ] **REG-002** — 记录事务、一致性、索引、分区、扩缩容、备份、CDC、查询、生态和治理能力。
- [ ] **REG-003** — 区分声明能力、已实现适配器、已验证版本和仅规划支持。
- [ ] **REG-004** — 为能力记录官方证据、抓取日期、版本范围、置信度和过期时间。
- [ ] **REG-005** — 记录许可证、托管/自建、区域、国产化、离线部署、运维复杂度和锁定风险。
- [ ] **REG-006** — 支持离线快照、可插拔 provider、版本绑定和完整性/过期检查。
- [ ] **REG-007** — 固化输入和授权范围。
- [ ] **REG-008** — 验证机器可读输出。
- [ ] **REG-009** — 记录证据、成本、风险和回退。
- [ ] **REG-010** — 运行对应测试并更新完成状态。
- [ ] **REG-011** — 生成交付与未覆盖项。

## elmos-database-constraint-filter

- [ ] **FILTER-001** — 把驻留、许可证、部署、语言、事务、一致性、RPO/RTO 转为硬约束。
- [ ] **FILTER-002** — 把容量、对象限制、分区键、索引、状态大小和类型兼容转为技术约束。
- [ ] **FILTER-003** — 按 system-of-record、cache、search、analytics、lakehouse、graph、vector 分角色过滤。
- [ ] **FILTER-004** — 用规则引擎或 CP-SAT 求解可行组合，而不是只选单个产品。
- [ ] **FILTER-005** — 为淘汰项输出约束、证据和可解除条件；无解时生成最小冲突集合。
- [ ] **FILTER-006** — 固定输入、规则和注册表快照，保证结果可重放。
- [ ] **FILTER-007** — 固化输入和授权范围。
- [ ] **FILTER-008** — 验证机器可读输出。
- [ ] **FILTER-009** — 记录证据、成本、风险和回退。
- [ ] **FILTER-010** — 运行对应测试并更新完成状态。
- [ ] **FILTER-011** — 生成交付与未覆盖项。

## elmos-database-mcda-ranker

- [ ] **RANK-001** — 规范化性能、可靠性、成本、可运维性、生态、迁移难度和锁定风险。
- [ ] **RANK-002** — 硬约束与软偏好分离；软权重来自项目类型和用户偏好并可审计。
- [ ] **RANK-003** — 计算加权效用、Pareto 前沿和复杂度惩罚，防止无必要的多技术堆叠。
- [ ] **RANK-004** — 缺失数据使用区间并传播到总分置信区间。
- [ ] **RANK-005** — 运行权重扰动/蒙特卡洛敏感性，识别排名稳健度。
- [ ] **RANK-006** — 输出 Top-N、角色、优势、风险、置信度和重新评估阈值。
- [ ] **RANK-007** — 固化输入和授权范围。
- [ ] **RANK-008** — 验证机器可读输出。
- [ ] **RANK-009** — 记录证据、成本、风险和回退。
- [ ] **RANK-010** — 运行对应测试并更新完成状态。
- [ ] **RANK-011** — 生成交付与未覆盖项。

## elmos-polyglot-persistence-planner

- [ ] **POLY-001** — 为每个 bounded context 指定唯一 system of record。
- [ ] **POLY-002** — 把缓存、搜索、向量、图、时序、OLAP、湖仓定义为明确派生角色。
- [ ] **POLY-003** — 优先一库多能力，只有 SLO/数据模型差异可量化时才新增技术。
- [ ] **POLY-004** — 为派生存储设计 CDC/Outbox/事件/批同步，明确延迟、顺序、幂等、删除和重建。
- [ ] **POLY-005** — 计算组合的运维复杂度、故障域、复制成本和一致性风险。
- [ ] **POLY-006** — 生成缓存/搜索/分析故障时的降级路径和禁止的跨库事务模式。
- [ ] **POLY-007** — 固化输入和授权范围。
- [ ] **POLY-008** — 验证机器可读输出。
- [ ] **POLY-009** — 记录证据、成本、风险和回退。
- [ ] **POLY-010** — 运行对应测试并更新完成状态。
- [ ] **POLY-011** — 生成交付与未覆盖项。

## elmos-data-architecture-adr

- [ ] **ADR-001** — 记录问题、上下文、硬约束、软偏好、候选、选择和拒绝原因。
- [ ] **ADR-002** — 引用注册表证据和基准快照，不复制未经验证的营销结论。
- [ ] **ADR-003** — 记录数据流、所有权、一致性、故障域、RPO/RTO 和成本范围。
- [ ] **ADR-004** — 列出假设、未知、验证任务、回退方案和重新评估触发器。
- [ ] **ADR-005** — 生成机器可读 decision-ledger，绑定需求、规则、模型和代码版本。
- [ ] **ADR-006** — 支持 supersede，保持历史决策不可变；进入生成前做 readiness check。
- [ ] **ADR-007** — 固化输入和授权范围。
- [ ] **ADR-008** — 验证机器可读输出。
- [ ] **ADR-009** — 记录证据、成本、风险和回退。
- [ ] **ADR-010** — 运行对应测试并更新完成状态。
- [ ] **ADR-011** — 生成交付与未覆盖项。

## elmos-database-benchmark-harness

- [ ] **BENCH-001** — 从真实查询、分布、热点、并发和增长模型生成 workload pack。
- [ ] **BENCH-002** — 固定硬件、版本、配置、规模、预热、压缩和重复次数。
- [ ] **BENCH-003** — 测量写入、点查、范围、连接、聚合、更新、删除、并发和混合负载。
- [ ] **BENCH-004** — 记录 P50/P95/P99、吞吐、错误、资源、放大、恢复时间和单位成本。
- [ ] **BENCH-005** — 注入节点、网络、磁盘、broker、checkpoint、元数据故障并验证语义。
- [ ] **BENCH-006** — 检测缓存偏差、数据过小、索引/预聚合不等价；保留原始结果和置信区间。
- [ ] **BENCH-007** — 固化输入和授权范围。
- [ ] **BENCH-008** — 验证机器可读输出。
- [ ] **BENCH-009** — 记录证据、成本、风险和回退。
- [ ] **BENCH-010** — 运行对应测试并更新完成状态。
- [ ] **BENCH-011** — 生成交付与未覆盖项。

## elmos-database-cost-capacity-planner

- [ ] **COST-001** — 计算热/温/冷数据及副本、索引、WAL、快照、临时空间和压缩后的容量。
- [ ] **COST-002** — 按峰值、突发、重建、compaction、backfill、故障降级计算 CPU/内存/磁盘/网络。
- [ ] **COST-003** — 区分 dev/test/staging/prod/dr，避免单环境成本冒充总成本。
- [ ] **COST-004** — 比较托管、自建、云、混合和本地的人力、许可证、流量与机会成本。
- [ ] **COST-005** — 建立基线、增长、峰值、灾难场景，计算每百万事件、每 TB、每查询、每租户成本。
- [ ] **COST-006** — 设置预算 guardrail、自动扩缩上下限、异常告警和价格 as-of 时间。
- [ ] **COST-007** — 固化输入和授权范围。
- [ ] **COST-008** — 验证机器可读输出。
- [ ] **COST-009** — 记录证据、成本、风险和回退。
- [ ] **COST-010** — 运行对应测试并更新完成状态。
- [ ] **COST-011** — 生成交付与未覆盖项。

## elmos-database-schema-physical-design

- [ ] **SCHEMA-001** — 建立领域模型、业务键、主键、唯一性、引用完整性和租户键。
- [ ] **SCHEMA-002** — 按 OLTP、文档、时序、图、向量、搜索、OLAP 角色生成物理模型。
- [ ] **SCHEMA-003** — 依据过滤、连接、排序、聚合和写放大设计索引、投影、物化视图。
- [ ] **SCHEMA-004** — 依据规模、倾斜和局部性设计分区、分片、路由键与再平衡。
- [ ] **SCHEMA-005** — 设计压缩、编码、文件大小、compaction、TTL、冷热分层和归档。
- [ ] **SCHEMA-006** — 生成兼容 schema 演进、DDL、迁移、数据字典、图和 explain 校验。
- [ ] **SCHEMA-007** — 固化输入和授权范围。
- [ ] **SCHEMA-008** — 验证机器可读输出。
- [ ] **SCHEMA-009** — 记录证据、成本、风险和回退。
- [ ] **SCHEMA-010** — 运行对应测试并更新完成状态。
- [ ] **SCHEMA-011** — 生成交付与未覆盖项。

## elmos-database-ha-dr

- [ ] **HADR-001** — 为每个数据角色定义副本、共识、故障转移和读写路由语义。
- [ ] **HADR-002** — 区分同 AZ、跨 AZ、跨区域、离线备份和逻辑错误恢复。
- [ ] **HADR-003** — 设计全量、增量、WAL/binlog、快照、PITR、对象锁和备份加密。
- [ ] **HADR-004** — 定义 failover/failback、split-brain 防护、fencing 和连接切换。
- [ ] **HADR-005** — 定期 restore drill，验证行数、校验和、业务不变量和下游重建。
- [ ] **HADR-006** — 为缓存、搜索、湖仓元数据和流状态分别生成恢复 runbook。
- [ ] **HADR-007** — 固化输入和授权范围。
- [ ] **HADR-008** — 验证机器可读输出。
- [ ] **HADR-009** — 记录证据、成本、风险和回退。
- [ ] **HADR-010** — 运行对应测试并更新完成状态。
- [ ] **HADR-011** — 生成交付与未覆盖项。

## elmos-database-security-multitenancy

- [ ] **DBSEC-001** — 比较数据库/schema/table/row/column/encryption-domain 隔离级别。
- [ ] **DBSEC-002** — 按租户规模、噪声邻居、迁移和成本选择共享库、独立 schema、独立库或混合模式。
- [ ] **DBSEC-003** — 定义服务身份、最小权限、短期凭据、轮换、break-glass 和 secrets broker。
- [ ] **DBSEC-004** — 实现传输、静态、备份和字段级加密、tokenization、masking。
- [ ] **DBSEC-005** — 定义 RLS/ABAC/RBAC、管理面/数据面隔离和跨租户查询禁止规则。
- [ ] **DBSEC-006** — 验证注入、越权、旁路连接、备份泄漏、缓存和统计侧信道。
- [ ] **DBSEC-007** — 固化输入和授权范围。
- [ ] **DBSEC-008** — 验证机器可读输出。
- [ ] **DBSEC-009** — 记录证据、成本、风险和回退。
- [ ] **DBSEC-010** — 运行对应测试并更新完成状态。
- [ ] **DBSEC-011** — 生成交付与未覆盖项。

## elmos-database-migration-modernization

- [ ] **MIG-001** — 盘点 DDL、SQL、存储过程、触发器、扩展、字符集、时间语义和驱动依赖。
- [ ] **MIG-002** — 生成类型、DDL、查询与行为差异映射，标记不可自动转换项。
- [ ] **MIG-003** — 设计全量快照、增量 CDC、校验水位、重放、幂等和断点续传。
- [ ] **MIG-004** — 优先 Outbox/CDC/双读或影子流量，避免不可控应用双写。
- [ ] **MIG-005** — 执行行数、校验和、业务不变量、结果、性能和故障语义差分。
- [ ] **MIG-006** — 按租户/表/分片/流量渐进切换，保存节点进度、成本、证据和回退点。
- [ ] **MIG-007** — 固化输入和授权范围。
- [ ] **MIG-008** — 验证机器可读输出。
- [ ] **MIG-009** — 记录证据、成本、风险和回退。
- [ ] **MIG-010** — 运行对应测试并更新完成状态。
- [ ] **MIG-011** — 生成交付与未覆盖项。

## elmos-bigdata-project-classifier

- [ ] **CLASS-001** — 按采集、存储、处理、治理、服务、可视化和反馈闭环拆解价值流。
- [ ] **CLASS-002** — 识别离线数仓、实时计算、推荐、画像、风控、IoT、日志、搜索、ML、治理场景。
- [ ] **CLASS-003** — 识别 OLTP、OLAP、HTAP、湖、仓、湖仓、联邦和派生存储角色。
- [ ] **CLASS-004** — 识别 bounded/unbounded、事件时间、低延迟、回放和批流一致性。
- [ ] **CLASS-005** — 识别集中平台、Data Mesh 领域所有权和 Data Fabric 元数据覆盖层。
- [ ] **CLASS-006** — 允许多类型组合，输出主/次类型、组合原因和必需/可选/禁止能力。
- [ ] **CLASS-007** — 固化输入和授权范围。
- [ ] **CLASS-008** — 验证机器可读输出。
- [ ] **CLASS-009** — 记录证据、成本、风险和回退。
- [ ] **CLASS-010** — 运行对应测试并更新完成状态。
- [ ] **CLASS-011** — 生成交付与未覆盖项。

## elmos-bigdata-pattern-selector

- [ ] **PATTERN-001** — 批处理用于高吞吐、分钟至天级 SLA、复杂历史重算和稳定报表。
- [ ] **PATTERN-002** — 流式用于持续事件、秒/亚秒响应、状态计算、CEP 和实时特征。
- [ ] **PATTERN-003** — Kappa 只在日志可重放、流逻辑可表达历史且保留成本可接受时选择。
- [ ] **PATTERN-004** — Lambda 只在批层与实时层确有不同语义且双维护成本可接受时选择。
- [ ] **PATTERN-005** — 统一流批指同一语义处理 bounded/unbounded，仍需明确运行模式与 sink 语义。
- [ ] **PATTERN-006** — 湖仓用于开放表和多引擎历史；联邦用于跨源/过渡；Data Fabric 可叠加任意模式。
- [ ] **PATTERN-007** — 固化输入和授权范围。
- [ ] **PATTERN-008** — 验证机器可读输出。
- [ ] **PATTERN-009** — 记录证据、成本、风险和回退。
- [ ] **PATTERN-010** — 运行对应测试并更新完成状态。
- [ ] **PATTERN-011** — 生成交付与未覆盖项。

## elmos-ingestion-connector-planner

- [ ] **INGEST-001** — 为每个源选择 snapshot、incremental、CDC、polling、webhook、stream、file-drop 或 API。
- [ ] **INGEST-002** — 评估源端负载、限流、窗口、分页、断点、日志保留和 schema 获取。
- [ ] **INGEST-003** — 选择 Debezium、Kafka Connect、Flink CDC、DataX、SeaTunnel、NiFi 或定制适配器。
- [ ] **INGEST-004** — 定义 offset、水位、幂等键、文件原子性、重复检测和断点续传。
- [ ] **INGEST-005** — 定义 Avro/Protobuf/JSON/Parquet、压缩和 Schema Registry 策略。
- [ ] **INGEST-006** — 生成 quarantine、DLQ、回放、审计、租户隔离、健康检查和故障测试。
- [ ] **INGEST-007** — 固化输入和授权范围。
- [ ] **INGEST-008** — 验证机器可读输出。
- [ ] **INGEST-009** — 记录证据、成本、风险和回退。
- [ ] **INGEST-010** — 运行对应测试并更新完成状态。
- [ ] **INGEST-011** — 生成交付与未覆盖项。

## elmos-cdc-event-backbone

- [ ] **CDC-001** — 在原生日志 CDC、Outbox、应用事件和轮询之间按可靠性与侵入性选择。
- [ ] **CDC-002** — 定义 snapshot→streaming 一致水位、offset、复制槽/binlog 保留和恢复。
- [ ] **CDC-003** — 设计 topic/stream、partition key、ordering domain、retention、compaction 和租户隔离。
- [ ] **CDC-004** — 定义 event envelope、业务键、schema id、source position、event time、trace/idempotency id。
- [ ] **CDC-005** — 设置 backward/forward/full 兼容和 CI 检查；处理重复、乱序、删除、DDL、事务边界和 DLQ。
- [ ] **CDC-006** — 消费者采用事务、幂等 upsert 或去重；重放与重建按租户和范围受控。
- [ ] **CDC-007** — 固化输入和授权范围。
- [ ] **CDC-008** — 验证机器可读输出。
- [ ] **CDC-009** — 记录证据、成本、风险和回退。
- [ ] **CDC-010** — 运行对应测试并更新完成状态。
- [ ] **CDC-011** — 生成交付与未覆盖项。

## elmos-batch-processing-generator

- [ ] **BATCH-001** — 选择 Spark SQL/DataFrame、Flink Batch、Beam 或数据库内 ELT；遗留 MapReduce 仅作兼容。
- [ ] **BATCH-002** — 生成分层 pipeline、显式输入输出契约、分区裁剪、谓词下推和可复用转换。
- [ ] **BATCH-003** — 为作业定义 full refresh、incremental、merge、watermark 和 backfill。
- [ ] **BATCH-004** — 使用 staging、atomic commit、snapshot 或事务表格式保证幂等提交。
- [ ] **BATCH-005** — 处理小文件、倾斜、shuffle、spill、资源隔离和并发调度。
- [ ] **BATCH-006** — 生成质量、单元、集成、回归、性能、lineage、监控和失败恢复。
- [ ] **BATCH-007** — 固化输入和授权范围。
- [ ] **BATCH-008** — 验证机器可读输出。
- [ ] **BATCH-009** — 记录证据、成本、风险和回退。
- [ ] **BATCH-010** — 运行对应测试并更新完成状态。
- [ ] **BATCH-011** — 生成交付与未覆盖项。

## elmos-stream-processing-generator

- [ ] **STREAM-001** — 按延迟、状态、生态和团队选择 Flink、Kafka Streams、Structured Streaming 或 Beam runner。
- [ ] **STREAM-002** — 定义 event/processing time、watermark、allowed lateness、窗口、触发器和迟到侧输出。
- [ ] **STREAM-003** — 设计 keyed state、TTL、backend、checkpoint、savepoint、升级兼容和状态预算。
- [ ] **STREAM-004** — 处理乱序、重复、重平衡、背压、热点 key、广播状态和外部维表。
- [ ] **STREAM-005** — 为 sink 选择事务、两阶段提交、幂等 upsert 或去重。
- [ ] **STREAM-006** — 生成重放、恢复、升级/回滚和覆盖水位、迟到、故障、批流对比的测试。
- [ ] **STREAM-007** — 固化输入和授权范围。
- [ ] **STREAM-008** — 验证机器可读输出。
- [ ] **STREAM-009** — 记录证据、成本、风险和回退。
- [ ] **STREAM-010** — 运行对应测试并更新完成状态。
- [ ] **STREAM-011** — 生成交付与未覆盖项。

## elmos-lakehouse-generator

- [ ] **LAKE-001** — 在 Iceberg、Delta Lake、Hudi 中按引擎生态、更新模式和治理要求选择。
- [ ] **LAKE-002** — 设计 object store、catalog、namespace、warehouse、权限和多环境隔离。
- [ ] **LAKE-003** — 采用 Parquet/ORC/Avro，设计文件大小、排序、分区、聚簇和统计。
- [ ] **LAKE-004** — 定义 append/upsert/merge/delete、snapshot、time travel、branch/tag 和并发提交。
- [ ] **LAKE-005** — 生成 compaction、小文件重写、元数据清理、过期快照和 orphan file 清理。
- [ ] **LAKE-006** — 支持批回填和流写入，验证多引擎兼容、分层、质量、血缘、安全和恢复。
- [ ] **LAKE-007** — 固化输入和授权范围。
- [ ] **LAKE-008** — 验证机器可读输出。
- [ ] **LAKE-009** — 记录证据、成本、风险和回退。
- [ ] **LAKE-010** — 运行对应测试并更新完成状态。
- [ ] **LAKE-011** — 生成交付与未覆盖项。

## elmos-warehouse-olap-serving

- [ ] **OLAP-001** — 区分离线报表、交互 BI、实时分析、客户嵌入分析和高并发 API。
- [ ] **OLAP-002** — 在云数仓、ClickHouse、Doris、StarRocks、Druid、Pinot、Trino 等角色中筛选。
- [ ] **OLAP-003** — 设计星型/雪花/宽表/明细/聚合、物化视图和语义层。
- [ ] **OLAP-004** — 规划 ingestion、更新删除、分区、排序/主键、分桶、副本和冷热层。
- [ ] **OLAP-005** — 设计资源组、并发、超时、缓存和 noisy-neighbor 隔离。
- [ ] **OLAP-006** — 用代表查询验证扫描、join、聚合、尾延迟、写查并发，并提供降级。
- [ ] **OLAP-007** — 固化输入和授权范围。
- [ ] **OLAP-008** — 验证机器可读输出。
- [ ] **OLAP-009** — 记录证据、成本、风险和回退。
- [ ] **OLAP-010** — 运行对应测试并更新完成状态。
- [ ] **OLAP-011** — 生成交付与未覆盖项。

## elmos-federated-query-data-fabric

- [ ] **FED-001** — 识别适合虚拟访问与必须物化的数据，避免把联邦查询当无限性能层。
- [ ] **FED-002** — 选择 Trino/等价引擎并验证谓词、聚合、join、limit 下推和写能力。
- [ ] **FED-003** — 设计 catalog、namespace、身份传递、行列权限、masking 和跨域审计。
- [ ] **FED-004** — 建立缓存、物化、结果复用和异步导出，同时标明新鲜度。
- [ ] **FED-005** — 估算跨源 join 的数据移动、网络、源端负载、失败和成本。
- [ ] **FED-006** — 以 metadata/lineage/policy/discovery/quality/automation 构建 Data Fabric 覆盖层。
- [ ] **FED-007** — 固化输入和授权范围。
- [ ] **FED-008** — 验证机器可读输出。
- [ ] **FED-009** — 记录证据、成本、风险和回退。
- [ ] **FED-010** — 运行对应测试并更新完成状态。
- [ ] **FED-011** — 生成交付与未覆盖项。

## elmos-data-modeling-semantic-layer

- [ ] **MODEL-001** — 识别事实、维度、粒度、业务键、事件和度量，先定义业务语义。
- [ ] **MODEL-002** — 按变化频率、审计和团队选择 3NF、星型、雪花、Data Vault、宽表或混合。
- [ ] **MODEL-003** — 定义 SCD、有效/系统时间、迟到维度和回溯修正。
- [ ] **MODEL-004** — 明确 raw/detail/summary/serving 责任，禁止无价值层级复制。
- [ ] **MODEL-005** — 定义指标公式、维度、过滤、时间口径、owner、版本和测试。
- [ ] **MODEL-006** — 生成 dbt/SQL/semantic model、字典、ER 图、lineage，并验证批流/API/BI 一致。
- [ ] **MODEL-007** — 固化输入和授权范围。
- [ ] **MODEL-008** — 验证机器可读输出。
- [ ] **MODEL-009** — 记录证据、成本、风险和回退。
- [ ] **MODEL-010** — 运行对应测试并更新完成状态。
- [ ] **MODEL-011** — 生成交付与未覆盖项。

## elmos-metadata-catalog-lineage

- [ ] **META-001** — 定义 dataset/job/run/column/dashboard/metric/model/owner 的稳定标识。
- [ ] **META-002** — 采用 OpenLineage 等运行事件标准，接入 Spark/Flink/Airflow/Dagster/dbt/查询引擎。
- [ ] **META-003** — 选择 OpenMetadata、DataHub、Atlas 或兼容目录并保留可替换接口。
- [ ] **META-004** — 采集 schema、统计、标签、术语、质量、SLO、使用量、血缘和版本。
- [ ] **META-005** — 实现表/列/跨系统和设计态/运行态血缘，建立 owner/steward/domain/认证/弃用。
- [ ] **META-006** — 生成影响分析、通知、审批、审计和 lineage completeness 校验。
- [ ] **META-007** — 固化输入和授权范围。
- [ ] **META-008** — 验证机器可读输出。
- [ ] **META-009** — 记录证据、成本、风险和回退。
- [ ] **META-010** — 运行对应测试并更新完成状态。
- [ ] **META-011** — 生成交付与未覆盖项。

## elmos-data-quality-observability

- [ ] **DQOBS-001** — 为源、事件、表、特征、指标和 API 定义 owner、schema、freshness、completeness、compatibility。
- [ ] **DQOBS-002** — 生成 not-null、unique、referential、range、distribution、volume、freshness、业务不变量测试。
- [ ] **DQOBS-003** — 区分阻断、隔离、告警和观察级，避免所有异常都停平台。
- [ ] **DQOBS-004** — 监控 lag、watermark、checkpoint、row/bytes/files、schema drift 和成本。
- [ ] **DQOBS-005** — 用季节性与业务日历做异常检测，同时保留确定性阈值。
- [ ] **DQOBS-006** — 结合 lineage 做影响分析和根因排序，生成 quarantine、补数、重跑、回滚和通知。
- [ ] **DQOBS-007** — 固化输入和授权范围。
- [ ] **DQOBS-008** — 验证机器可读输出。
- [ ] **DQOBS-009** — 记录证据、成本、风险和回退。
- [ ] **DQOBS-010** — 运行对应测试并更新完成状态。
- [ ] **DQOBS-011** — 生成交付与未覆盖项。

## elmos-orchestration-backfill-replay

- [ ] **ORCH-001** — 区分数据作业编排与 Elmos 长任务控制：数据 DAG 可用 Airflow/Dagster，Elmos 控制面可用 Temporal。
- [ ] **ORCH-002** — 按资产依赖、时间、事件和审批设计 DAG，不用 sleep/polling 占 worker。
- [ ] **ORCH-003** — 为节点定义幂等键、输入快照、输出提交、重试分类、超时和补偿。
- [ ] **ORCH-004** — 设计分区 backfill、事件 replay、范围锁、并发限制和下游影响预览。
- [ ] **ORCH-005** — 隔离历史回填与实时结果，使用版本/命名空间/原子切换。
- [ ] **ORCH-006** — 持久化进度、offset、成本、日志、lineage 和证据；验证重复触发与故障恢复。
- [ ] **ORCH-007** — 固化输入和授权范围。
- [ ] **ORCH-008** — 验证机器可读输出。
- [ ] **ORCH-009** — 记录证据、成本、风险和回退。
- [ ] **ORCH-010** — 运行对应测试并更新完成状态。
- [ ] **ORCH-011** — 生成交付与未覆盖项。

## elmos-feature-store-ml-pipeline

- [ ] **FEAST-001** — 定义 entity、event timestamp、feature view、label、freshness、owner 和版本。
- [ ] **FEAST-002** — 生成 point-in-time correct join，防止未来信息泄漏和训练/服务偏差。
- [ ] **FEAST-003** — 设计 offline store、online store、registry、materialization 和 feature service。
- [ ] **FEAST-004** — 按延迟和一致性选择在线 serving store，权威历史保留在离线层。
- [ ] **FEAST-005** — 生成批/流特征、回填、TTL、缺失和迟到修正，接入 Feast 或可替换接口。
- [ ] **FEAST-006** — 测试质量、漂移、覆盖、freshness、离在线一致、性能和训练快照可重现性。
- [ ] **FEAST-007** — 固化输入和授权范围。
- [ ] **FEAST-008** — 验证机器可读输出。
- [ ] **FEAST-009** — 记录证据、成本、风险和回退。
- [ ] **FEAST-010** — 运行对应测试并更新完成状态。
- [ ] **FEAST-011** — 生成交付与未覆盖项。

## elmos-bigdata-api-dashboard

- [ ] **SERVE-001** — 区分同步查询、异步导出、订阅推送、预计算和缓存路径。
- [ ] **SERVE-002** — 生成 REST/GraphQL/SQL/semantic API 契约、分页、过滤、限流和版本。
- [ ] **SERVE-003** — 在 ECharts、Superset、Grafana、Tableau、Power BI 等适配器中按场景选择。
- [ ] **SERVE-004** — 图表绑定机器可读指标、新鲜度和最后更新时间。
- [ ] **SERVE-005** — 实现租户/行列权限、masking、导出控制、审计、缓存键与失效。
- [ ] **SERVE-006** — 测试正确性、并发、P95、权限、导出、空/错状态、时区、单位和回归。
- [ ] **SERVE-007** — 固化输入和授权范围。
- [ ] **SERVE-008** — 验证机器可读输出。
- [ ] **SERVE-009** — 记录证据、成本、风险和回退。
- [ ] **SERVE-010** — 运行对应测试并更新完成状态。
- [ ] **SERVE-011** — 生成交付与未覆盖项。

## elmos-bigdata-infra-deployment

- [ ] **INFRA-001** — 生成最小本地栈和种子数据，明确与生产性能的差异。
- [ ] **INFRA-002** — 生成 dev/test/staging/prod/dr 参数，不复制密钥或硬编码端点。
- [ ] **INFRA-003** — 为状态组件设计存储类、反亲和、PDB、拓扑、资源、扩缩容和升级。
- [ ] **INFRA-004** — 生成网络策略、服务身份、TLS、secrets broker、私有端点和 egress 边界。
- [ ] **INFRA-005** — 生成 Helm/Terraform/GitOps、版本锁、可回滚部署、备份和灾备接口。
- [ ] **INFRA-006** — 运行 lint、plan、dry-run、policy-as-code、smoke，并接入日志/指标/trace/audit/cost tag。
- [ ] **INFRA-007** — 固化输入和授权范围。
- [ ] **INFRA-008** — 验证机器可读输出。
- [ ] **INFRA-009** — 记录证据、成本、风险和回退。
- [ ] **INFRA-010** — 运行对应测试并更新完成状态。
- [ ] **INFRA-011** — 生成交付与未覆盖项。

## elmos-bigdata-security-governance

- [ ] **GOV-001** — 建立组织级数据分类与自动标签，覆盖 source/topic/bucket/table/column/feature/dashboard/export。
- [ ] **GOV-002** — 实施 RBAC/ABAC、purpose-based access、row/column policy、masking、tokenization。
- [ ] **GOV-003** — 定义 consent、retention、legal hold、right-to-delete、归档和可验证删除传播。
- [ ] **GOV-004** — 设计跨区域/跨云/跨域驻留、传输、egress 和审批。
- [ ] **GOV-005** — 记录访问、变更、导出、模型使用、策略决策和管理员行为。
- [ ] **GOV-006** — 建立 owner/steward、数据产品 SLA、认证/弃用/例外/复审和政策即代码测试。
- [ ] **GOV-007** — 固化输入和授权范围。
- [ ] **GOV-008** — 验证机器可读输出。
- [ ] **GOV-009** — 记录证据、成本、风险和回退。
- [ ] **GOV-010** — 运行对应测试并更新完成状态。
- [ ] **GOV-011** — 生成交付与未覆盖项。

## elmos-bigdata-test-validation

- [ ] **TEST-001** — 从需求、契约、指标、SLO 和故障模型生成可追踪测试矩阵。
- [ ] **TEST-002** — 执行转换单元、schema/contract compatibility、质量和业务不变量。
- [ ] **TEST-003** — 执行 connector/broker/engine/catalog/warehouse/API/dashboard 集成。
- [ ] **TEST-004** — 执行 batch vs stream、旧 vs 新、full vs incremental、replay vs live 差分。
- [ ] **TEST-005** — 覆盖重复、乱序、迟到、删除、演进、回填、重试、恢复和部分失败。
- [ ] **TEST-006** — 执行租户/权限/脱敏/导出/密钥/审计、安全和端到端 SLO/成本验证。
- [ ] **TEST-007** — 固化输入和授权范围。
- [ ] **TEST-008** — 验证机器可读输出。
- [ ] **TEST-009** — 记录证据、成本、风险和回退。
- [ ] **TEST-010** — 运行对应测试并更新完成状态。
- [ ] **TEST-011** — 生成交付与未覆盖项。

## elmos-bigdata-performance-chaos

- [ ] **CHAOS-001** — 建立 steady、peak、burst、growth、backfill、disaster 六类负载。
- [ ] **CHAOS-002** — 注入热点 key、倾斜、大消息、小文件、慢 sink、积压和高并发查询。
- [ ] **CHAOS-003** — 注入 broker/worker/coordinator/catalog/object-store/network/disk/credential 故障。
- [ ] **CHAOS-004** — 测量 time-to-insight、P95/P99、lag、backpressure、checkpoint、恢复和正确性。
- [ ] **CHAOS-005** — 验证扩缩容、rebalance、state migration、compaction、限流与重试风暴。
- [ ] **CHAOS-006** — 确定安全容量包络、熔断、降级、自动扩缩阈值和回归基线。
- [ ] **CHAOS-007** — 固化输入和授权范围。
- [ ] **CHAOS-008** — 验证机器可读输出。
- [ ] **CHAOS-009** — 记录证据、成本、风险和回退。
- [ ] **CHAOS-010** — 运行对应测试并更新完成状态。
- [ ] **CHAOS-011** — 生成交付与未覆盖项。

## elmos-bigdata-cost-autotuning

- [ ] **OPT-001** — 分解计算、存储、网络、日志、备份、空闲、许可证和运维成本。
- [ ] **OPT-002** — 识别 over-provision、重扫、低效 join、无效索引、过多副本、小文件和过长保留。
- [ ] **OPT-003** — 生成 partition/sort/cluster/MV/cache/compaction/pushdown 优化。
- [ ] **OPT-004** — 优化 autoscaling、spot、资源池、调度窗口和 workload priority。
- [ ] **OPT-005** — 用 canary/shadow 验证，设置正确性和 SLO guardrail、上下限、冷却和回滚。
- [ ] **OPT-006** — 记录基线、收益、置信度、潜在回归，并将验证结果版本化反馈选择器。
- [ ] **OPT-007** — 固化输入和授权范围。
- [ ] **OPT-008** — 验证机器可读输出。
- [ ] **OPT-009** — 记录证据、成本、风险和回退。
- [ ] **OPT-010** — 运行对应测试并更新完成状态。
- [ ] **OPT-011** — 生成交付与未覆盖项。

## elmos-bigdata-auto-repair

- [ ] **REPAIR-001** — 关联 Data SLO、任务、组件、版本、schema、权限、成本和下游影响。
- [ ] **REPAIR-002** — 按证据、时间、变更和反事实测试排序根因候选。
- [ ] **REPAIR-003** — 优先无副作用诊断与低风险动作：幂等重试、扩容、切副本、隔离毒数据。
- [ ] **REPAIR-004** — 回填、schema 回退、配置、切流和数据修正按风险设置审批。
- [ ] **REPAIR-005** — 修复前创建快照/savepoint/备份，在 shadow/canary 验证。
- [ ] **REPAIR-006** — 运行针对性与全量回归，确认正确性、SLO、成本、安全后逐步扩大。
- [ ] **REPAIR-007** — 固化输入和授权范围。
- [ ] **REPAIR-008** — 验证机器可读输出。
- [ ] **REPAIR-009** — 记录证据、成本、风险和回退。
- [ ] **REPAIR-010** — 运行对应测试并更新完成状态。
- [ ] **REPAIR-011** — 生成交付与未覆盖项。

## elmos-bigdata-evidence-certification

- [ ] **CERT-001** — E1 静态完整性：文件、schema、依赖、配置、文档和追踪矩阵。
- [ ] **CERT-002** — E2 本地/组件：单元、契约、质量和关键组件运行。
- [ ] **CERT-003** — E3 集成/E2E：真实 connector、数据流、API、BI、权限。
- [ ] **CERT-004** — E4 生产相似：压力、混沌、恢复、升级、成本、多租户。
- [ ] **CERT-005** — E5 受控生产/影子：真实 SLO、告警、回滚、运营闭环。
- [ ] **CERT-006** — 每项结论记录 evidence URI、环境、版本、时间、范围；区分 implemented/configured/tested/verified/certified。
- [ ] **CERT-007** — 固化输入和授权范围。
- [ ] **CERT-008** — 验证机器可读输出。
- [ ] **CERT-009** — 记录证据、成本、风险和回退。
- [ ] **CERT-010** — 运行对应测试并更新完成状态。
- [ ] **CERT-011** — 生成交付与未覆盖项。

## elmos-bigdata-project-orchestrator

- [ ] **MASTER-001** — 创建不可变输入快照、授权范围、tenant_id、task_id、idempotency_key 和预算。
- [ ] **MASTER-002** — 构建可恢复 DAG，受每账号最多 3 个并发任务约束；内容寻址缓存按租户隔离。
- [ ] **MASTER-003** — 通过模型网关为提取/规划/编码/评审/修复选择性价比模型并记录 token/费用。
- [ ] **MASTER-004** — 执行需求 IR、画像、硬过滤、排序、多模规划、ADR 和架构基线。
- [ ] **MASTER-005** — 生成完整仓库、管道、IaC、测试、文档、图表、runbook、样例并自动修复回归。
- [ ] **MASTER-006** — 异步持久化节点输入/输出/状态/日志/成本/恢复点，客户端断线不终止服务端任务。
- [ ] **MASTER-007** — 分别报告系统自主 wall-clock ETA、人类等价工作量、HITL 等待，不能混为一项。
- [ ] **MASTER-008** — 生成 E1–E5 证据、完成度、已验证范围、未覆盖风险和交付包。
- [ ] **MASTER-009** — 固化输入和授权范围。
- [ ] **MASTER-010** — 验证机器可读输出。
- [ ] **MASTER-011** — 记录证据、成本、风险和回退。
- [ ] **MASTER-012** — 运行对应测试并更新完成状态。
- [ ] **MASTER-013** — 生成交付与未覆盖项。

## elmos-template-offline-warehouse

- [ ] **TPLDW-001** — 生成 source→raw→clean/detail→summary/serving 数据流与业务粒度。
- [ ] **TPLDW-002** — 默认评估对象存储+开放表+Spark/dbt+Trino/OLAP，不强制固定产品。
- [ ] **TPLDW-003** — 生成增量抽取、SCD、历史回填、分区和小文件维护。
- [ ] **TPLDW-004** — 生成指标目录、语义层、BI 模型和经营报表样例。
- [ ] **TPLDW-005** — 生成质量、血缘、调度、成本、权限和审计。
- [ ] **TPLDW-006** — 执行全量/增量等价、批次 SLA、恢复和数据正确性验证。
- [ ] **TPLDW-007** — 固化输入和授权范围。
- [ ] **TPLDW-008** — 验证机器可读输出。
- [ ] **TPLDW-009** — 记录证据、成本、风险和回退。
- [ ] **TPLDW-010** — 运行对应测试并更新完成状态。
- [ ] **TPLDW-011** — 生成交付与未覆盖项。

## elmos-template-realtime-analytics

- [ ] **TPLRT-001** — 生成 CDC/事件→Kafka/Pulsar→Flink/等价引擎→OLAP/cache→API/大屏。
- [ ] **TPLRT-002** — 定义 event time、watermark、late data、dedup、state、checkpoint。
- [ ] **TPLRT-003** — 生成实时/离线对账、重放和历史修正路径。
- [ ] **TPLRT-004** — 生成物化/预聚合、查询并发和新鲜度显示。
- [ ] **TPLRT-005** — 生成 lag/backpressure/checkpoint/query latency/cost 监控。
- [ ] **TPLRT-006** — 测试峰值、乱序、重复、broker/worker 故障和恢复。
- [ ] **TPLRT-007** — 固化输入和授权范围。
- [ ] **TPLRT-008** — 验证机器可读输出。
- [ ] **TPLRT-009** — 记录证据、成本、风险和回退。
- [ ] **TPLRT-010** — 运行对应测试并更新完成状态。
- [ ] **TPLRT-011** — 生成交付与未覆盖项。

## elmos-template-realtime-user-profile

- [ ] **TPL360-001** — 设计 identity graph、主身份、设备合并、冲突和可撤销关联。
- [ ] **TPL360-002** — 生成 CDC/事件采集、实时标签、离线历史回填和画像版本。
- [ ] **TPL360-003** — 用权威历史层+低延迟 serving store 组合，明确缓存和重建。
- [ ] **TPL360-004** — 定义标签、freshness、TTL、置信度和 owner。
- [ ] **TPL360-005** — 实现 consent、purpose、删除传播、masking 和跨租户隔离。
- [ ] **TPL360-006** — 验证误合并、迟到、重复、删除、实时/离线一致和查询延迟。
- [ ] **TPL360-007** — 固化输入和授权范围。
- [ ] **TPL360-008** — 验证机器可读输出。
- [ ] **TPL360-009** — 记录证据、成本、风险和回退。
- [ ] **TPL360-010** — 运行对应测试并更新完成状态。
- [ ] **TPL360-011** — 生成交付与未覆盖项。

## elmos-template-recommendation-system

- [ ] **TPLREC-001** — 生成曝光、点击、停留、转化和负样本事件契约。
- [ ] **TPLREC-002** — 建立 point-in-time training set、特征和标签延迟窗口。
- [ ] **TPLREC-003** — 设计批/流特征、online store、候选索引、缓存和模型服务边界。
- [ ] **TPLREC-004** — 生成召回、粗排、精排、规则和冷启动数据路径。
- [ ] **TPLREC-005** — 实现 A/B、探索、反馈回流、偏差、漂移和异常监控。
- [ ] **TPLREC-006** — 验证训练泄漏、特征一致、延迟、降级和结果可追踪。
- [ ] **TPLREC-007** — 固化输入和授权范围。
- [ ] **TPLREC-008** — 验证机器可读输出。
- [ ] **TPLREC-009** — 记录证据、成本、风险和回退。
- [ ] **TPLREC-010** — 运行对应测试并更新完成状态。
- [ ] **TPLREC-011** — 生成交付与未覆盖项。

## elmos-template-iot-timeseries

- [ ] **TPLIOT-001** — 建立 device/twin/measurement/event/command 契约和设备身份。
- [ ] **TPLIOT-002** — 生成边缘缓冲、断网续传、MQTT/Kafka、乱序和时钟漂移处理。
- [ ] **TPLIOT-003** — 选择时序数据库、实时流处理和湖仓历史层组合。
- [ ] **TPLIOT-004** — 设计 downsampling、retention、compression、hot/cold 和高基数标签。
- [ ] **TPLIOT-005** — 生成规则/CEP 告警、状态机、维护和可视化。
- [ ] **TPLIOT-006** — 验证断网、重复、漂移、乱序、突发、重连和历史补传。
- [ ] **TPLIOT-007** — 固化输入和授权范围。
- [ ] **TPLIOT-008** — 验证机器可读输出。
- [ ] **TPLIOT-009** — 记录证据、成本、风险和回退。
- [ ] **TPLIOT-010** — 运行对应测试并更新完成状态。
- [ ] **TPLIOT-011** — 生成交付与未覆盖项。

## elmos-template-fraud-risk

- [ ] **TPLRISK-001** — 生成交易、身份、设备、账户、关系和决策事件契约。
- [ ] **TPLRISK-002** — 设计实时窗口、velocity、黑白名单、图特征和历史特征。
- [ ] **TPLRISK-003** — 组合规则引擎、模型评分、图查询和人工复核。
- [ ] **TPLRISK-004** — 记录每次决策输入版本、规则、模型、解释和结果。
- [ ] **TPLRISK-005** — 生成低延迟 serving、降级规则、熔断和高可用。
- [ ] **TPLRISK-006** — 验证重放一致、时间穿越、重复交易、热点实体、回滚和权限。
- [ ] **TPLRISK-007** — 固化输入和授权范围。
- [ ] **TPLRISK-008** — 验证机器可读输出。
- [ ] **TPLRISK-009** — 记录证据、成本、风险和回退。
- [ ] **TPLRISK-010** — 运行对应测试并更新完成状态。
- [ ] **TPLRISK-011** — 生成交付与未覆盖项。

## elmos-template-log-observability

- [ ] **TPLOBS-001** — 生成 OpenTelemetry/agent→buffer→stream→列式 OLAP/湖仓数据流。
- [ ] **TPLOBS-002** — 规范 service、trace、span、host、tenant、severity 字段。
- [ ] **TPLOBS-003** — 设计采样、动态采样、压缩、索引、分区、TTL 和冷热归档。
- [ ] **TPLOBS-004** — 实现敏感字段过滤、tokenization、租户隔离和审计。
- [ ] **TPLOBS-005** — 生成跨日志/指标/trace 查询、dashboard、告警和 incident link。
- [ ] **TPLOBS-006** — 验证峰值摄取、查询并发、丢包、积压、成本和恢复。
- [ ] **TPLOBS-007** — 固化输入和授权范围。
- [ ] **TPLOBS-008** — 验证机器可读输出。
- [ ] **TPLOBS-009** — 记录证据、成本、风险和回退。
- [ ] **TPLOBS-010** — 运行对应测试并更新完成状态。
- [ ] **TPLOBS-011** — 生成交付与未覆盖项。

## elmos-template-data-governance-platform

- [ ] **TPLGOV-001** — 生成 metadata ingestion、catalog、lineage、quality、glossary、ownership 服务。
- [ ] **TPLGOV-002** — 建立 domain、data product、owner、steward、certification、deprecation。
- [ ] **TPLGOV-003** — 接入数据库、湖仓、消息、管道、BI、ML、API 元数据。
- [ ] **TPLGOV-004** — 生成 ABAC/RBAC、分类、masking、access request 和审计。
- [ ] **TPLGOV-005** — 生成 SLO、质量、影响分析、变更通知和治理 dashboard。
- [ ] **TPLGOV-006** — 验证元数据覆盖、血缘准确、权限和治理工作流。
- [ ] **TPLGOV-007** — 固化输入和授权范围。
- [ ] **TPLGOV-008** — 验证机器可读输出。
- [ ] **TPLGOV-009** — 记录证据、成本、风险和回退。
- [ ] **TPLGOV-010** — 运行对应测试并更新完成状态。
- [ ] **TPLGOV-011** — 生成交付与未覆盖项。

## elmos-template-vector-knowledge-analytics

- [ ] **TPLVEC-001** — 生成 document/version/chunk/embedding/ACL/source-citation/delete 事件契约。
- [ ] **TPLVEC-002** — 选择 pgvector、Milvus、Qdrant、Weaviate 或搜索引擎向量能力，并保留关键词检索。
- [ ] **TPLVEC-003** — 设计解析、分块、去重、embedding 版本、增量更新和重建。
- [ ] **TPLVEC-004** — 建立 vector、BM25、metadata filter、rerank、query rewrite 可替换管道。
- [ ] **TPLVEC-005** — 确保 ACL 在检索前过滤，删除与权限变化传播到所有索引。
- [ ] **TPLVEC-006** — 生成 relevance/recall/MRR/nDCG/citation/latency/cost/security 评测。
- [ ] **TPLVEC-007** — 固化输入和授权范围。
- [ ] **TPLVEC-008** — 验证机器可读输出。
- [ ] **TPLVEC-009** — 记录证据、成本、风险和回退。
- [ ] **TPLVEC-010** — 运行对应测试并更新完成状态。
- [ ] **TPLVEC-011** — 生成交付与未覆盖项。

## elmos-template-cdc-migration-modernization

- [ ] **TPLMIG-001** — 生成源盘点、DDL/SQL/作业/报表依赖和差异矩阵。
- [ ] **TPLMIG-002** — 生成 snapshot、CDC、offset、水位、重放、断点和幂等。
- [ ] **TPLMIG-003** — 建立旧新双运行、影子查询、行数/校验和/业务不变量/性能对比。
- [ ] **TPLMIG-004** — 按表/域/租户/流量渐进切换并设置自动回滚阈值。
- [ ] **TPLMIG-005** — 保留历史回填、schema 演进、删除传播和下游重建。
- [ ] **TPLMIG-006** — 生成退役、归档、审计、成本和生产认证证据。
- [ ] **TPLMIG-007** — 固化输入和授权范围。
- [ ] **TPLMIG-008** — 验证机器可读输出。
- [ ] **TPLMIG-009** — 记录证据、成本、风险和回退。
- [ ] **TPLMIG-010** — 运行对应测试并更新完成状态。
- [ ] **TPLMIG-011** — 生成交付与未覆盖项。
