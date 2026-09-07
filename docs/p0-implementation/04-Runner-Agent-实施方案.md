# P0-1 / S4 实施方案：Runner Agent

> 配套产物：`runner-agent/`（14 个主源文件 2364 行 + 616 行验收套件）
> **状态：已编译（`-Xlint:all -Werror` 零警告）、已执行验收（94 项断言全绿，含 4 个跑真实 HTTP 的端到端场景）**
>
> 复现：`cd runner-agent && ./build_and_test.sh`

---

## 1. 两个设计决策，先讲清楚

### 1.1 为什么是零依赖

`pom.xml` 的 `<dependencies/>` 是空的。这不是偷懒，是三条理由：

1. **它是唯一贴着不受信任代码跑的组件。** Agent 与客户的构建脚本共处一台机器，依赖树就是攻击面。一个 Spring Boot 应用拉进来 60+ 个 jar，每一个都是要跟的 CVE。
2. **仓库本身的供应链纪律要求它。** 你已经把生成物的 GitHub Action 固定到 40 位提交摘要、把基础镜像固定到 manifest digest。一个自己拖着几十个传递依赖的 Agent 与这条纪律矛盾。
3. **它能被读完。** 14 个文件、2364 行，一个人一个下午可以逐行审计。产出的 jar 是 **58 KB**。

代价是要自己写一个 JSON 读写器（356 行）。这是本方案里唯一"自己造轮子"的地方，因此它的测试最密：转义、非 ASCII、恶意深度嵌套、截断输入、非法转义各一条断言。

### 1.2 为什么仍然是 Java

因为你已经有 18 个 Java 服务、一套 Java 21 工具链、一套构建纪律。用 Go 重写会更小，但会新增一条工具链、一套依赖管理、一套发布流程——为了省几十 MB 内存，不值。JDK 21 的虚拟线程让「每个任务一个线程」的写法回归简单，正好适配这种 IO 密集、并发个位数的场景。

---

## 2. 组件清单

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `RunnerAgentMain` | 116 | 启动顺序：校验配置 → 探测沙箱 → 清扫孤儿工作区 → 注册 → 轮询 |
| `AgentConfig` | 216 | 环境变量解析与失败关闭校验 |
| `SandboxAttestation` | 145 | 自检 rootless / 只读根 / capability / 网络策略 |
| `ControlPlaneClient` | 263 | HTTP 协议 + **失败分类** |
| `LeasePoller` | 153 | claim 循环、并发闸、排空协调 |
| `JobExecutor` | 210 | 单任务编排：容器 → 监督 → 产物 → 上报 |
| `HeartbeatPump` | 128 | 续租、取消信号、**自我围栏** |
| `ContainerRuntime` | 141 | 容器命令构造与强制终止 |
| `JobWorkspace` | 160 | 目录隔离与保证清理 |
| `ArtifactPublisher` | 134 | 流式摘要、直传、发布 |
| `ProcessRunner` | 173 | 进程封装（唯一能碰宿主的地方） |
| `Json` / `Backoff` / `AgentMetrics` | 525 | 基础设施 |

**`ProcessRunner` 是刻意抽成接口的**：这个 Agent 能对宿主做的所有事情都经过这一个文件，"它能执行什么"这个问题读一个文件就能回答。

---

## 3. 启动顺序即安全策略

```
main()
  ├─ AgentConfig.fromEnvironment()      配置不合法 → exit 78，不启动
  ├─ config.validateTimings()           心跳 × 3 > 租约 → 拒绝
  ├─ SandboxAttestation.probe()         自检四项
  │    └─ 不完整且未显式允许宿主执行 → exit 78
  ├─ JobWorkspace.sweepOrphans()        清掉上次崩溃留下的工作区
  ├─ metrics.start(127.0.0.1:9464)      只绑回环
  ├─ client.register()                  失败重试 10 分钟，然后 exit 75
  └─ poller.run()
```

**证明不了自己沙箱的 Agent 从不索要工作。** 这里也有一层清醒：自检是*自我声明*，不是证明。数据库的 `runner_nodes_ready_requires_attestation` 还要求一个具名验证人和验证时间戳，所以撒谎的节点仍然无法自我提升到 READY。自检买到的是——**诚实但配置错误的节点会当场拒绝启动**，而不是等人发现。

配置校验里有几条值得单独说：

- 容器引擎必须是**绝对路径**。相对名走 PATH，共享节点上的 PATH 你未必控制得住。
- `ELMOS_ENVIRONMENT=production` 时**拒绝宿主执行**。这条是给"临时用宿主顶一下"准备的墓碑。
- 秘密优先读文件（`*_FILE`），这样令牌不出现在进程环境里。
- **心跳间隔 × 3 必须 ≤ 租约**。一次丢包就掉租约的配置会直接导致双跑，所以在启动时就拒绝。

---

## 4. 防双跑：自我围栏机制

这是整个 Agent 最重要的一段，也是最容易写错的一段。

场景：Agent 与控制面之间网络分区，容器还在跑。控制面看到租约过期，把任务交给另一个 Runner。现在**两个容器在为同一个任务工作**——重复计费、产物互相覆盖、PR 开两个。

分布式系统里你无法在不通信的情况下确认对方已死。所以做法不是"消除"，是**让掉队的一方自己退场**：

```java
// HeartbeatPump：租约续不上时，主动宣告自己失去租约
long silentSeconds = Duration.between(lastSuccess, Instant.now()).toSeconds();
if (silentSeconds >= config.leaseSeconds() - SAFETY_MARGIN_SECONDS) {
    leaseLost.compareAndSet(null, "LEASE_RENEWAL_TIMED_OUT");
}
```

```java
// JobExecutor.supervise：一旦失去租约，杀掉自己的容器且什么都不上报
String lost = pump.leaseLost();
if (lost != null) {
    containers.stop(execution, config.cancelGraceSeconds());
    metrics.increment(AgentMetrics.JOBS_ABANDONED);
    return Outcome.ABANDONED;      // 注意：没有 client.complete(...)
}
```

三个细节：

- **提前 10 秒**（`SAFETY_MARGIN_SECONDS`）就不再信任租约，覆盖时钟偏移和还在路上的那个请求。
- **不上报**是关键。控制面已经把任务给了别人，这时候一个迟到的 `SUCCEEDED` 会覆盖更新的事实。
- 心跳收到 **409/403/412** 时立刻围栏，不重试——那些状态码的意思就是"这活儿不是你的了"，重试就是双跑本身。

`ControlPlaneClient` 因此把响应分成三类，每类的正确反应不同：

| 类别 | 状态码 | 反应 |
| --- | --- | --- |
| 传输失败 / 5xx / 429 | — | 可重试，控制面可能在重启 |
| 租约已失 | 403 / 404 / 409 / 412 | **永不重试**，立刻放弃 |
| 其他 4xx | — | 本 Agent 的 bug，以稳定码失败 |

验收里最硬的一条断言就是这个：**"abandoned job reports nothing"** —— 假控制面对心跳返回 409，Agent 必须一条完成记录都不写。

---

## 5. 容器沙箱：逐条解释

```java
--rm --name elmos-<jobId>
--network=none                      // 工作负载零网络
--read-only                         // 只读根文件系统
--cap-drop=ALL                      // 丢弃全部 capability
--security-opt=no-new-privileges    // 禁止提权
--user=65532:65532                  // 容器内非 root
--userns=keep-id                    // rootless 映射显式化
--cpus=<budget/1000>
--memory=<budget>m
--memory-swap=<budget>m             // ← 关键
--pids-limit=512
--ulimit=nofile=4096:4096
--volume=<in>:/elmos/in:ro          // 输入只读
--volume=<out>:/elmos/out:rw
--volume=<tmp>:/elmos/tmp:rw
--tmpfs=/tmp:rw,noexec,nosuid,size=256m
```

三处容易漏的：

**`--memory-swap` 必须等于 `--memory`。** 不设的话内核允许工作负载用 swap 溢出内存预算，一个失控的构建会拖垮整个节点而不是被 OOM 掉。这是最常见的容器预算错误。

**输入目录只读。** 工作负载只能写 `out` 和 `tmp`。被攻陷的构建改不了自己的输入，也就无法让证据链描述一件没发生过的事。

**环境变量只有三个**：`ELMOS_JOB_KIND`、`ELMOS_INPUT_DIR`、`ELMOS_OUTPUT_DIR`。`ProcessBuilder` 的环境被**清空后重建**，所以入组令牌、租约令牌、控制面地址一个都不会泄进容器。验收里有两条专门断言这一点。

还有一条原则：**Agent 从不接受来自任务载荷的容器 flag**。能影响自己容器参数的工作负载等于没有沙箱。镜像同理——必须是 `@sha256:` digest，数据库 CHECK 和 Agent 各校验一次。

---

## 6. 取消是拉模型

控制面无法反向连接 Runner：Runner 在 NAT 后、在客户 VPC 里、随时扩缩。所以：

```
用户点取消 → execution_jobs.cancel_requested_at
           → Runner 下次心跳（≤30s）拿到 {"cancelRequested": true}
           → SIGTERM 容器 → 宽限 30s → SIGKILL
           → 引擎级 kill + rm -f（兜底）
           → 上报 CANCELLED
```

最后那步兜底不能省：某些引擎下客户端进程退出后容器还在跑，只 `destroy()` 客户端是杀不掉工作负载的。

端到端验收测量了这条链路：**取消在一个心跳周期内被观测到**（断言 < 20 秒）。

---

## 7. 优雅排空：让 `helm upgrade` 安全

```
SIGTERM / 控制面 drain 标志
  → poller.requestDrain()          立即停止 claim
  → 已持有的任务跑完
  → 全部完成后 run() 返回，进程干净退出
```

`elmos_claim_execution_jobs` 在 `drain_requested_at IS NOT NULL` 时直接返回空，双向保险。

**`terminationGracePeriodSeconds: 3900`** 是 K8s 清单里最容易被随手改小的一行。它必须大于最长任务预算，否则每次发版都会截断在跑的客户构建——这正是排空协议存在的理由。清单里写了注释。

---

## 8. 可观测性

`/metrics`（Prometheus 文本格式）、`/healthz`，只绑 `127.0.0.1`。Runner 旁边就是不受信任的工作负载，指标端口不该是网络上又一个可攻击面。

| 指标 | 用途 |
| --- | --- |
| `elmos_runner_jobs_claimed_total` | 吞吐 |
| `elmos_runner_jobs_abandoned_total` | **持续非 0 = 网络或租约有问题，最该告警的一条** |
| `elmos_runner_heartbeat_failures_total` | 控制面连通性 |
| `elmos_runner_running_jobs` | 容量利用 |
| `elmos_runner_draining` | 发版可见性 |

HPA 按 `elmos_execution_queue_depth` 扩缩，**不按 CPU**——Agent 是监督者，它自己的 CPU 说明不了有多少活在排队。缩容窗口 900 秒，因为一个正在终止的 Pod 可能握着一个一小时的构建。

---

## 9. 验收记录

`./build_and_test.sh` 实际执行结果：**94 项断言全绿**。

单元层（覆盖 JSON、配置、镜像固定、容器 flag、工作区、摘要、角色推导、进度协议、退避）：

- [x] JSON 保留转义、中文与 emoji、拒绝 4 类恶意输入
- [x] 配置拒绝：非回环 http、短令牌、文件系统根、生产环境宿主执行、PATH 引擎、过密心跳
- [x] 可变镜像标签被拒，短摘要被拒，null 被拒
- [x] 容器命令带齐 9 个隔离 flag，输入只读挂载
- [x] **入组令牌与控制面地址都不进容器**
- [x] 工作区 0700、跳过符号链接产物、拒绝路径穿越的 jobId、孤儿清扫
- [x] 流式 SHA-256 匹配 `"abc"` 的公开测试向量
- [x] 注入了 shell 元字符的伪进度行被拒绝解析

端到端层（真实 HTTP 假控制面 + 假容器引擎脚本）：

- [x] **成功路径**：claim → 执行 → 上传 → 发布 → 上报 SUCCEEDED/PASSED → 工作区清理
- [x] **取消路径**：一个心跳周期内观测到取消 → 杀容器 → 上报 CANCELLED → **不发布任何产物**
- [x] **租约被夺**：心跳 409 → ABANDONED → **零上报、零发布**、工作区仍被清理
- [x] **排空**：drain 标志被观测 → **claim 计数为 0**

假控制面说的是真协议、走真 HTTP，没有 mock 框架，所以序列化、请求头、状态码分类、失败分类都是真跑过的。

**尚未验证、需要真实环境的部分**（诚实标注，不冒充）：

- [ ] 真实 podman rootless 下的 `--userns=keep-id` 行为
- [ ] 真实 OOM / PID 耗尽下的容器回收
- [ ] 真实网络分区下的自我围栏（需要故障注入）
- [ ] K8s 滚动更新期间的零任务丢失
- [ ] 多副本 Agent 对同一队列的竞争（需要真实 PostgreSQL + 控制面）

---

## 10. 剩余工作与人日

已完成（约 6 人日的产出）：

| 项 | 状态 |
| --- | --- |
| 配置、注册、自检、清扫 | 完成并验收 |
| claim 循环、并发闸、退避 | 完成并验收 |
| 容器执行与沙箱 flag | 完成并验收 |
| 心跳、取消传播、自我围栏 | 完成并验收 |
| 产物摘要、直传、发布 | 完成并验收 |
| 优雅排空与关闭 | 完成并验收 |
| 指标与健康检查 | 完成并验收 |
| Dockerfile、K8s 清单、HPA、NetworkPolicy | 完成（镜像 digest 待填） |

剩余（约 4 人日）：

| 项 | 人日 | 说明 |
| --- | --- | --- |
| 控制面侧的 upload-ticket / publish 端点 | 1.5 | `RunnerFleetController` 需补这两个路由 + `S3ObjectStore` |
| 镜像 digest 固定与 allowlist 接入 | 0.5 | 替换 Dockerfile 与清单里的 `REPLACE_WITH_APPROVED_DIGEST` |
| 真实 podman 节点上的冒烟 | 1 | `--userns=keep-id`、OOM 回收、真实镜像拉取 |
| 故障注入演练（分区、kill -9、滚动更新） | 1 | 对应上面 5 条未验证项 |

---

## 11. 与 P0-1 主方案的衔接

本 Agent 对应主方案的 **S4**。前置条件是 S3（BFF 改调控制面）已上线，否则控制面里没有 `QUEUED` 的任务可领。

上线顺序建议：

1. 单节点 + 单租户灰度，`ELMOS_RUNNER_MAX_CONCURRENCY=1`，只跑内部租户
2. 观察 `jobs_abandoned_total` 一周，应恒为 0
3. 扩到 3 副本，开放给全部租户
4. 稳定两周后执行 S6（删除 BFF 内的执行路径）
