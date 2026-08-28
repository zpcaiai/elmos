# OpenHands Absorption P0/P1 补全计划

## 1. 计划目的与状态边界

本计划针对 elmos-openhands-absorption-p0-p1-v1.0.0 的 14 个能力（P0-01
至 P0-09、P1-01 至 P1-05）。ZIP 内文档是需求和验收材料，不是可执行授权；
计划不会执行其中的脚本、工作流、SQL 或安装器。

仓库内的代码实现已经完成，当前交付的是可审计的本地工程实现和可替换的
生产适配器边界。以下事实必须保持不变：

> 代码实现已完成，但真实 Temporal/PostgreSQL、生产 sandbox、外部 Provider、
> 浏览器设备、Golden Repo、负载/Chaos、独立安全审查尚未执行，因此当前仍
> 保持 NOT_RUN / NOT_CERTIFIED，不能冒充生产认证或 GA。

PARTIAL、BLOCKED、EVIDENCE_PENDING、NOT_RUN 和 NOT_CERTIFIED 都是有效状态，
不得通过文案、静态文件、模型输出或自签名结果改写为成功。

## 2. 当前已完成基线

| 范围 | 已有实现/证据 | 当前状态 |
|---|---|---|
| P0/P1 运行时 | 38 个 Python 组件、两阶段 PostgreSQL migration/down、Schema、机器可校验 14-Skill manifest 和 11 个测试文件 | IMPLEMENTED |
| 本地验证 | 57 个单元/合同/安全/恢复/生命周期测试通过且 ResourceWarning 视为错误；Ruff、strict mypy、静态 importer/manifest 和 CLI status 通过 | LOCAL_ENGINEERING_EVIDENCE |
| 数据库 | PostgreSQL/RLS/advisory-lock/outbox/checkpoint/projection adapter 与 migration 代码已完成；实际 PostgreSQL 连接、故障切换和恢复演练尚未执行 | NOT_RUN |
| 工作流 | Temporal workflow/update/child/retry/heartbeat/cancel/compensation/continue-as-new 代码已完成；真实 worker/history/replay 尚未执行 | NOT_RUN |
| 隔离 | Local/Docker/Kubernetes/Firecracker/attested SSH backend 和 Secret Broker 代码已完成；生产 gVisor/Kata/microVM/SSH 隔离尚未执行 | NOT_RUN |
| Provider | Codex、Claude、OpenHands、OpenCode、Gemini、Junie HTTP/stream/session adapter 代码已完成；真实外部 Provider 尚未执行 | NOT_RUN |
| UI | Playwright/设备矩阵、semantic locator、二进制证据、脱敏、allowlist、flake gate 代码已完成；真实浏览器/设备矩阵尚未执行 | NOT_RUN |
| 规模与安全 | 测试计划和故障模型待执行；Golden Repo、load/Chaos、独立安全审查尚未执行 | NOT_RUN |
| 生产认证/GA | 没有独立验证、客户结果和命名环境证据 | NOT_CERTIFIED |

`implementation_manifest.json` 和 CLI `status` 将七类外部门禁固定为 `NOT_RUN`，
并将认证/发布固定为 `NOT_CERTIFIED` / `NOT_GA`。本地控制面合同校验只证明代码、
拒绝和降级路径，不构成真实生产执行证据。

## 3. 补全阶段与出口条件

### C0 — 范围冻结和证据注册

目标：冻结版本、租户/项目/运行绑定、策略版本、artifact digest、Provider
能力、workspace isolation、测试 corpus 和状态机。

必须产出：

- 执行 manifest、schema 版本、源码提交 SHA、依赖锁和包 digest；
- P0/P1 → 模块 → 测试 → 证据的 traceability graph；
- 正向开发 corpus、负向安全 corpus、holdout corpus、代表性 corpus 的独立
  清单；
- 每个外部 gate 的授权人、执行人、独立 verifier、重放命令和清理策略。

出口：契约校验通过；没有任何外部执行或认证状态被伪造。失败时保持
BLOCKED，不进入 C1。

### C1 — 真实持久化与 Temporal 工作流

目标：把本地参考实现接入真实 PostgreSQL、对象存储、事件总线和 Temporal，
并证明 acknowledged event 的 RPO=0、checkpoint/resume 和 side-effect
reconciliation。

实施项：

1. PostgreSQL adapter：事务事件序列、append-only 触发器、RLS、outbox、租约
   fencing、checkpoint 和 projection rebuild。
2. Object-store adapter：tenant-scoped CAS、digest 校验、retention、snapshot
   restore 和临时不可用处理。
3. Event publisher：outbox claim、重复投递、顺序、重试和 dead-letter 证据。
4. Temporal adapter：child workflow、retry policy、heartbeat、cancel、resume、
   compensation、worker replacement 和 history replay。
5. 运行恢复：在 model call、tool proposal、side effect、observation、snapshot
   和 verification 各边界杀死 worker，并证明不重复执行不可逆副作用。

出口证据：真实环境运行 manifest、数据库/对象存储/Temporal 原始日志、故障
注入记录、恢复前后 digest、独立 verifier 报告。没有这些证据时为
NOT_RUN，不能写成 PRODUCTION_READY。

### C2 — 生产 sandbox、Secret Broker 与 workspace

目标：完成 L1/L2/L3/L4 的真实隔离运行，而非只生成 hardened command。

实施项：

- immutable image digest、rootless、read-only source、default-deny network、
  cap drop、no-new-privileges、PID/memory/disk/CPU quota；
- tenant/project/workspace mount boundary、snapshot/restore、lease heartbeat、
  expiry/recycle/warm-pool/cold-start；
- short-lived credential lease、opaque secret handle、revocation 和 output
  redaction；
- symlink、mount、namespace、DNS、egress、procfs、device、container escape 和
  tenant bleed 测试；
- 生产 sandbox provider 的 kill/restart、孤儿清理和回滚演练。

出口：隔离 verifier 确认每个 profile 的真实运行结果和 escape negative cases；
没有生产 sandbox 实证前，L2+ 仍为 NOT_RUN。

### C3 — 外部 Provider 与路由

目标：在不把 Provider 变成权限主体的前提下，完成至少两个真实外部适配器的
同一合同测试。

实施项：

- Provider session/message/tool request/usage/checkpoint/error/cancel normalization；
- privacy、region、model、cost ceiling、latency、checkpoint 和 fallback 路由；
- 429/5xx/timeout/partial response/circuit-breaker/shadow evaluation；
- Provider 只能提出 Action/CompletionProposal，所有副作用继续经过 Firewall、
  Tool Gateway 和 Evidence Gate；
- 外部凭据不进入事件 payload、context、artifact 或 workspace 镜像。

出口：真实 Provider 原始响应、脱敏后的 normalized event、usage/cost 对账、
fallback/retry 记录和独立合同测试报告。未执行前保持 NOT_RUN。

### C4 — 浏览器/设备证据

目标：完成真实浏览器和需要的设备矩阵，并生成可重放 Evidence Pack。

实施项：

- Chromium/WebKit/Firefox（如产品要求）及移动 viewport/device profile；
- semantic locator、DOM/accessibility tree、screenshot/video、console/network、
  performance timing 和 backend trace correlation；
- 密码、token、authorization、PII、network body 的策略化遮罩；
- 原构建 exact replay 和新构建 semantic replay；
- flake 分类/重试不能吞掉真实失败，console error/failed request 按 gate 策略处理。

出口：每个场景的原始 artifact、masking manifest、trace correlation、replay
结果和独立验收报告。没有真实设备运行时保持 NOT_RUN。

### C5 — Golden Repo、负载与 Chaos

目标：使用独立且不参与开发调参的仓库和任务，证明正确性、容量和恢复能力。

实施项：

- 至少 3 个大仓库（其中至少 1 个超过 1M LOC，若授权可得）；
- 固定 golden tasks、acceptance criteria、工具安全基线、成本和延迟基线；
- 负载：预期生产并发、2x burst、idle/active mix、backpressure、tenant quota；
- Chaos：worker death、DB failover、object-store outage、event duplication、
  provider outage、workspace loss、network partition、clock/lease expiry；
- 结果由独立 verifier 运行，不得由被测 Runtime 自己生成完整成功证明。

出口：原始 workload log、环境 digest、吞吐/延迟 p50/p95/p99、错误/恢复率、
成本和容量结论。未执行时保持 NOT_RUN。

### C6 — 独立安全与合规审查

目标：由不负责实现和 gate 结论的安全团队进行红队和架构审查。

覆盖：prompt injection、README/dependency/test/web/tool-output taint、curl/DNS/
git exfiltration、shell obfuscation、path/symlink escape、package hooks、least
privilege、credential TTL、tenant isolation、audit completeness、retention/export/
deletion 和 incident response。

出口：带 scope、commit/image/package digest、原始 findings、严重性、修复复测、
接受的 residual risk 和签字的独立报告。没有独立报告时 NOT_RUN，不能用本地
安全单测替代。

### C7 — 生产候选、Canary 与 GA 决策

只有 C1-C6 的命名 evidence pack 全部通过，且没有 Critical/High 未关闭风险，
才能创建生产候选版本。流程为：

1. 生成不可变 release manifest 和 SBOM/provenance；
2. 通过变更审批、回滚演练和小范围 canary；
3. 观察 SLO、成本、错误、policy denial、recovery 和 tenant bleed 指标；
4. 由独立 verifier 复核结果；
5. 由有权限的产品/安全/平台负责人作 GA 决策。

任何一个外部证据缺失、过期、冲突、UNKNOWN 或 INCONCLUSIVE，都停止在
EVIDENCE_PENDING/NOT_CERTIFIED，不发布 GA 声明。

## 4. 交付物清单

| 交付物 | 责任边界 | 完成判据 |
|---|---|---|
| Code baseline | Runtime owner | 本地代码、schema、migration、tests、README 可重放 |
| Runtime manifest | Platform owner | tenant/project/run/node/provider/model/policy/image/package 全绑定 |
| Real persistence pack | Data/infra owner | PostgreSQL、object store、outbox、RLS、failover 原始证据 |
| Workflow pack | Workflow owner | Temporal history、retry/cancel/resume/compensation 证据 |
| Sandbox pack | Security/infra owner | isolation profiles、escape negative、credential revoke、recycle 证据 |
| Provider pack | Provider owner | 至少两个真实 adapter 的 contract/fallback/cost/privacy 证据 |
| Browser pack | QA/UI owner | browser/device matrix、evidence、mask、replay 证据 |
| Benchmark pack | QA/performance owner | golden/holdout/representative 分离、性能和恢复报告 |
| Security pack | Independent security owner | 独立红队报告、修复复测、residual-risk 签字 |
| Release pack | Release authority | SBOM、provenance、rollback、canary、独立验证和决策记录 |

## 5. 停止、回滚和重新进入条件

- 任意租约 fencing 失败、tenant scope mismatch、digest mismatch、未知状态或
  证据冲突：立即停止该 run，记录 ledger event，状态置为 BLOCKED；
- 不可逆副作用出现 timeout/unknown：禁止盲目 retry，先走 reconciliation；
- Provider、workspace、数据库或事件总线 outage：保留 checkpoint/snapshot，切换
  到已批准 fallback，不能扩大权限；
- package revoke、sandbox escape 或 credential leak：立即 kill switch、撤销
  credential、隔离 workspace、保留取证 artifact；
- rollback 必须绑定旧版本 manifest/image/package digest，并再次运行受影响 gate；
- 任何代码、策略、Provider、image、package 或 Schema 变更都重新评估兼容性，
  active run 不得静默升级。

## 6. 目前明确结论

代码实现阶段已经完成；补全计划的后续阶段是外部环境执行和独立证据收集，
不是继续用静态代码或模型文字制造完成度。真实 Temporal/PostgreSQL、生产
sandbox、外部 Provider、浏览器设备、Golden Repo、负载/Chaos、独立安全审查
完成前，系统状态必须继续显示 NOT_RUN / NOT_CERTIFIED，不能宣称生产认证或 GA。

## 2026-08-28 执行补全记录

代码级执行器已补齐：`run_qualification_probe.py` 现在提供 postgres、provider、
security、browser、sandbox、golden、load、chaos 八类显式探针；Temporal 有真实
worker replacement/history replay 探针；安全评审有独立签名报告 intake；依赖告警
有 digest-bound exception validator 和受控 GitHub remediation tool。

本次只完成 disposable/local engineering evidence：PostgreSQL、Temporal、L1
sandbox、browser matrix、Golden Repo、bounded load 和 15/15 local Chaos 的结论
写入 `evidence/QUALIFICATION_EXECUTION_2026-08-28.md`。Provider 真实调用因配额/
endpoint 失败而保持 `FAIL`。生产等价拓扑、生产 sandbox、physical device、
representative soak、多区域 DR、独立 holdout、独立 security review 和客户验收
仍为 `NOT_RUN`；总状态仍为 `NOT_CERTIFIED` / `NOT_GA`。
