# Elmos 多租户任务控制与 FinOps Skills Package

版本：**1.0.0**  
包名：`elmos-multitenant-task-finops-skills`

本包将以下产品要求整理为可由 Codex、Claude Code 或工程团队直接实施、测试和审计的生产级 Skills 体系：

- Elmos 采用多租户模式，租户、账号、项目、任务和产物全链路隔离；
- 每个认证账号在所有租户成员关系下，最多同时执行 **3 个顶层任务**；
- 第 4 个及之后的任务必须可靠入队为 `WAITING_FOR_SLOT`，不得丢弃，也不得提前执行；
- 任务进度、节点、执行尝试、检查点、租约、副作用、输入、输出、日志和异常必须持久化；
- 客户端断线、服务重启、Worker 失联后，任务可从兼容检查点恢复；
- 每次任务都要记录模型、CPU、GPU、内存、存储、网络、Runner、Sandbox 和第三方 API 用量；
- 成本、客户扣费、已确认收入、已收现金、退款、税费和支付手续费分别记账；
- 支持按账号、租户、项目、任务、模型、供应商、Skill 和时间统计总成本、总收入、毛利润与毛利率。

English documentation: [`README.en.md`](README.en.md)

## 一、不可妥协的系统约束

```text
账号级并发上限 = 3 个正在执行的顶层任务
```

这里的“账号级”是认证账号全局范围，而不是浏览器标签页、设备或单个租户成员关系范围。一个账号即使同时属于多个租户，也只能占用三个顶层任务槽。

```text
实际可运行任务数 = min(
  3,
  租户剩余任务配额,
  租户剩余资源单元,
  平台/工作负载容量,
  模型供应商并发额度,
  任务与租户预算
)
```

只有顶层任务占账号槽。任务内部 DAG 节点由 Worker Pool、工作负载类别和资源单元控制，不能借“节点不占槽”无限展开并发。

## 二、参考架构

```text
OIDC/JWT + 服务端租户成员关系校验
                 │
                 ▼
Spring Boot Control API
  ├─ 幂等任务提交
  ├─ 账号三槽原子准入
  ├─ 租户/资源/预算门禁
  └─ API、SSE、审计
                 │
                 ▼
PostgreSQL 权威状态 + Transactional Outbox
  ├─ Task / Run / Node / Attempt
  ├─ Slot Lease + Fencing Generation
  ├─ Event Journal + Progress Snapshot
  ├─ Checkpoint + Side-effect Receipt
  ├─ Input / Artifact / Log Manifest
  ├─ Usage / Cost Ledger
  └─ Revenue / Allocation / Margin Ledger
                 │
       ┌─────────┴─────────┐
       ▼                   ▼
Temporal Workflow      S3 / MinIO
       │               大型输入、输出、日志、快照
       ▼
工作负载 Worker Pool / Private Runner / Sandbox
       │
       ▼
Kafka / NATS / Redpanda 事件适配层
       │
       ├─ Progress Projection + SSE/WebSocket
       ├─ Metering / FinOps
       └─ Analytics / ClickHouse（可选）
```

PostgreSQL 是准入、当前状态、关键事件、检查点和财务账本的最终事实源。Temporal 是持久化工作流引擎。对象存储拥有大型内容。Redis 只能作为缓存、限流和队列位置加速层，不能单独决定是否突破 3 个任务。

## 三、12 个 Skills

| 顺序 | Skill | 职责 |
|---:|---|---|
| 1 | `elmos-multitenant-task-finops-orchestrator` | 扫描现有仓库、冻结契约、生成实施计划和证据矩阵 |
| 2 | `elmos-tenant-identity-rls` | OIDC、成员关系、数据库角色、FORCE RLS、审计 |
| 3 | `elmos-account-concurrency-admission` | 账号三槽、幂等提交、原子 Claim/Renew/Release、排队 |
| 4 | `elmos-workload-aware-scheduler` | 多租户公平调度、资源单元、背压和 Worker Pool |
| 5 | `elmos-task-lifecycle-temporal` | Task/Run 状态机、Temporal、暂停/恢复/取消/重试 |
| 6 | `elmos-task-progress-journal` | 有序事件、异步进度、单调进度、SSE 重放、ETA |
| 7 | `elmos-checkpoint-recovery` | 检查点、Lease/Fencing、UNKNOWN_RESULT、对账恢复 |
| 8 | `elmos-task-io-artifact-archive` | 输入、输出、中间状态、日志、产物和保留策略 |
| 9 | `elmos-usage-metering-cost-ledger` | Token/算力/存储/网络/工具计量、价格快照与成本账本 |
| 10 | `elmos-revenue-margin-ledger` | 收费、收入确认、现金、退款、分摊、毛利和毛利率 |
| 11 | `elmos-task-financial-analytics` | 任务与历史汇总、下钻、异常检测和数据导出 |
| 12 | `elmos-concurrency-recovery-finops-certification` | 并发、恢复、RLS、财务对账、负载与生产发布门禁 |

共包含 **144 条稳定实施任务**，详见：

- `docs/TASK-MATRIX.csv`
- `docs/task-catalog.json`
- `docs/FIRST-40-TASKS.md`
- `docs/IMPLEMENTATION-ROADMAP.md`

## 四、关键设计原则

### 1. 禁止 Count-Then-Start

下面的实现会在多个 API 实例并发时超卖：

```sql
SELECT count(*) FROM task WHERE account_id = ? AND state = 'RUNNING';
-- 稍后再 INSERT / UPDATE
```

必须使用本包提供的 `account_task_slot` 三槽表、数据库行锁、Lease Generation 和原子 Claim/Release 函数。

### 2. 当前快照与不可变历史并存

```text
task / task_progress_snapshot
  → 页面快速查询

task_event / usage_event / revenue_entry
  → 恢复、审计、重算和对账的最终事实
```

关键状态迁移、节点完成、检查点、副作用凭证、用量和财务流水必须在确认前持久化。心跳、细粒度进度和普通日志可以异步批量写入。

### 3. 恢复不是简单重试

恢复必须使用：

```text
Checkpoint
+ Lease expiry
+ Fencing generation
+ Side-effect receipt
+ Idempotency key
+ UNKNOWN_RESULT reconciliation
+ Workflow version compatibility
```

未完成但可能已经产生外部副作用的节点，必须先对账，再决定重试或人工恢复。

### 4. 成本与收入分账

```text
系统实际成本 ≠ 客户扣费 ≠ 已确认收入 ≠ 已收现金
```

失败重试可能产生系统成本，但不一定向客户收费。预充值可能形成客户余额或递延收入，而不是立即全部确认为收入。

### 5. 汇总可重建

任务成本、租户日汇总和利润报表都是投影。任何汇总必须能从不可变用量账本和收入账本重新生成，并带上：

```text
scope + reporting currency + recognition basis + as_of
```

## 五、目录结构

```text
.
├── .agents/skills/                 # 12 个 Skills
├── api/openapi.yaml                # 控制、任务、进度、财务与分析 API
├── events/asyncapi.yaml            # 生命周期、进度、检查点、用量和收入事件
├── schemas/                        # Draft 2020-12 JSON Schema
├── examples/                       # 可自动验证的示例
├── sql/                            # PostgreSQL/Flyway 参考迁移和查询
├── config/                         # 准入、工作负载、价格、收入确认和保留策略
├── diagrams/                       # Mermaid 架构、状态机和时序图
├── docs/                           # PRD、架构、数据库、恢复、FinOps、SLO、门禁
├── templates/                      # 实施计划、执行报告、证据包和 ADR 模板
├── tests/                          # 并发、RLS、负载、Chaos、财务对账测试规范
├── scripts/                        # 校验、任务目录、Smoke Test 和打包脚本
├── AGENTS.md                       # Codex 执行入口
├── CLAUDE.md                       # Claude Code 执行入口
├── install.sh
├── uninstall.sh
├── verify.sh
└── skill-manifest.*
```

## 六、安装

安装到 Codex：

```bash
./install.sh --codex
```

安装到 Claude Code：

```bash
./install.sh --claude
```

安装到自定义目录：

```bash
./install.sh --target /path/to/skills
```

安装器只复制 `.agents/skills/*`，不会修改目标项目源码。

## 七、验证

```bash
./verify.sh
```

验证内容包括：

- 12 个 Skill 的 frontmatter、章节和依赖；
- 144 条任务 ID 的完整性与唯一性；
- Skill 依赖图无环；
- JSON Schema 与示例；
- OpenAPI、AsyncAPI 和配置 YAML 的语法与内部 `$ref`；
- SQL 中的三槽、Lease Generation、RLS、事件、检查点和财务账本契约；
- Shell 语法、安装/卸载 Smoke Test；
- 明显 Secret 和未完成占位符扫描。

## 八、推荐执行方法

在 Elmos 代码仓库中先运行总编排 Skill：

```text
$elmos-multitenant-task-finops-orchestrator
```

输入至少包含：

```text
- 当前仓库路径和 Commit SHA
- 已有身份、任务、Temporal、Runner、数据库、对象存储、计费和监控实现
- 部署形态：SaaS / 专属租户 / 私有化 / 离线
- PostgreSQL、Temporal、消息总线和对象存储版本
- 当前收费模式和报表币种
```

执行时不得直接宣称“生产可用”。只有第 12 个认证 Skill 在目标仓库中实际完成迁移、集成测试、RLS 攻击测试、100 并发竞争测试、Worker 故障恢复、账单对账和发布门禁之后，才允许形成生产声明。

## 九、生产声明边界

本下载包已经验证的是：Skills、文档、契约、示例、参考 SQL、安装器和校验脚本本身。

它不等同于某个 Elmos 源代码仓库已经真实完成：

- PostgreSQL 迁移和 RLS；
- Temporal Workflow 和 Worker；
- Private Runner、Sandbox、mTLS 与租约；
- 对象存储、模型调用和支付提供商接入；
- 生产负载、Chaos、备份恢复与财务对账。

这些能力必须由目标仓库产生可执行证据后才能确认。
