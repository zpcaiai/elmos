# P0-1 实施方案：Runner 集群与任务落库

> 配套产物（均已在真实 schema 上执行验证）：
> `sql/V52__execution_job_queue_and_runner_fleet.sql`、`sql/smoke_test_p0.sql`、
> `java/ExecutionJobPort.java`、`java/JdbcExecutionJobStore.java`、
> `java/RunnerFleetController.java`、`ts/jobClient.ts`

---

## 1. 现状与目标

现在一次生成任务的完整生命周期发生在 **一个 Next.js 进程内部**：

```
浏览器 → app/api/generation/jobs/route.ts
       → lib/server/generationRunner.ts::createJob()
            ├─ mkdir(ELMOS_LOCAL_RUNNER_ROOT/<tenant>/<job>)   本地磁盘
            ├─ atomicJson(project-intent.json)
            ├─ rename(analysis-review.json)                     一次性消费
            ├─ scheduledJobs.add(...)                           进程内 Set
            └─ void runJob(...)                                 fire-and-forget 子进程
```

由此产生四个硬约束，任何一个都足以挡住第二个真实付费用户：

| 约束 | 代码位置 | 后果 |
| --- | --- | --- |
| 租户与 Actor 是进程级环境变量 | `ELMOS_LOCAL_RUNNER_TENANT_ID` / `_ACTOR_ID` | 一套部署只能服务一个租户的一个人 |
| 并发上限是进程内 `Set` | `scheduledJobs`，`createJob` 中的 `>= 2` 判断 | Web 起 3 副本，实际并发变成 6，配额形同虚设 |
| 任务状态在本地磁盘 + 内存 | `jobRoot()` / capability 自述 `EPHEMERAL_PROCESS_LOCAL` | Web 发版 = 杀掉所有在跑的构建 |
| 执行令牌人工配置、24 小时手工续期 | `ELMOS_LOCAL_RUNNER_AUTH_TOKEN(_EXPIRES_AT)` | 运维每天续命，且令牌泄露即全租户失守 |

**目标**：把「任务」变成数据库里的权威记录，把「执行」搬到独立的、可水平扩展的、经过证明的 Runner 进程，且**不改变现有的证据与门禁语义**——内容寻址、浏览器复算 SHA-256、终态不可改写、失败关闭，全部保留。

**非目标**（本阶段明确不做）：跨区域调度、GPU 调度、Windows Runner、把 18 个引擎全部改造。先打穿 generation 一条线。

---

## 2. 队列选型：为什么是 PostgreSQL `SKIP LOCKED`

先算量级，再选技术。

- 任务时长：生成 1–8 分钟，整库转换 10 分钟–数小时。**分钟级，不是毫秒级**。
- 单租户并发：CNY 套餐里已经写死了——`elmos-free-trial` 1、`elmos-pro-monthly` 3、`elmos-pro-annual` 5（`V49__self_service_billing_and_usage.sql`）。
- 即使 1000 个付费租户全部打满，也只有约 3000 个在跑任务；入队速率远低于 10 次/秒。

这个量级下，队列的瓶颈不是吞吐，是**语义**。

| 候选 | 事务一致性 | 租约/心跳 | 与 RLS/审计同源 | 运维成本 | 结论 |
| --- | --- | --- | --- | --- | --- |
| **PostgreSQL `FOR UPDATE SKIP LOCKED`** | 与业务表同事务，入队和计费预留可原子完成 | 用 `lease_expires_at` 天然表达，reaper 补偿 | 同库，同审计，同备份 | 零新增组件 | **选它** |
| Redis Stream / Redisson | 与 PG 跨系统，需两阶段或对账 | 有 consumer group，但**持久化不保证** | 需另建审计 | 新增有状态组件 | 否决：宕机丢租约 → 同一任务双跑 |
| RabbitMQ | 跨系统 | ack/nack 可用，但重投可见性弱 | 需另建 | 新增组件 + 镜像队列运维 | 否决：收益不抵成本 |
| Kafka | 跨系统 | **分区顺序 ≠ 每任务租约**，rebalance 期间同分区可被两个 consumer 短暂持有 | 需另建 | 最高 | 否决：语义不匹配 |
| Temporal | 强，但引入自己的持久化 | 优秀 | 与现有 evidence 体系是两套世界观 | 引入第 19 个服务 + 团队学习成本 | 否决：本阶段过重 |

**决定性理由**：入队必须和「配额校验 + 用量预留」在同一个事务里。V49 已经有 `elmos_reserve_usage`；用外部 broker 就必须写 outbox + 对账，等于凭空多一条要维护的一致性链路。而这条链路一旦有洞，表现就是**用户被扣了额度但任务没跑**——最难解释的那种 bug。

**什么时候必须换**（写进文档，避免以后拍脑袋）：

- 持续入队速率 > 50 jobs/s，或
- `execution_job_dispatch` 活跃行数 > 10⁷，或
- 需要跨区域/跨集群调度。

届时的迁移路径已经预留好了：`execution_job_dispatch` 本身就是一张 outbox 投影，把它换成 broker 不需要动 `execution_jobs`、审计、计费或证据。

---

## 3. 目标架构

三种进程，职责不重叠：

```
┌─────────────┐   HTTPS + 会话      ┌──────────────────┐
│  Web BFF    │ ──────────────────► │  Control Plane   │
│ (Next.js)   │  /api/v1/execution  │  (Spring Boot)   │
│  无执行能力  │ ◄────────────────── │  只调度不执行     │
└─────────────┘                     └────────┬─────────┘
                                             │ PostgreSQL
                                             │ SKIP LOCKED 领取
                                    ┌────────▼─────────┐
                                    │  Runner Agent    │  ← 可水平扩展
                                    │  rootless 容器    │
                                    └──────────────────┘
                                             │ presigned PUT
                                    ┌────────▼─────────┐
                                    │  对象存储 (OSS)   │
                                    └──────────────────┘
```

一次任务的完整时序：

```
BFF          Control Plane        Runner Agent       容器          对象存储
 │ POST job        │                   │              │              │
 ├────────────────►│ enqueue (事务内:   │              │              │
 │                 │  配额+用量预留+     │              │              │
 │                 │  jobs+dispatch)   │              │              │
 │◄────────────────┤ 202 {jobId}       │              │              │
 │                 │                   │              │              │
 │                 │◄──────────────────┤ claim (SKIP LOCKED)         │
 │                 ├──────────────────►│ lease + 一次性令牌           │
 │                 │                   ├─────────────►│ 启动 rootless │
 │                 │◄──────────────────┤ heartbeat    │              │
 │                 ├──────────────────►│ {cancel:false}              │
 │ GET job         │                   │              ├─────────────►│ PUT 产物
 ├────────────────►│                   │◄─────────────┤              │
 │◄────────────────┤ RUNNING 45%       ├──────────────────────────────► verify
 │                 │◄──────────────────┤ complete(SUCCEEDED)         │
 │ 下载             ├──────────────────►│              │              │
 ├────────────────►│ presigned GET ────┼──────────────┼─────────────►│
 │◄────────────────┤                   │              │              │
 │ 浏览器复算 SHA-256                    │              │              │
```

**关键边界没有变**：控制面不启动容器、不执行客户代码、不持有长期存储凭据。它只发租约、收报告。这与 V9/B36 已经确立的「执行者不能同时裁判」是同一条线。

---

## 4. 数据模型与不变量

完整 DDL 见 `V52`。这里只讲**为什么这么切**。

### 4.1 两张表，两种租户模型

| 表 | RLS | 承载 | 理由 |
| --- | --- | --- | --- |
| `execution_jobs` / `execution_job_events` | **FORCE ROW LEVEL SECURITY** | 客户请求内容、检查点、失败码 | 与 V49/V51 完全一致 |
| `execution_job_dispatch` / `execution_dispatch_org_counters` | **无 RLS（刻意）** | 只有 ID、能力、优先级、租约时间 | 公平调度必须一次看见所有租户，而 `app.organization_id` 是每事务一个值，天生看不到 |

这是本方案唯一一处偏离「所有表都 RLS」的地方，因此做了三重补偿：

1. dispatch 表**不含任何客户内容**——没有 payload，没有文件名，没有仓库地址；
2. `REVOKE ALL FROM PUBLIC`，只 `GRANT` 给专用的 `elmos_scheduler` 角色；
3. 所有跨租户操作只能经过 `SECURITY DEFINER` 函数，函数内部逐条绑定明确的 organization。

### 4.2 五条数据库级不变量

这些不是代码约定，是**改不掉的约束**：

| 不变量 | 实现 | 防的是什么 |
| --- | --- | --- |
| 终态不可改写 | `elmos_guard_execution_job_transition()` 触发器 | 新写的接口把 FAILED 改成 SUCCEEDED |
| Runner 未证明 → 不可 READY | `runner_nodes_ready_requires_attestation` CHECK | 有人为了让流水线绿，把 attestation 默认成 true |
| 生产镜像必须是 digest | `execution_jobs_runner_image_digest` 正则 CHECK | `:latest` 悄悄进生产 |
| 无有效订阅 → 并发上限 0 | `elmos_execution_concurrency_limit()` 返回 0 | 欠费租户继续白嫖算力 |
| 事件仅追加 | `elmos_forbid_append_only_mutation()` | 事后抹掉失败记录 |

### 4.3 并发上限只有一个来源

`elmos_execution_concurrency_limit()` 直接读 `self_service_pricing_plan_versions.concurrent_job_limit`。**不新建配额表**——多一张表就多一处会漂移的真相。改套餐即改并发，无需二次同步。

烟测里验证过：`org-a`（pro-monthly）= 3，`org-b`（trial）= 1，无订阅 = 0。

---

## 5. 公平调度：为什么不是简单的 FIFO

朴素 FIFO 有一个必然发生的故障：一个租户一次提交 200 个任务，后面所有租户排队到明天。

`elmos_claim_execution_jobs` 的排序是：

```sql
ORDER BY coalesce(c.leased_count, 0) ASC,   -- 当前在跑得少的租户优先
         d.priority DESC,
         d.enqueued_at ASC
FOR UPDATE OF d SKIP LOCKED
```

再在循环里对每个候选做一次租户配额检查，超限即 `CONTINUE`（跳过该租户继续找下一个），不是 `EXIT`。

`leased_count` 走 `execution_dispatch_org_counters` 而不是 `count(*)` 子查询，是为了让排序保持 O(1)；代价是计数器可能漂移，所以 reaper 每轮都调 `elmos_reconcile_dispatch_counters()` 校正。烟测断言了整个流程跑完后漂移为 0。

**已验证的公平性**：`org-a` 排 5 个、`org-b` 排 2 个，一个容量为 4 的 Runner 领取的结果是 **3 + 1**（各自被套餐卡住），而不是 4 + 0。小租户没有被饿死。

---

## 6. Runner Agent 设计

### 6.1 状态机

```
        register ──► REGISTERED ──(人工/自动验证 attestation)──► READY
                                                                  │
                          ┌────────── claim ◄──────────────────────┤
                          │                                        │
                     RUNNING(n) ── complete ────────────────────►  │
                          │                                        │
                     drain 请求 ──► DRAINING ──(排空)──► RETIRED    │
                          │                                        │
                   心跳超时 120s ──► LOST ◄───────────────────────  ┘
```

### 6.2 执行循环（伪码）

```
loop:
  if draining and running == 0: exit(0)
  POST /runner/v1/nodes/{id}/heartbeat        # 节点级心跳，拿 drain 信号
  if capacity_free and not draining:
      leases = POST /runner/v1/leases/claim
      for lease in leases: spawn(execute(lease))
  sleep(backoff)                               # 空转时指数退避到 5s

execute(lease):
  workdir = mkdtemp()                          # 本节点临时目录，任务结束即删
  container = podman run \
      --rm --read-only --network=none \
      --cap-drop=ALL --security-opt=no-new-privileges \
      --cpus=<budget> --memory=<budget> --pids-limit=<budget> \
      --user=<非 root> \
      <runner_image@sha256:...>                # digest 由 job 携带，agent 不选镜像
  every 30s:
      r = POST /runner/v1/leases/{id}/heartbeat {stage, progress, checkpoint}
      if r.cancelRequested: container.SIGTERM(); grace 30s; SIGKILL
  产物:
      sha = sha256(file)
      ticket = POST /api/v1/execution/artifacts/upload-ticket
      PUT ticket.uploadUrl                     # 直传对象存储，不过控制面
      POST .../verify                          # 服务端复算摘要后才 AVAILABLE
  POST /runner/v1/leases/{id}/complete {status, resultStatus, failureCode}
```

### 6.3 三个容易做错的地方

**取消必须是拉模型。** 控制面不能反向连 Runner——Runner 在客户 VPC 里、在 NAT 后面、随时扩缩。取消写进 `cancel_requested_at`，Runner 下次心跳（≤30 秒）拿到信号后自己 SIGTERM。烟测验证了这条链路。

**产物直传，不过控制面。** 控制面转发大文件会把自己变成带宽瓶颈，也会让内存打满。Runner 拿 presigned PUT 直接写对象存储。

**Agent 不选镜像。** `runner_image` 由 job 携带且必须是 `@sha256:`，数据库 CHECK 兜底。Agent 只是执行者，不是策略决定者——否则一个被攻陷的 Agent 就能换掉工具链。

### 6.4 优雅排空

发版时先 `drain`：Agent 停止 claim，跑完手上的任务再退出。`elmos_claim_execution_jobs` 在 `drain_requested_at IS NOT NULL` 时直接返回空。这是「helm upgrade 期间在途任务零丢失」的实现基础。

---

## 7. 失败模式与防双跑论证

「同一个任务被两个 Runner 同时执行」是这类系统最贵的 bug（重复计费、产物互相覆盖、PR 开两个）。逐条论证：

| 场景 | 会双跑吗 | 保护机制 |
| --- | --- | --- |
| 两个 Runner 同时 claim | 否 | `FOR UPDATE ... SKIP LOCKED` 行级互斥 |
| Runner 卡住但进程活着 | 否 | 心跳停 → 租约过期 → reaper 回收；老 Runner 再心跳会拿到 `ELMOS_LEASE_NOT_ACTIVE` |
| Runner 被 kill -9 | 否 | 同上，且新租约是新 `lease_id` + 新令牌，旧令牌永远失配 |
| 网络分区，Runner 仍在跑 | **可能短暂重叠** | 租约过期后旧 Runner 无法 complete（凭据失配），其产物无法发布（`content_objects` 按 `(org, sha256)` 唯一 + 服务端校验）；重叠期的副作用被限制在它自己的临时目录内 |
| reaper 多副本同时跑 | 否 | 单实例 + `SKIP LOCKED`；建议加 `pg_advisory_lock` |
| Runner 重复上报 complete | 否 | `elmos_complete_execution_job` 幂等，已释放的租约返回 `false` |
| 用户重复点提交 | 否 | 幂等键 = `sha256(tenant, actor, analysisDigest)`，同摘要返回原 job，不同摘要冲突 |

网络分区那一行是唯一「不能完全消除」的：分布式系统里，你无法在不通信的情况下确认对方已死。做法是**限制爆炸半径**而不是假装它不存在——重叠期间旧 Runner 的一切副作用都写不进权威存储。任何声称完全消除的设计都在骗自己。

---

## 8. 从 `generationRunner.ts` 迁移：六步绞杀

原则：**每一步都可独立上线、独立回滚，且线上始终只有一条执行路径生效**。绝不搞「两条路径并行跑一周」——那会产生两套不一致的任务状态。

### S0 · 准备（不改行为）

- 应用 V52，跑 `smoke_test_p0.sql`。
- 新增开关 `ELMOS_EXECUTION_MODE = INPROCESS | CONTROL_PLANE`，默认 `INPROCESS`。
- **验收**：全量回归通过，行为零变化。**回滚**：删除迁移即可（新表无人写）。

### S1 · 抽出纯函数

把 `generationRunner.ts` 里与执行无关的部分移到 `lib/shared/generationPlan.ts`：`validateCreate`、多实体边界校验（`PRODUCTION_PROFILE_SINGLE_ENTITY_ONLY`）、`project-intent.json` 构造。

这些逻辑将来要在控制面和 BFF 各跑一次（BFF 快速反馈、控制面权威校验），必须**字节级一致**。

- **验收**：新增契约测试，对 20 组固定输入断言 `project-intent.json` 的字节输出与迁移前完全一致。
- **回滚**：纯重构，`git revert`。

### S2 · 审阅摘要迁到数据库 ⚠️ 最关键的一步

现在的一次性消费靠文件 `rename()`：

```ts
await rename(analysisReviewFile(runner, context, digest), confined(root, "analysis-review.json"));
// 失败 → ANALYSIS_REVIEW_ALREADY_CONSUMED
```

这个语义（一次性、原子、失败即拒）必须保住，换成：

```sql
UPDATE analysis_reviews
   SET consumed_at = now(), consumed_by_job = :jobId
 WHERE organization_id = :org AND analysis_digest = :digest AND consumed_at IS NULL
RETURNING request_payload;
-- 零行 → ANALYSIS_REVIEW_ALREADY_CONSUMED
```

- **验收**：并发消费同一摘要 100 次，恰好 1 次成功、99 次拿到 `ALREADY_CONSUMED`。
- **回滚**：开关切回文件路径（本步保留双写一个发布周期）。

### S3 · BFF 改调控制面

用 `ts/jobClient.ts` 替换 `generationRunner` 的四个导出。`app/api/generation/jobs/**` 只改 import。

```ts
// 之前
import { createJob, getJob, cancelJob } from "../../../lib/server/generationRunner";
// 之后
import { createJob, getJob, cancelJob } from "../../../lib/server/jobClient";
```

此时任务已经落库、可跨副本查询、重启不丢，但**还没有 Runner**——控制面里的任务停在 `QUEUED`。因此 S3 和 S4 要在同一个发布窗口内完成，或者 S3 先只对内部租户开启。

- **验收**：Playwright 走一遍提交 → 刷新 → 恢复；杀掉 Web Pod 后任务记录仍在。
- **回滚**：开关切回 `INPROCESS`。

### S4 · Runner Agent 上线

部署 Agent，注册 → 验证 attestation → READY。生成镜像固定 digest。`ELMOS_LOCAL_RUNNER_EXECUTOR=HOST_DEVELOPMENT` 在 `NODE_ENV=production` 下继续拒绝（这条现有保护保留）。

- **验收**：两个租户同时提交，落在不同 Runner；`kill -9` Runner 后任务 90 秒内被接管或标记；`drain` 后新任务不再进入该节点。
- **回滚**：Runner 全部 drain + 开关回 `INPROCESS`；已入库的任务标记 `LOST` 并通知用户重跑（需要提前准备这个话术）。

### S5 · 产物改 presigned 下载

见 `03-P0-3`。浏览器端 SHA-256 复算逻辑**一行不改**——它本来就是对的。

- **验收**：Web 起 3 副本，任一副本签发的链接都能下载且摘要一致；篡改 1 字节后浏览器拒收。

### S6 · 删除进程内执行路径

删掉 `runJob`、`scheduledJobs`、`jobRoot` 及相关子进程代码（约占 `generationRunner.ts` 的 60%）。`ELMOS_LOCAL_RUNNER_*` 降级为仅本地开发；`ELMOS_TRUSTED_SINGLE_TENANT_ORGANIZATION_ID` 同步降级。

- **验收**：全仓搜索 `scheduledJobs`、`ELMOS_LOCAL_RUNNER_TENANT_ID` 零命中（生产代码路径）；`production-readiness-check` 通过。
- **回滚**：本步不可回滚，因此必须在 S4/S5 稳定运行至少两周后再做。

### 后续（不在 P0-1 范围）

- `translationRunner.ts` 复用同一套，`business_line = TRANSLATION`，`checkpoint_cursor` 承载现有的断点续跑游标。
- Spring 代理复用同一套，`business_line = SPRING_UPGRADE`。
- **`startRuntime` / `stopRuntime`（生成项目的一键预览）需要单独设计**：它是长驻进程而非一次性任务，应建模为独立 job kind + 强制 TTL + 独立端口分配，绝不能继续留在 BFF 进程里。这是 S6 之前必须解决的遗留项。

---

## 9. 运维

**Reaper**：控制面内 `@Scheduled(fixedDelay=15s)`。多副本时用 `pg_advisory_lock(hashtext('elmos_execution_reaper'))` 保证同时只有一个在跑。

**必须暴露的指标**（`/actuator/prometheus`）：

- `elmos_execution_queue_depth{business_line}` — 队列深度，> 100 持续 5 分钟告警
- `elmos_execution_claim_latency_seconds` — 入队到领取的延迟，P95 > 60s 告警
- `elmos_execution_lease_expired_total` — 租约过期计数，突增即 Runner 有问题
- `elmos_runner_nodes_ready` — READY 节点数，为 0 立即告警
- `elmos_dispatch_counter_drift_total` — 计数器漂移修正次数，持续非 0 说明有并发 bug

**容量估算**：单个 `elmos_claim_execution_jobs` 调用在 dispatch 表 10⁵ 行时约 2–5ms（索引 `idx_execution_job_dispatch_ready` 覆盖）。20 个 Agent 每 2 秒 claim 一次 = 10 QPS，PG 毫无压力。

---

## 10. 验收标准（可执行）

数据库层已全部验证通过（`smoke_test_p0.sql`，在真实 V1–V51 schema 上执行）：

- [x] 套餐驱动的并发上限：pro=3 / trial=1 / 无订阅=0
- [x] 公平调度：5 vs 2 排队，容量 4 → 领取 3+1，小租户不饿死
- [x] 饱和后二次 claim 返回 0，不超发
- [x] 幂等：同摘要返回原 job；异摘要冲突
- [x] 可变镜像标签在数据库层被拒
- [x] 未证明的 Runner 无法进入 READY
- [x] 伪造租约令牌被拒
- [x] 取消经心跳传达到 Runner
- [x] 终态无法被 UPDATE 改写
- [x] Runner 失联 → 租约过期 → 自动重排队
- [x] 计数器零漂移

端到端还需要（S4 之后）：

- [ ] 两租户并发提交，落在不同 Runner，互不可见
- [ ] `kill -9` Web Pod，任务跑完，新 Web 实例能查到终态
- [ ] `kill -9` Runner，90 秒内接管或标记失败重投
- [ ] `helm upgrade` 期间在途任务零丢失
- [ ] 恶意仓库（构建脚本死循环 + 10GB）在预算内失败关闭，不影响其他租户

---

## 11. 工作量估算

| 步骤 | 内容 | 人日 |
| --- | --- | --- |
| S0 | 迁移 + 烟测接入 CI | 1（SQL 已完成） |
| S1 | 抽纯函数 + 契约测试 | 3 |
| S2 | 审阅摘要迁库 + 并发测试 | 3 |
| S3 | jobClient 接入 + 控制面 API + Playwright | 5 |
| S4 | Runner Agent（含容器执行、心跳、取消、排空） | 10 |
| S5 | 对象存储接入（见 P0-3） | 5 |
| S6 | 删除旧路径 + 回归 | 3 |
| | **合计** | **约 30 人日** |

两人并行约 3 周。S4 是关键路径，建议最早启动。
