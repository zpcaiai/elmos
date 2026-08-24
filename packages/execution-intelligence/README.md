# packages/execution-intelligence

项目生成/转换的执行智能：Token、费用、系统自主运行时、人工基线、双时间线对比、持久执行与恢复、模型路由、结果封存、生产就绪评估、Chaos 验证。

纯标准库，Python ≥ 3.10，无网络依赖，可在 elmos 现有的 symlink-free 钉版工具链下直接运行。

## 五条不可违反的口径（结构上强制，不靠约定）

1. **系统 ETA 只含机器自主时间。** 人工审批、验收、凭据等待写在 `human_assisted`，`system_runtime.excludes` 明文列出；测试断言端到端时间严格大于系统 ETA。
2. **人工基线与系统估算共用同一份任务 DAG**，因此共用同一个 Definition of Done。
3. **一切是区间。** 每个量带 P50/P80/P90/Worst Case/mean/min/max，外加 `assumptions`、`exclusions`、`confidence`。
4. **不写死任何厂商价格。** 费率必须带 `effective_date` / `verified_at` / `source_reference`；模板里的 `null` 会被校验拒绝（退出码 3 = BLOCKED）。
   `config/model-pricing.json` 自述为 2026-08-19 从厂商文档页读取的列表价（8 个模型，Anthropic / OpenAI / DeepSeek），
   每条带来源 URL 与核验时间。该自述不是本次运行的独立核验；它们也不是账户议价、批量价或报价单。
   价格随时会变，预算前必须重新核验并更新 `verified_at`。Kimi 与 Qwen 的费率仍留空，没有猜测。
5. **不同币种永不互相排名。** `cross_currency_comparison` 恒为 `null`。

另外两条：**缺证据不等于通过**（就绪门禁没有证据就是 `NOT_EXECUTED`）；**schema 必须被执行**（CLI 对已知 JSON 产物执行校验，失败即 BLOCKED）。

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
| 16 就绪评估 | `certifier.py` | `production-readiness.json/-report.md`、`evidence-manifest.json` |
| 17 Chaos 验证 | `chaos.py` | `chaos-test-report.json`、`recovery-evidence.md` |

补充能力（不属于原 18 个 Skill，但补上了它们缺的证据链）：

| 能力 | 实现 | 产物 |
| --- | --- | --- |
| 真实遥测接入 | `telemetry.py` | 三种来源：pytest 汇总行（聚合均值）、`--durations=0`（逐节点实测）、Agent 会话记录（**唯一带真实 token 计数的来源**） |
| Skill 拆分建议 | `skill_advice.py`（`advise-skills`） | `skill-split-advice.json`、`SKILL_SPLIT_ADVICE.md` |
| 人工基线锚点 | `human_anchor.py`（`human-anchor`） | `human-baseline-anchor.json`、`HUMAN_BASELINE_ANCHOR.md`（从 git 历史推出的上下界，不是测量值） |
| 分类占比对照 | `token_mix.py`（`token-mix`） | `token-mix-comparison.json`、`TOKEN_MIX_COMPARISON.md`（见下面「分类占比比总量更容易错」） |
| 计数校准 | `config/token-count-calibration.json` | 启发式对真实 BPE 的实测偏差，`scan-tokens` 默认应用 |
| PostgreSQL 后端 | `postgres.py` | 同一份契约在包内 PostgreSQL 目标 schema 上的实现 |
| 参考 HTTP 服务器 | `server.py` | 让 `openapi/` 的重连与幂等契约能被 curl 真的验证 |

## 目录

```text
src/elmos_execution_intelligence/   实现
config/                             估算默认值、人工基线、价格模板、分解模型、能力矩阵
schemas/                            23 个 JSON Schema（全部被执行校验）
sql/                                PostgreSQL 持久执行表结构（生产目标）
openapi/                            异步任务 API 与 Last-Event-ID 重连契约
references/                         架构、状态机、失败分类、持久执行、估算方法、验收标准
templates/                          执行计划与事故恢复报告模板（被渲染器真实消费）
profiles/elmos/                     elmos 自身的项目画像与任务 DAG
tests/                              单元与端到端测试
estimation/                         本地输出目录（默认被 Git 忽略）
```

## 完整链路

```bash
cd packages/execution-intelligence

make scan        # 静态语料扫描
make audit       # 01 范围审计 + 风险缺口register + 画像种子
make dag         # 02 从范围基线派生任务 DAG
make forecast    # 03-07 全部预测与报告
make plan        # 08 执行计划
make execute     # 08-12 持久执行（模拟执行器，只产出合成遥测）
make route       # 14 模型路由优化
make chaos       # 17 Chaos 与恢复验证
make calibrate   # 13 用执行遥测校准
make certify     # 16 门禁式生产就绪评估
make advise      # 超重 SKILL.md 的拆分建议
make anchor      # 从 git 历史推人工基线锚点（需先导出 git log）
make mix         # 预测假设的 token 分类占比 vs 真实会话实测占比
make durations   # 用**正确参数**产出逐节点耗时日志（见下面「--durations 的坑」）
make ingest      # 把真实遥测接进来（pytest 汇总 / 逐节点 / Agent 会话记录）
make validate    # 校验画像与 DAG
make schemas     # 对产物目录做一次 schema 自检
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
`apply-calibration` 写回任务 DAG，再重新 `forecast`。测试
`test_full_loop_from_scope_to_certification` 定义了这条闭环；是否在当前提交通过，必须以本次测试输出为准。

## 持久执行是参考实现

`durable.py` 跑在 SQLite 上，不是生产部署。它存在的意义是**让契约可测**：
harness 注入 Worker 消失、创建新的编排器对象、模拟客户端断连重连并重复提交；它没有杀真实 OS
进程，也没有执行真实集群故障。`sql/001_execution_intelligence.sql` 是 PostgreSQL 目标；更换为
PostgreSQL + Temporal 后仍需重新验证相同契约，不能从 SQLite harness 直接推断。

`sql/001_execution_intelligence.sql` 是 PostgreSQL 目标 schema，`postgres.py` 试图实现与 SQLite
后端相同的契约；`make pg-conformance PG_DSN=...` 才会在调用者提供的真实 PostgreSQL 上执行
同一批断言。仓库中的源码、README 或一次历史运行都不证明当前提交已通过该检查；必须保留本次
命令、精确 PostgreSQL/依赖版本和原始输出后，才可陈述当前提交的 PostgreSQL 工程证据。
即使该检查通过，也不证明可以上生产——Temporal、连接池、迁移管理、集群级故障演练都还没有。

**存储位置有硬约束。** SQLite 需要真正的文件锁；网络盘和 FUSE 挂载（包括桌面桥挂载的工作树）
不提供，表现为一句毫无信息量的 `disk I/O error`。把 `--store` 放在本地盘（例如 `/tmp/elmos-run.db`），
或者用 `:memory:` 跑一次性的。放错位置时本包会给出指明原因的 BLOCKED，而不是抛栈。

模拟执行器产出的遥测是合成的，但被它验证的持久性质是真的。`run-summary.json` 里
`simulated: true` 明确标注了这一点。

## 证据与提交边界

- `execute`、内存 `chaos` 和 CI 中手工生成的会话均为工程 harness；它们不能替代真实 Runner、
  生产故障演练、客户验收或独立验证。
- `certify` 会让 `block` 与 `not_certified` 返回非零，但当前本地 JSON 证据没有签名、授权者、
  独立验证者或可信采集链。即使本地文件被编辑到 `release`，也只能视为本地规则评估，不能视为
  生产批准或认证。
- `estimation/` 是默认被 Git 忽略的生成输出，可能含 session 路径、仓库清单、作者聚合和真实遥测。
  若必须保留证据，应先脱敏并复制到受治理的证据区，绑定来源、授权、哈希与独立验证；原始 Agent
  transcript、数据库、日志、缓存和任何含绝对用户路径或密钥的材料都不得提交。
- `token-mix` 不再默认遍历用户主目录。必须显式传入已经授权、已确认可处理的 `TRANSCRIPT` 路径；
  输出只保留聚合 token 数据，原始会话文件不进入本目录。
- CI 的 `/tmp/ci` readiness 步骤是负对照：它只在 synthetic evidence 被明确判为 `block` 且返回
  退出码 1 时通过。该绿色步骤证明拒绝逻辑工作，不表示 readiness PASS。
- 当前工作树中生成的 readiness 样例结论是 `block`，且不进入源码提交；其中的 PASS 仅代表单项
  本地规则成立，不能覆盖整体 BLOCK，更不能升级为生产或认证结论。

## Token 分类不重复计数

`input`、`cached_input`、`cache_write`、`output`、`reasoning_output` 互斥，`total` 是它们的和。
测试 `test_token_categories_sum_to_total_without_double_counting` 逐样本断言。
任何时候都不得把 `total` 再加回某个分类。

## 分类占比比总量更容易错

不同分类的单价可能相差很大，所以一份预测可以把 token **总量**算得很准，账单仍然明显偏离；
只比总量看不出来。`token-mix` 拿显式授权的 Agent 会话聚合与预测占比对照，并按任务轮数报告
缓存 warm-up 曲线。短任务可能由 `cache_write` 主导，长任务的 `cached_input` 占比才逐步升高，
因此偏差不是常数。具体会话数字属于被忽略的本地生成输出，不在 README 中充当当前证据。

产物里报的是**曲线**（`warmup.depths` / `cost_by_session_depth`），不是一个数；
`overstatement_factor_is_full_session_only` 标明头条倍数是**上限**。

**它不回写预测**：schema 里 `applied_to_forecast` 是 `const false`。
一个会话是**发现**，不是校准（门槛 20 个会话）。
`MODEL_COST_COMPARISON.md` 现在会声明它的占比有没有被核对过——没跑过 `token-mix`
就直接印「⚠ 占比未经核对」。

## `--durations` 的坑：默认会静默丢掉 69% 的节点

`--durations=0` **不等于**「每个节点」。pytest 会隐藏低于默认时长门槛的条目，使快速节点缺失并
抬高样本均值；具体影响取决于本次测试集合，不能沿用历史节点数或倍数。

`ingest-telemetry --durations-log` **拒收**被截断的日志（`TruncatedDurations`），
消息里直接给正确命令。要那份慢尾巴得显式加 `--allow-truncated-durations`。

正确写法（`make durations` 用的就是这个）：

```bash
pytest <tests> -q --durations=0 --durations-min=0 | tee run.log
```

## 静态扫描是什么，不是什么

`scan-tokens` 回答的是「把磁盘上的材料喂给模型**一次**要多少 token」。它是预测的输入，
不是预测本身。重复读取、返工、失败重试、子 Agent 放大都由任务 DAG 的 `token_profile` 表达。
用文件字符数直接推算整个项目的 token 预算，是 `CLAUDE.md` 明令禁止的做法。

没有 tiktoken 时用 CJK 感知的启发式计数，结果标 `cjk-aware-heuristic`、`exact_counts=false`。
计费级静态计数请用目标厂商的官方计数接口。

## 测试

```bash
make lint        # ruff（E,F,I,B,UP,S / 120 列）+ mypy --strict，与路由引擎同一标准
make test        # 全量测试
# 或直接：
python3 -m pytest -q tests
```

纯 Python、无网络、无外部工具链依赖。`test_contracts.py` 里 OpenAPI 相关用例需要 PyYAML，
缺失时自动跳过；其余全部无依赖。跳过不是通过，CI 的 PostgreSQL conformance 步骤会显式拒绝
把 skipped 用例当成绿色证据。
