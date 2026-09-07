# 持久执行

## 幂等

每个副作用一个稳定幂等键。键的作用域（`scope`）区分不同类型的操作，避免跨类碰撞。

- 键存在且 `completed` → 返回原响应，不执行。
- 键存在且 `in_flight` → 说明有并发同键请求，返回 409 或等待，不并行执行。
- 键存在但请求摘要不同 → **客户端 bug**，返回 409。不能把旧响应给一个不同的请求。

`request_digest` 这一列是关键：没有它，同一个键配不同的 body 会拿到错误的旧结果，
而且几乎无法排查。

## Outbox

状态变更和"要通知外界"这件事写在同一个事务里，发布是事务之后的独立动作。
这样不会出现"状态改了但没人知道"，也不会出现"通知发了但状态没改"。
发布失败只会导致重复通知，而重复通知由消费侧的幂等键吸收。

## Checkpoint

三种粒度，按代价递增：

| 类型 | 内容 | 何时用 |
| --- | --- | --- |
| `state` | 编排器内部状态 JSON | 每次任务状态迁移 |
| `git` | 分支 + commit | 每个产出代码的里程碑 |
| `workspace` / `object-store` | 工作区快照 + 摘要 | 重建代价高于快照代价时 |

`workspace_digest` 用于恢复时对账。摘要不匹配意味着**先恢复，不是先重跑**。

## 事件重放

`run_event` 只追加，序号在 run 行锁下分配，因此单调且无空洞。
SSE 的 `id:` 就是 `seq`；客户端用 `Last-Event-ID` 重连，服务端回放 `seq > N`。
轮询兜底 `?afterSeq=N` 读同一张表，所以客户端可以在两种方式之间切换而不丢事件、不重复。

## 为什么参考实现用 SQLite

因为幂等、重放、恢复这三条性质要**能被测试断言**。SQLite 版本在测试里可以真的杀掉一个
"Worker"、真的重启编排器、真的重连事件流。换成 Postgres + Temporal 之后，断言不变，
只是存储换了。见 `tests/test_durable.py` 和 `chaos` 命令。

## 参考实现的存储位置约束

SQLite 依赖 POSIX 字节范围锁。网络盘、FUSE 挂载（含桌面桥挂载的工作树）都不提供，
症状是一句 `disk I/O error`，完全指不出原因。参考实现因此在打开失败时抛
`StoreUnavailable` 并直接说明该把库放哪里。

生产用 PostgreSQL 时这个约束不存在，但"状态存储必须在能提供事务与锁的介质上"这条不变。

## PostgreSQL 上验证过什么（2026-08-19）

`sql/001_execution_intelligence.sql` 在**真实 PostgreSQL 16.13** 上完整执行通过：
10 张表、3 个枚举、`append_run_event` 函数、`calibration_input` 视图全部创建成功。

`postgres.py` 是同一份契约的 PostgreSQL 实现，直接跑在这份未经修改的生产 schema 上——
用它自己的枚举、它自己的 `append_run_event`、它自己的内容寻址唯一约束。
`tests/test_store_conformance.py` 的 11 条断言同时对 SQLite 和 PostgreSQL 各跑一遍，
**22 项全部通过**。没设 `ELMOS_EI_PG_DSN` 时 PostgreSQL 那一半报 skip，不报 pass。

### 跑一次之后才发现的一个缺陷

`calibration_input` 视图原本读 `estimate #>> '{token_profile,total}'`，
但 `token_profile` 里只有五个互斥分类，从来没有 `total` 这个键——
于是 `estimated_total_tokens` 恒为 NULL，视图静默失效。
已改为在视图里把五个分类相加。**这类问题只有真的把 DDL 跑起来才会暴露。**

### 仍然不成立的话

跑通 DDL 和契约一致性测试，**不等于**生产部署。没有 Temporal、没有连接池、没有
迁移管理、没有多租户压测、没有故障演练在真实集群上做过。
"这套东西可以上生产"这句话现在依然不能说。
