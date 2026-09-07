# OpenHands Absorption 生产接入、故障与回滚 Runbook

## 适用范围

本 Runbook 描述代码完成后的真实环境接入和证据收集流程。它不是执行授权；所有
命令中的环境、租户、凭据、数据库、集群和 Provider 必须由部署负责人显式提供。
在没有变更单、隔离测试环境和回滚责任人时停止执行。

当前状态：本地 disposable 工程探针已有局部 `PASS`/`FAIL` 结果；生产等价环境、
外部成功和独立审查仍为 `NOT_RUN`，认证为 `NOT_CERTIFIED`，发布为 `NOT_GA`。

## 进入条件

执行负责人必须先冻结并签署：

- commit、wheel/container、SBOM、provenance 和配置 digest；
- tenant/project/run、region、data residency、retention 和 deletion policy；
- PostgreSQL、Temporal、对象存储、event bus、sandbox、Provider、browser lab 的
  命名环境和一次性授权；
- executor、independent verifier、evidence store、replay command 和 cleanup owner；
- SLO、容量、成本、安全 oracle，以及停止/回滚阈值。

缺少任一项时，campaign 保持 `NOT_RUN` 或 `BLOCKED`。

## 本地预检

从仓库根目录执行：

```bash
make openhands-absorption
PYTHONPATH=engines/openhands-absorption-engine/src python -m elmos_openhands status
git diff --check
```

预期结果只能写为 `LOCAL_ENGINEERING_EVIDENCE`。`status` 必须继续显示七类外部
门禁为 `NOT_RUN`、认证为 `NOT_CERTIFIED`、发布为 `NOT_GA`。

## PostgreSQL 与 Temporal 接入

1. 在一次性数据库备份并记录 server/extension/config digest。
2. 使用事务型 migration runner 依次应用 `0001`、`0002`；禁止把 ZIP 内 SQL
   作为 migration 输入。
3. 创建最小权限 app、outbox publisher、projection 和 migration 身份；为每个
   请求设置本地事务变量 `app.tenant_id`，并验证 RLS/`FORCE ROW LEVEL SECURITY`。
4. 对 append-only trigger、advisory run lock、lease fencing、checkpoint、large
   payload CAS、outbox claim/retry/dead-letter 和 projection rebuild 执行合同测试。
5. 注册真实 Temporal worker/activity；确认 workflow update、heartbeat、retry、
   child workflow、continue-as-new、graceful cancel 和 compensation。
6. 分别在 append 前/后、Provider 前/后、side effect 前/后、checkpoint 前/后杀死
   worker；未知外部结果必须进入 reconciliation，禁止盲重试。
7. 保存数据库日志、Temporal history、worker 日志、artifact digest、恢复前后
   projection checksum 和独立 verifier 结论。

只有原始证据齐全且 verifier 独立时，该 campaign 才能进入
`READY_FOR_EXTERNAL_GATE`；代码不会产出 `CERTIFIED`。

## Sandbox 与 Secret Broker 接入

1. 仅使用 immutable image digest；禁止 mutable tag。
2. 验证 rootless、read-only source、writable output、cap-drop、no-new-privileges、
   seccomp、PID/CPU/memory/disk quota 和 default-deny egress。
3. L2 只允许已证明的 gVisor/Kata profile；L3 只允许真实 microVM；L4 需要独立
   attested dedicated host。未满足时必须降为实际隔离等级，不能提高标签。
4. Secret Broker 只返回短期 opaque lease；TTL 不得超过 workspace lease，且测试
   revoke、rotation、log/artifact/context/screenshot redaction。
5. 执行 path/symlink/hardlink/mount/procfs/device/DNS/redirect/rebinding/tenant bleed/
   orphan cleanup/restore negative suite。
6. escape、secret leak、tenant bleed 或 attestation mismatch 立即触发 kill switch，
   撤销凭据、隔离 workspace 并保留 forensic evidence。

## Provider 与 Browser 接入

Provider：

- 每个 adapter 使用独立最小权限 credential lease 和允许区域；
- 同一 digest-bound Golden Task 验证 start/send/stream/checkpoint/resume/cancel/
  usage/error；429、5xx、timeout、partial 和未知结果必须可审计；
- shadow 模式禁止 Action；Provider 输出只能提出 Action/CompletionProposal；
- usage/cost 与 Provider 报表逐行对账，凭据不得进入 payload/CAS/workspace。

Browser/device：

- 冻结 Chromium/Firefox/WebKit 和设备 profile/build digest；
- 运行 semantic locator、DOM、accessibility、screenshot、video、console、network、
  performance 和 backend trace correlation；
- 敏感 fill 必须存在 masking attestation；二进制证据保持原字节，文本按策略脱敏；
- console error/failed request 默认失败，allowlist 必须 exact、审批、理由和到期；
- flake 不能重试成 PASS，必须保持 `FLAKY_BLOCKED`。

## Golden、Load、Chaos 和独立安全

- Golden：至少三个超过 500k LOC 的仓库且一个超过 1M LOC，冻结 commit/task/
  oracle；holdout 不参与实现调参。
- Load：冻结生产并发、2x burst、soak、tenant mix、payload 和成本阈值，报告
  p50/p95/p99、backpressure、错误、恢复和费用。
- Chaos：覆盖 worker、PostgreSQL、Temporal、CAS、event bus、Provider、workspace、
  network partition、clock/lease 和 cancellation；acknowledged event RPO 目标由真实
  证据验证。
- Security：由未参与实现/自验的团队执行 prompt injection、exfiltration、escape、
  authz、supply chain、secret、tenant isolation、retention/deletion 和 DoS review。

任一 Critical/High 未关闭、UNKNOWN/INCONCLUSIVE、自验证、证据缺失或清理失败均
阻断 release。

## 回滚

### 应用回滚

1. 激活 global/tenant/package/tool kill switch，停止新 admission。
2. graceful cancel 活跃 workflow 并等待 compensation/reconciliation；未知副作用
   单独登记，不得因超时推定失败或成功。
3. 将 package pin、container image 和配置恢复到已知良好 digest。
4. 恢复后重建 projection、验证 ledger/event/CAS chain、对账 Provider 和 FinOps。

### 数据库回滚

- 优先使用 forward compensation，保留不可变事件和审计事实。
- 仅在一次性/明确批准的环境使用 down migration；先执行 `0002...down.sql`，再执行
  `0001...down.sql`。`0001` down 会在发现 `0002` 对象时失败关闭。
- 生产数据删除前必须完成授权 export、legal-hold 检查、独立 deletion verification。

## 事故分级与恢复

| 事件 | 立即动作 | 恢复 oracle |
|---|---|---|
| Ledger/RLS/digest mismatch | 停止写入、隔离租户、保留 WAL/history | 独立重算 chain/projection 全一致 |
| Sandbox escape/tenant bleed | 全局 kill、撤销 secret、保留镜像/trace | 修复后独立 negative suite 通过 |
| Provider UNKNOWN | 禁止盲 retry、查询/对账 Provider | 单一最终 receipt 与 ledger 一致 |
| CAS corruption/outage | 阻断 evidence success、回退安全 snapshot | digest/size/version 全验证 |
| Temporal split/replay error | drain worker、冻结 workflow version | history replay 和 compensation 一致 |
| Browser privacy leak | 撤销/隔离 artifact、通知安全与隐私负责人 | 清理证明和独立复测完成 |

## 退出条件

每个 campaign 都必须生成 content-addressed raw evidence、环境 digest、授权、执行人、
独立 verifier、replay、cleanup 和 findings。全部外部门禁通过后，系统最多报告
`READY_FOR_EXTERNAL_GATE`；生产认证和 GA 只能由授权的外部决策流程作出。

2026-08-28 的执行记录位于
[`evidence/QUALIFICATION_EXECUTION_2026-08-28.md`](evidence/QUALIFICATION_EXECUTION_2026-08-28.md)。
它明确区分本地自证与生产资格：本地 PostgreSQL/Temporal、L1 sandbox、浏览器
矩阵、Golden Repo、bounded load/Chaos 和 Bandit 可作为工程 evidence；Provider
真实调用当前失败；生产 sandbox、physical device、代表性 soak、多节点/多区域
恢复、独立 holdout 和独立 security review 不能从这些结果推导。

代码实现已完成，但真实 Temporal/PostgreSQL、生产 sandbox、外部 Provider、浏览器设备、Golden Repo、负载/Chaos、独立安全审查尚未执行，因此当前仍保持 `NOT_RUN / NOT_CERTIFIED`，不能冒充生产认证或 GA。
