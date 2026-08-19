# packages/execution-intelligence

项目生成/转换的执行智能：Token、费用、系统自主运行时、人工基线、双时间线对比、持久执行与恢复、模型路由、结果封存、生产就绪认证、Chaos 验证。

纯标准库，Python ≥ 3.10，无网络依赖，可在 elmos 现有的 symlink-free 钉版工具链下直接运行。

## 五条不可违反的口径（结构上强制，不靠约定）

1. **系统 ETA 只含机器自主时间。** 人工审批、验收、凭据等待写在 `human_assisted`，`system_runtime.excludes` 明文列出；测试断言端到端时间严格大于系统 ETA。
2. **人工基线与系统估算共用同一份任务 DAG**，因此共用同一个 Definition of Done。
3. **一切是区间。** 每个量带 P50/P80/P90/Worst Case/mean/min/max，外加 `assumptions`、`exclusions`、`confidence`。
4. **不写死任何厂商价格。** 费率必须带 `effective_date` / `verified_at` / `source_reference`；模板里的 `null` 会被校验拒绝（退出码 3 = BLOCKED）。
   `config/model-pricing.json` 里是 2026-08-19 从各厂商官方文档页读到的**已核验列表价**（8 个模型，Anthropic / OpenAI / DeepSeek），
   每条带来源 URL 与核验时间，`not_for_billing=false`。它们是**列表价，不是你的账户议价、不是批量价、不是报价单**；
   价格随时会变，引用前重新核验并更新 `verified_at`。Kimi 与 Qwen 当天没取到可用费率，**留空并写明原因**，没有编。
5. **不同币种永不互相排名。** `cross_currency_comparison` 恒为 `null`。

另外两条：**缺证据不等于通过**（认证门禁没有证据就是 `NOT_EXECUTED`）；**schema 必须被执行**（每个 JSON 产物写盘后立即被校验，失败即 BLOCKED）。

## 18 个 Skill 的落地位置

| Skill | 实现 | 产物 |
| --- | --- | --- |
| 00 编排 | `cli.py` 各命令 + Makefile 目标 | — |
| 01 范围审计 | `scope.py` | `scope-baseline.json/.md`、`risk-and-gap-register.json`、`project-profile.seed.json` |
| 02 任务分解 | `decompose.py` + `config/decomposition-model.json` | `task-dag.json`、`critical-path-seed.json`、`task-estimation-seed.csv` |
| 03 Token 预算 | `simulation.py`、`token_scan.py` | `token-forecast.json`、`TOKEN_BUDGET.md`、`task-token-estimates.csv` |
| 04 费用 | `cost.py` | `cost-forecast.json`、`MODEL_COST_COMPARISON.md` |
| 05 系统 ETA | `simulation.py` | `autonomous-runtime.json`、`SYSTEM_RUNTIME_ESTIMATE.md` |
| 06 人工基线 | `simulation.py` | `human-effort.json`、`HUMAN_EFFORT_ESTIMATE.md` |
| 07 双时间线 | `comparison.py` | `time-comparison.json`、`SYSTEM_VS_HUMAN_COMPARISON.md` |
| 08 持久编排 | `durable.py::Orchestrator` | `run-summary.json`、`TASK_EXECUTION_PLAN.md` |
| 09 Checkpoint | `durable.py::DurableStore.record_checkpoint` | `checkpoint` 表 + 恢复对账 |
| 10 幂等与副作用 | `durable.py`（幂等键、Outbox、内容寻址 Artifact） | 幂等记录、审计事件 |
| 11 可重连事件流 | `durable.py::append_event/events_since/sse_frames` | SSE 帧与轮询页 |
| 12 恢复感知 ETA | `durable.py::recovery_aware_eta` | `recovery-eta-update.json` |
| 13 校准 | `calibration.py` | `calibration.json`、`estimator-profiles.json`、`forecast-accuracy-report.md` |
| 14 模型路由 | `routing.py` + `config/provider-capabilities.json` | `model-routing-plan.json`、`MODEL_ROUTING_COMPARISON.md` |
| 15 结果封存 | `publisher.py` | `result-manifest.json` |
| 16 就绪认证 | `certifier.py` | `production-readiness.json/-report.md`、`evidence-manifest.json` |
| 17 Chaos 验证 | `chaos.py` | `chaos-test-report.json`、`recovery-evidence.md` |

补充能力（不属于原 18 个 Skill，但补上了它们缺的证据链）：

| 能力 | 实现 | 产物 |
| --- | --- | --- |
| 真实遥测接入 | `telemetry.py` | 三种来源：pytest 汇总行（聚合均值）、`--durations=0`（逐节点实测）、Agent 会话记录（**唯一带真实 token 计数的来源**） |
| Skill 拆分建议 | `skill_advice.py` | `skill-split-advice.json`、`SKILL_SPLIT_ADVICE.md` |
| 人工基线锚点 | `human_anchor.py` | `human-baseline-anchor.json`、`HUMAN_BASELINE_ANCHOR.md`（从 git 历史推出的上下界，不是测量值） |
| 计数校准 | `config/token-count-calibration.json` | 启发式对真实 BPE 的实测偏差，`scan-tokens` 默认应用 |
| PostgreSQL 后端 | `postgres.py` | 同一份契约跑在未修改的生产 schema 上 |
| 参考 HTTP 服务器 | `server.py` | 让 `openapi/` 的重连与幂等契约能被 curl 真的验证 |

## 目录

```text
src/elmos_execution_intelligence/   实现
config/                             估算默认值、人工基线、价格模板、分解模型、能力矩阵
schemas/                            21 个 JSON Schema（全部被执行校验）
sql/                                PostgreSQL 持久执行表结构（生产目标）
openapi/                            异步任务 API 与 Last-Event-ID 重连契约
references/                         架构、状态机、失败分类、持久执行、估算方法、验收标准
templates/                          执行计划与事故恢复报告模板（被渲染器真实消费）
profiles/elmos/                     elmos 自身的项目画像与任务 DAG
tests/                              单元与端到端测试
estimation/                         输出目录
```

## 完整链路

```bash
cd packages/execution-intelligence

make scan        # 静态语料扫描
make audit       # 01 范围审计 + 风险缺口register + 画像种子
make dag         # 02 从范围基线派生任务 DAG
make forecast    # 03-07 全部预测与报告
make plan        # 08 执行计划
make execute     # 08-12 持久执行（模拟执行器，产出真实遥测）
make route       # 14 模型路由优化
make chaos       # 17 Chaos 与恢复验证
make calibrate   # 13 用执行遥测校准
make certify     # 16 门禁式生产就绪评估
make advise      # 超重 SKILL.md 的拆分建议
make anchor      # 从 git 历史推人工基线锚点（需先导出 git log）
make serve       # 起参考 HTTP 服务器
make pg-conformance PG_DSN=...   # 同一批断言对 SQLite 与 PostgreSQL 各跑一遍
make all         # 上面全部，按顺序
```

也可以逐条用 CLI（`pip install -e .` 之后是 `elmos-ei`）：

```bash
PYTHONPATH=src python3 -m elmos_execution_intelligence.cli --help
```

## 闭环

```text
audit-scope ──► decompose ──► forecast ──► plan ──► execute
                                  ▲                    │
                                  │                    ▼
              apply-calibration ◄─┴── calibrate ◄── export-telemetry
```

执行产生的 `model_usage` 直接导出成 `calibrate` 需要的 JSONL；校准倍率通过
`apply-calibration` 写回任务 DAG，再重新 `forecast`。这条闭环在测试
`test_full_loop_from_scope_to_certification` 里被完整跑过一遍。

## 持久执行是参考实现

`durable.py` 跑在 SQLite 上，不是生产部署。它存在的意义是**让契约可测**：
测试里真的杀掉一个 Worker、真的重启编排器、真的断开客户端再重连、真的重复提交。
`sql/001_execution_intelligence.sql` 是生产目标，语义一一对应；换成 PostgreSQL + Temporal 之后断言不变。

**生产 schema 已在真实 PostgreSQL 16.13 上验证。** `sql/001_execution_intelligence.sql`
完整执行通过；`postgres.py` 在这份未修改的 schema 上实现同一份契约；
`tests/test_store_conformance.py` 的同一批断言对 SQLite 与 PostgreSQL 各跑一遍，22 项全过
（`make pg-conformance PG_DSN=...`）。这证明契约可移植，**不证明可以上生产**——
Temporal、连接池、迁移管理、集群级故障演练都还没有。

**存储位置有硬约束。** SQLite 需要真正的文件锁；网络盘和 FUSE 挂载（包括桌面桥挂载的工作树）
不提供，表现为一句毫无信息量的 `disk I/O error`。把 `--store` 放在本地盘（例如 `/tmp/elmos-run.db`），
或者用 `:memory:` 跑一次性的。放错位置时本包会给出指明原因的 BLOCKED，而不是抛栈。

模拟执行器产出的遥测是合成的，但被它验证的持久性质是真的。`run-summary.json` 里
`simulated: true` 明确标注了这一点。

## Token 分类不重复计数

`input`、`cached_input`、`cache_write`、`output`、`reasoning_output` 互斥，`total` 是它们的和。
测试 `test_token_categories_sum_to_total_without_double_counting` 逐样本断言。
任何时候都不得把 `total` 再加回某个分类。

## 静态扫描是什么，不是什么

`scan-tokens` 回答的是「把磁盘上的材料喂给模型**一次**要多少 token」。它是预测的输入，
不是预测本身。重复读取、返工、失败重试、子 Agent 放大都由任务 DAG 的 `token_profile` 表达。
用文件字符数直接推算整个项目的 token 预算，是 `CLAUDE.md` 明令禁止的做法。

没有 tiktoken 时用 CJK 感知的启发式计数，结果标 `cjk-aware-heuristic`、`exact_counts=false`。
计费级静态计数请用目标厂商的官方计数接口。

## 测试

```bash
python3 -m pytest -q tests
```

纯 Python、无网络、无外部工具链依赖。`test_contracts.py` 里 OpenAPI 相关用例需要 PyYAML，
缺失时自动跳过；其余全部无依赖。
