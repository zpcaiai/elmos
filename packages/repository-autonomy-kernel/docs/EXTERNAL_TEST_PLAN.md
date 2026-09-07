# Repository Autonomy Kernel v2.0.0 外部边界测试计划

## 1. 测试原则

本计划验证真实外部能力，不把静态文件、mock、health endpoint、`LOCAL_ENGINEERING_VALIDATED` 或手工填写的 response 当成生产证据。所有测试都绑定 exact package/adapter/image/migration/provider/region/tenant/commit digest，并保存原始输出和可重放命令。

仓库现已物化 T00–T08 的 125 个强制 case，其中 T06 精确包含 7 × 12 = 84 个 Provider conformance 单元。`CertificationEvidenceIngestor` 只接受 allowlist case，外部 PASS 必须由 host trust store 验签并绑定真实来源、授权 receipt、原始制品、环境和 replay；生产者与验证者必须不同。当前仓库测试只执行本地工程 fixtures，因此矩阵外部项继续报告 `NOT_RUN`，E1–E5 与 P05 继续报告 `NOT_CERTIFIED`。

测试数据分为四套且必须独立：

1. development：可重复的安全样例；
2. negative：越权、篡改、超时、重复、故障样例；
3. holdout：测试执行者不可提前调优的仓库和任务；
4. representative：获得授权的真实客户仓库和生产等价负载。

## 2. 通过状态与证据包

每个 test case 需要：`case_id`、测试 Skill、输入 digest、源快照/commit、环境和版本、tenant/account、授权 receipt、executor、独立 verifier、原始日志/trace/object hash、期望 oracle、实际结果、清理 receipt、重放命令和时间窗口。

结果只允许：`PASS`、`FAIL`、`BLOCKED`、`UNKNOWN`、`NOT_RUN`。`UNKNOWN` 不能重试副作用操作，必须先 reconciliation；`NOT_RUN`、缺原始证据、self-verification、只测 mock、缺 holdout 或不完整 repeat 都不能进入认证汇总。

本地工程测试另外覆盖外部 sidecar 的 executable digest 漂移、协议越权、环境引用缺失、二进制载荷、超时、输出洪泛、畸形响应、secret 泄漏和进程组终止。统一执行前运行：

```bash
PYTHONPATH=src python -m elmos_repository_autonomy.cli external-preflight \
  --manifest /approved/path/external-qualification-manifest.json
```

返回 `READY_FOR_AUTHORIZED_EXECUTION` 只表示绑定完整；命令不会执行 manifest 中的 adapter，也不会把 T01–T08、E1–E5 或 P05 改为通过。

## 3. 测试矩阵

### T00：本地合同和反伪造基线

| ID | 场景 | 期望 |
|---|---|---|
| T00-01 | ZIP 路径、digest、31 Skill、20 Schema、资产清单 | 精确匹配；不执行附件代码 |
| T00-02 | 31 handler 正常、空输入、未知 Skill、未知输出字段 | 结构化结果；错误不能泄漏 stack trace |
| T00-03 | run 状态非法跳转、事件顺序破坏、checkpoint hash 篡改 | fail-closed，拒绝恢复 |
| T00-04 | 同一租户重复 idempotency key | 不产生第二个 run/side effect |
| T00-05 | 跨租户读取 artifact/run/cache/tool call | 拒绝并记录审计 |
| T00-06 | completion claim 自称成功但缺部署/独立证据 | 不签发 P05 |

执行命令：`make repository-autonomy-kernel`。这是 E1 工程基线，不是 E2-E5 真实外部证据。

### T01：PostgreSQL 17、迁移和 RLS

- `V001` 到 `V006` 在全新 PostgreSQL 17 数据库按序执行；重复执行、迁移锁竞争、中途失败恢复和向前/回滚脚本分别测试。
- 设置合法 tenant context 时只能读写本租户；缺少、伪造、过期或格式非法的 `app.tenant_id` 必须拒绝。
- parent/child run、artifact、evidence、tool、finding、cache、cost、eval 和 ELO 全链路跨租户 negative。
- 事务提交前断电/连接断开后重连，验证 outbox/event/checkpoint/lease 状态和唯一约束。
- 备份恢复到隔离数据库，执行 schema、行数、hash、事件 replay 和租户隔离 holdout 对比。

通过门槛：迁移无人工修补；RLS negative 100% 拒绝；恢复后 digest 和重放状态一致；独立 verifier 使用不同数据库连接和脚本。

### T02：真实 SCM

- exact commit clone/fetch/read：仓库、分支、tag、submodule、LFS 和 sparse workspace 分别验证完整性。
- permission matrix：read、branch、PR、write、tag、webhook、delete 分开授权；请求体不能提升权限。
- negative：错误 commit、force-push、删除仓库、撤销 token、跨租户 native ID、私有仓库无授权、恶意文件路径、超大仓库、LFS 缺对象。
- reliability：中断重连、重复 webhook、重复 PR 请求、checkpoint resume、stale workspace lease 和未知写入结果。
- 真实写入只在隔离 fork/branch 执行，并验证 diff、commit、PR、回滚和清理。

通过门槛：所有 write scope 有批准；exact commit 可重放；未 hydration workspace 不得进入后续写入；未知结果不自动重试。

### T03：S3/兼容对象存储

- put/read-back：内容 hash、size、media type、tenant key prefix、版本 ID 和 metadata 全部核对。
- signed URL：短 TTL、method/content-type/hash 绑定、过期和错误租户拒绝。
- security：无 public ACL、服务端加密、KMS key policy、日志不含 secret；跨租户同 hash 不得共享权限。
- lifecycle：Legal Hold、retention、版本删除、GC dry-run、orphan cleanup 和恢复演练。
- 故障：404、5xx、超时、部分上传、重复上传、ETag/hash 不一致；结果不确定时标记 `UNKNOWN`。

通过门槛：read-back SHA-256 100% 一致；所有删除可审计且受 hold 保护；对象存储与 evidence/artifact digest 关系可重放。

### T04：Event Bus

- publish/consume：tenant/run/step correlation、顺序键、event ID、causation ID、消费位点和 outbox 状态。
- duplicate delivery、重平衡、partition interruption、producer confirm timeout、consumer crash、DLQ/replay、pause/resume/cancel。
- 同一 idempotency key 的工具/Provider 事件只产生一个可确认 side effect；不确定 publish 进入 reconciliation。
- 跨租户 topic/key、未授权 consumer、schema/version 漂移和毒消息必须隔离或拒绝。

通过门槛：顺序和幂等在 holdout 故障脚本下稳定；无 exactly-once 口头声明，只有有 raw evidence 的已验证行为。

### T05：Secrets Broker

- short-lived lease：申请、scope 校验、注入、过期、主动撤销和轮换。
- negative：空/伪造 authority、越权 scope、错误 tenant、broker 超时、secret version 不存在、日志/异常/制品/缓存扫描。
- sandbox：ANALYZE 阶段零 secret，EXECUTE 只获得最小 scope；清理后 lease 和临时文件不可读。
- incident：worker crash、network split、撤销失败、重复 revoke 和未知 broker response。

通过门槛：任何 secret value 不出现在持久化、artifact、event、metrics、trace 和 error；broker 不可用默认拒绝；revoke 证据可由独立 verifier 查询。

### T06：Provider/adapter conformance

7 个 adapter × 12 个既定 case = 84 个最小测试单元，每个 adapter/version 单独出报告：

1. success with output；
2. explicit empty output；
3. interrupted；
4. timeout；
5. denied；
6. partial subagent max turns；
7. pause/resume；
8. cancel at safe point；
9. provider stream reconnect；
10. environment authority isolation；
11. stale fencing token denied；
12. telemetry/cost attribution。

另外加入 schema mapping、Unicode/大 payload、工具版本漂移、模型不可用、限流、重复请求、side-effect compensation 和 provider identity 不能成为 authority 的负例。

通过门槛：12/12 全部有真实 raw evidence 才能将 adapter 报告从 `BLOCKED` 提升；只传 `responses`、只测本地 handler 或只通过静态 conformance 不能产生外部/独立通过，也不能升级 E2 或 P05。

### T07：Kubernetes 集群

- manifest/schema、image digest/signature/SBOM、non-root/read-only/capabilities/seccomp、ServiceAccount、NetworkPolicy 和 PVC 检查。
- real rollout：双副本启动、迁移锁、readiness/liveness/version/metrics、滚动升级和旧/新版本混合运行。
- fault injection：pod crash、node drain、network deny、DB outage、S3/Event Bus/Secrets outage、consumer rebalance、disk full、lease takeover。
- recovery：从 backup 恢复、replay event/checkpoint、cancel/resume、rollback image、删除 orphan resources。
- security：未授权 ingress/egress、metadata service、shell/exec、容器逃逸基线和 secret exposure。

通过门槛：真实集群 raw event/log/metric/command 完整；dry-run、Helm template、Compose config 只算工程证据；rollback 和 restore 均需独立复核。

### T08：客户仓库和 Golden Route 接受测试

每条 Golden Route 至少使用一组 holdout 和一组已授权 representative repo，要求：

- baseline build/test/contract/security 先于任何改写；
- 源快照、目标 commit、Semantic IR、ChangeGraph、validation DAG、artifact/evidence graph 全部 digest-bound；
- 失败、部分完成、人工批准、pause/resume、回滚和客户验收单独记录；
- 语义未知、跳过测试、无数据库/事务/安全证据不得被聚合成成功；
- 客户确认必须由客户身份产生，不能由执行者或模型自签。

通过门槛：代表性仓库重复运行达到预设样本数，holdout 不调参；客户验收、成本/ETA/SLO 和回滚结果全部有独立证据。

## 4. E1-E5 认证执行顺序

| 级别 | 依赖 | 测试包 | 失败处理 |
|---|---|---|---|
| E1 | T00 | package/unit/negative/anti-fabrication | 修复后完整重跑，不覆盖旧结果 |
| E2 | E1 + T01/T03/T04/T05/T06 | 真实基础设施与适配器 conformance | 任一 `NOT_RUN/UNKNOWN` 保持 E2 `NOT_RUN` |
| E3 | E2 + T02/T08 | Golden Route、语义/契约等价、完整 DAG | 只要有未知语义或 holdout 缺失即 `BLOCKED` |
| E4 | E3 + T05/T07 + red-team | chaos/recovery/tenant/security/rollback | 任何 P0/P1 或重复副作用拒绝升级 |
| E5 | E4 + representative acceptance | 大仓库、重复性、cost/ETA/SLO、客户结果 | 缺客户签字或独立复核保持 `NOT_CERTIFIED`；E5 通过后才进入 P05 |

## 5. 退出与报告格式

最终报告按能力和 E 级别分别给出：`status`、evidence IDs/digests、未执行项、阻塞原因、风险 owner、重放命令、过期时间和下一步。不得只给一个总 PASS 数字。

只有在所有强制 E1-E5 证据真实、独立、可重放，且 [P05 gate](../src/elmos_repository_autonomy/certification.py) 按持久化 case、候选 digest、证据 hash、审批角色、T07 部署证据和客户验收记录完成交叉绑定时，才允许产生 `P05_DEPLOYMENT_COMPLETE`；Provider 或其他 evidence ID 重新贴标签必须失败，本测试计划本身永远不会改变认证状态。
