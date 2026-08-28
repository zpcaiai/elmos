# OpenHands Absorption P0/P1 测试计划

## 1. 目的和不可突破的状态边界

本计划验证 elmos-openhands-absorption-p0-p1-v1.0.0 的 14 个能力：P0-01
至 P0-09、P1-01 至 P1-05。代码实现已经完成，本计划负责补齐可重复、可审计、
分环境的测试证据，不把测试计划、静态校验或模型叙述当成生产认证。

必须保留以下声明：

> 代码实现已完成，但真实 Temporal/PostgreSQL、生产 sandbox、外部 Provider、
> 浏览器设备、Golden Repo、负载/Chaos、独立安全审查尚未执行，因此当前仍
> 保持 NOT_RUN / NOT_CERTIFIED，不能冒充生产认证或 GA。

测试结果状态使用：

| 状态 | 含义 | 是否可以支持认证 |
|---|---|---|
| NOT_RUN | 没有在命名环境实际执行 | 否 |
| RUNNING | 执行中，不能读取为成功 | 否 |
| PASS | 在指定环境中通过了指定 oracle | 仅作为该 gate 的局部证据 |
| FAIL | oracle 失败 | 否，触发修复/回滚 |
| BLOCKED | 前置条件、权限或资源缺失 | 否 |
| EVIDENCE_PENDING | 有执行痕迹但证据角色/完整性不足 | 否 |
| NOT_CERTIFIED | 没有满足独立验证、外部证据和认证门禁 | 否 |

UNKNOWN、INCONCLUSIVE、过期、冲突、无 digest、无 replay 或自验证的结果均
不得降级成 PASS。

## 2. 测试治理原则

### 2.1 证据角色分离

每个可认证测试必须绑定以下字段：

- test case ID、版本、需求/Skill ID、artifact 和执行 manifest digest；
- tenant、project、task、run、node、agent、trace、policy、provider、model、image、
  package、Schema 和数据集版本；
- 授权人、实际执行人、独立 verifier、执行时间和环境标识；
- 原始日志/截图/视频/数据库快照/Temporal history/网络记录；
- replay command、输入 digest、输出 digest、oracle 定义和清理结果；
- retry、timeout、partial、UNKNOWN 和 rollback 记录。

被测 Runtime、Provider、代码作者不能同时制造成功证据并担任唯一 verifier。
静态 validator 只能证明结构或工程质量，不能证明真实环境行为。

### 2.2 Corpus 隔离

四类 corpus 在 C0 阶段生成 manifest 并锁定 digest：

1. development：用于开发和本地回归，不用于最终成功率；
2. negative/security：用于拒绝、逃逸、越权、泄漏、破坏性动作；
3. holdout：开发者和调参过程不可见，用于独立验证；
4. representative/golden：代表真实租户、仓库规模、Provider、浏览器和运行负载。

不得把同一个任务、仓库快照、截图或故障样本同时作为开发和 holdout 证据。
修改测试、baseline、tolerance、allowlist 或失败 oracle 必须重新审批并重新跑
受影响 corpus。

## 3. 测试环境矩阵

| 环境 | 用途 | 允许副作用 | 当前状态 |
|---|---|---|---|
| L0 local SQLite/CAS | 单元、契约、确定性安全测试 | 仅临时本地目录 | 已执行局部测试 |
| disposable integration | PostgreSQL、对象存储、事件总线、Temporal、sandbox 集成 | 隔离租户和临时数据 | NOT_RUN |
| provider conformance | Codex/Claude/OpenHands-compatible 外部 adapter | 仅受控测试 workspace | NOT_RUN |
| browser/device lab | 浏览器、移动设备、viewport、trace correlation | 测试账号和临时数据 | NOT_RUN |
| load/chaos lab | 生产拓扑等价的压测、故障注入和恢复 | 不接入生产数据 | NOT_RUN |
| independent security lab | 红队、逃逸、exfiltration、供应链和租户隔离 | 只允许批准的测试范围 | NOT_RUN |
| canary/production | 仅在所有前置 gate 通过后 | 需正式变更审批 | NOT_RUN |

真实环境必须在测试开始前记录版本、镜像、依赖、网络、凭据租约、时钟、区域、
数据保留和清理策略。未命名环境的运行输出不能作为生产证据。

## 4. 已有本地工程测试基线

以下结果来自仓库实现的本地确定性测试，不代表外部环境认证：

| ID | 覆盖 | 判定 |
|---|---|---|
| LOC-001 | ZIP digest/member/schema 和 engine entrypoint | PASS |
| LOC-002 | Event ledger 单调 seq、hash chain、outbox、projection rebuild、idempotency | PASS |
| LOC-003 | run lease fencing、checkpoint、resume、budget 和 provider failure | PASS |
| LOC-004 | Action/Observation schema、Tool Registry/Gateway、timeout、output cap、redaction | PASS |
| LOC-005 | Firewall capability、path、network、secret、prompt injection、destructive guard | PASS |
| LOC-006 | Completion Gate、evidence verifier、hooks ordering、traceability | PASS |
| LOC-007 | CAS tenant scope、workspace snapshot/restore、lease restart、容器参数边界 | PASS |
| LOC-008 | Skill disclosure、signed package lifecycle、approval/revoke/deprecate | PASS |
| LOC-009 | DAG fan-out/fan-in、fencing、amendment cycle、node removal | PASS |
| LOC-010 | Native/provider normalization、routing、cost ceiling、fallback | PASS |
| LOC-011 | Browser capture、cleanup、locator evidence、secret masking | PASS |
| LOC-012 | Worker plane、admission quota、metrics、cost reconciliation、service cursor | PASS |
| LOC-013 | PostgreSQL adapter 的事务/RLS/advisory lock/outbox/checkpoint 合同（fake connection） | PASS（合同）；真实 DB NOT_RUN |
| LOC-014 | S3 CAS、broker ack/outbox、tenant/digest/encryption contract | PASS（fake client）；真实服务 NOT_RUN |
| LOC-015 | Sandbox backend fencing、Secret revoke、隔离等级和 snapshot attestation | PASS（fake backend）；生产隔离 NOT_RUN |
| LOC-016 | Provider durable session、exact idempotency、终态 replay、usage reconciliation | PASS（fake transport）；外部 Provider NOT_RUN |
| LOC-017 | Browser binary safety、PII/secret redaction、mask attestation、allowlist expiry、flake block | PASS（fake driver）；真实设备 NOT_RUN |
| LOC-018 | Evidence producer/verifier 分离、trust/revoke、qualification fail-closed | PASS（本地签名合同）；独立 verifier NOT_RUN |
| LOC-019 | Authenticated REST/WS/gRPC 共享 gateway core 的 trusted scope/RBAC/cursor 合同与 protobuf Schema 静态绑定 | PASS（直接合同/静态）；真实 FastAPI/gRPC server 部署与 E2E NOT_RUN |
| LOC-020 | Retention/export/legal-hold/idempotent deletion/UNKNOWN reconciliation | PASS（本地 provider）；真实删除证明 NOT_RUN |

当前本地执行证据为 57 个测试通过（并以 `ResourceWarning` 为错误）、Ruff、
strict mypy、静态 importer/manifest 和 CLI status 通过。完整 make gate 在每次
提交前重放。它们只能标记为 LOCAL_ENGINEERING_EVIDENCE，
不能覆盖下方的真实集成、独立验证、负载、Chaos 或认证要求。

## 5. 合同、集成和恢复测试

### 5.1 合同测试

| ID | 测试内容 | 关键 oracle | 需要的证据 | 当前状态 |
|---|---|---|---|---|
| CT-001 | Action/Observation envelope | oneOf、required fields、Schema version、拒绝未知/非法字段 | normalized input/output、schema validator log | PASS（本地） |
| CT-002 | Execution Event | tenant/run/seq、digest、previous_digest、timestamp、payload | raw event stream、recomputed digest | PASS（本地） |
| CT-003 | Provider adapter | 相同输入在 Native 和至少两个外部 adapter 上形成相同 normalized contract | raw provider response、normalized event、usage | NOT_RUN（外部） |
| CT-004 | Workspace API | lease、snapshot、restore、image digest、isolation profile | workspace manifest、snapshot digest、restore log | PASS（L0）；NOT_RUN（生产 profile） |
| CT-005 | Capability package | publisher、signature、SBOM/lock、permission、version、rollback | signed manifest、signature verify、package digest | PASS（本地 deterministic bundle/HMAC contract）；NOT_RUN（生产 KMS/Ed25519 registry） |
| CT-006 | Browser evidence | scenario、semantic locator、artifact refs、masking、replay metadata | screenshot/DOM/trace/network manifest | PASS（fake driver）；NOT_RUN（真实设备） |

### 5.2 真实集成测试

| ID | 测试内容 | 通过条件 | 当前状态 |
|---|---|---|---|
| INT-001 | PostgreSQL transaction/RLS | append、lease、checkpoint、projection 在并发和 tenant RLS 下正确；非法租户不可读写 | NOT_RUN |
| INT-002 | PostgreSQL append-only | update/delete 被拒绝；correction 只能追加事件；重放结果与原 projection digest 一致 | NOT_RUN |
| INT-003 | Object-store CAS | 内容 digest、tenant prefix、大小/媒体类型、临时 outage、重试和 retention 正确 | NOT_RUN |
| INT-004 | Outbox/event bus | transaction 与 outbox 原子；重复发布幂等；顺序和 dead-letter 可审计 | NOT_RUN |
| INT-005 | Temporal lifecycle | child workflow、heartbeat、retry、cancel、resume、compensation、worker replacement 正确 | NOT_RUN |
| INT-006 | Runtime recovery | 每个 side-effect 边界 kill/restart 后不重复不可逆动作，能恢复到安全 checkpoint | NOT_RUN |
| INT-007 | Production sandbox | rootless、read-only、network deny、quota、mount、PID、image digest 和孤儿清理通过 | NOT_RUN |
| INT-008 | Secret Broker | opaque handle、TTL、revocation、tenant binding、output redaction 和审计通过 | NOT_RUN |
| INT-009 | Provider external | 429/5xx/timeout/partial/cost/region/checkpoint/fallback 行为符合策略 | NOT_RUN |
| INT-010 | Browser/device | 真实浏览器/设备完成场景，证据可重放，console/network 失败不被隐藏 | NOT_RUN |

## 6. 安全负向测试

所有安全测试必须使用隔离租户和一次性凭据；发现逃逸、泄漏或越权时立即
停止测试、撤销 credential、保留 forensic artifact，并将结果标记为 FAIL，
不能通过重跑覆盖。

| ID | 攻击面 | 关键用例 | 当前状态 |
|---|---|---|---|
| SEC-001 | Prompt injection | README、dependency script、fixture、网页、tool output 中的 ignore/bypass/reveal 指令 | PASS（本地规则）；NOT_RUN（独立红队） |
| SEC-002 | Data exfiltration | curl/DNS/git push、token/password/credential 读取、压缩后外传、命令混淆 | PASS（本地部分）；NOT_RUN（sandbox 红队） |
| SEC-003 | Filesystem escape | ../、绝对路径、symlink、hardlink、mount、workspace 外读写 | PASS（本地部分）；NOT_RUN（生产 sandbox） |
| SEC-004 | Network escape | 未 allowlist 域名、IP literal、重定向、DNS rebinding、非 HTTP 通道 | PASS（本地部分）；NOT_RUN（真实网络隔离） |
| SEC-005 | Destructive action | rm/reset/drop/truncate/force push、未授权高风险动作、approval timeout | PASS（本地部分）；NOT_RUN（独立验证） |
| SEC-006 | Tenant bleed | 跨租户 run、event、CAS、workspace、package、cache、stream、metrics 查询 | PASS（本地部分）；NOT_RUN（PostgreSQL/分布式） |
| SEC-007 | Supply chain | 恶意 package hook、错误签名、digest collision、revoked package、依赖漂移 | PASS（本地部分）；NOT_RUN（独立供应链审查） |
| SEC-008 | Secret/privacy | 日志、event、context、artifact、screenshot、network body 中的 secret/PII | PASS（本地部分）；NOT_RUN（真实数据策略） |
| SEC-009 | Authorization | policy/capability/package/approval 混淆，provider 伪造成功或绕过 gate | PASS（本地部分）；NOT_RUN（独立审查） |
| SEC-010 | Availability abuse | oversized payload、event flood、lease churn、quota exhaustion、dead-letter flood | NOT_RUN |

本地规则测试不能替代独立安全审查。SEC-001 至 SEC-010 全部拥有独立报告前，
安全 gate 必须保持 NOT_RUN，认证保持 NOT_CERTIFIED。

## 7. 故障注入与灾难恢复

| ID | 注入点 | 必须观察的结果 | 当前状态 |
|---|---|---|---|
| CHAOS-001 | provider request 前后、tool proposal、side effect 前后、observation 前后 | 事件链连续；重试不重复副作用；状态为可恢复或 BLOCKED | NOT_RUN |
| CHAOS-002 | Temporal worker death/heartbeat loss | fencing 生效；新 worker 从安全 history/checkpoint 接管 | NOT_RUN |
| CHAOS-003 | PostgreSQL failover/connection loss | acknowledged writes RPO=0；未确认写入为 UNKNOWN，不盲目 retry | NOT_RUN |
| CHAOS-004 | object-store outage/corrupt snapshot | digest mismatch 被拒绝；回退到前一安全 checkpoint | NOT_RUN |
| CHAOS-005 | event duplication/out-of-order delivery | consumer 幂等；projection rebuild 与 shadow checksum 一致 | NOT_RUN |
| CHAOS-006 | workspace disappearance/lease expiry | 旧 lease 被 fence；snapshot restore 或安全 BLOCKED | NOT_RUN |
| CHAOS-007 | provider outage/429/5xx | circuit breaker、policy-allowed fallback、manifest amendment 可审计 | NOT_RUN |
| CHAOS-008 | network partition/clock skew | lease、timeout、cancel 和 reconciliation 不产生 split-brain | NOT_RUN |
| CHAOS-009 | cancellation during side effect | 记录 cancellation intent；side effect 最终状态可 reconcile | NOT_RUN |
| CHAOS-010 | full restore exercise | 数据库、CAS、ledger、projection、package pin 和 run state 可恢复 | NOT_RUN |

## 8. 性能、容量和成本测试

### 8.1 负载模型

C0 阶段必须根据目标部署冻结以下参数：租户数、idle/active run 比例、平均和
最大 context、tool call rate、event size、artifact size、Provider latency、
并发上限、2x burst、保持时间、区域和 quota。参数未冻结时结果只能为
NOT_RUN。

### 8.2 测试项

| ID | 范围 | 指标和 oracle | 当前状态 |
|---|---|---|---|
| PERF-001 | 预期生产并发 | throughput、queue、lease wait、p50/p95/p99 latency、error rate | NOT_RUN |
| PERF-002 | 2x burst | backpressure 生效；不丢 acknowledged event；不跨 tenant | NOT_RUN |
| PERF-003 | 长任务 | checkpoint cadence、resume p95、event/artifact growth、内存稳定性 | NOT_RUN |
| PERF-004 | 多租户公平性 | quota、noisy-neighbor、region/data residency 和调度公平 | NOT_RUN |
| PERF-005 | Provider mix | 成本、token、cache、latency、fallback 和 circuit 状态 | NOT_RUN |
| PERF-006 | Artifact/event volume | CAS、outbox、retention、压缩和存储成本可对账 | NOT_RUN |
| PERF-007 | Cost reconciliation | provider/infrastructure invoice sample 与 ledger cost 差异在批准阈值内 | NOT_RUN |

性能阈值、样本量、warm-up、测量窗口和统计方法必须在执行前冻结，不能根据
结果倒推阈值。任何超预算或容量不足的结果都保持 FAIL/BLOCKED。

## 9. Golden Repo 与产品验收

| ID | 内容 | 通过条件 | 当前状态 |
|---|---|---|---|
| GOLD-001 | 小型基准仓库 | task completion、diff、tests、evidence 和 rollback 全部可重放 | NOT_RUN |
| GOLD-002 | 中型基准仓库 | 多文件/多工具/失败修复/成本和延迟满足冻结阈值 | NOT_RUN |
| GOLD-003 | 大型基准仓库 | 至少 3 个大型仓库，至少 1 个超过 1M LOC（需授权） | NOT_RUN |
| GOLD-004 | Polyglot/复杂依赖 | package、workspace、Provider、DAG 和 gates 保持契约 | NOT_RUN |
| GOLD-005 | Holdout verification | 未参与开发调参的 verifier 在独立 corpus 上复现结果 | NOT_RUN |
| GOLD-006 | Customer outcome | 有授权的真实验收标准、人工结果和 residual risk 决策 | NOT_RUN |

Golden Repo 成功率不得由被测 Agent 的自然语言报告单独计算；必须绑定真实
diff、build/test/browser/security artifact、要求追踪和独立 oracle。

## 10. 观察性、审计和报告测试

| ID | 测试内容 | 通过条件 | 当前状态 |
|---|---|---|---|
| OBS-001 | end-to-end trace | task → node → turn → context → model → policy → tool → observation → checkpoint → verification 可关联 | PASS（本地结构）；NOT_RUN（真实 OTel） |
| OBS-002 | metrics | success/failure/retry/cancel/block、queue/lease、token、CPU/memory/time、storage、cost 有定义、grain、denominator | NOT_RUN |
| OBS-003 | audit | actor、tenant、package、policy、approval、provider、manifest、correction 和 revoke 可查询 | NOT_RUN |
| OBS-004 | retention/export/deletion | tenant export、retention、删除和审计保留策略不越权、不破坏不可变事实 | NOT_RUN |
| OBS-005 | incident evidence | outage、escape、leak、rollback 报告可从原始证据重放 | NOT_RUN |

## 11. Gate 顺序和进入/退出条件

1. C0：scope、corpus、manifest、授权、oracle、环境和证据角色冻结；
2. Local gate：本地合同、安全负向、lint/typecheck、unit/integration engineering
   evidence 全部通过；
3. Integration gate：CT-001 至 CT-006、INT-001 至 INT-010 在命名环境执行；
4. Security gate：SEC-001 至 SEC-010 由独立安全团队复核；
5. Resilience gate：CHAOS-001 至 CHAOS-010 完成并通过恢复 oracle；
6. Performance gate：PERF-001 至 PERF-007 的原始指标、阈值和成本对账通过；
7. Product gate：GOLD-001 至 GOLD-006 的独立验收通过；
8. Release gate：SBOM、provenance、rollback、canary、变更审批和独立验证齐全；
9. Certification/GA：只有授权决策人依据完整 evidence pack 作出决定。

任意 P0、租户隔离、Secret、sandbox escape、ledger integrity、不可逆副作用、
独立安全、恢复、关键 Golden Repo 或证据完整性失败，均阻断后续 gate。

## 12. 证据包格式

每个 test case 生成不可变 evidence record，至少包括：

- case_id、source_skill、requirement_refs、test_version、corpus_digest；
- code_commit、manifest_digest、environment_digest、image/package/schema digest；
- tenant/project/task/run/node/trace、authorization、executor、verifier；
- input_digest、raw_evidence_refs、output_digest、oracle_result；
- started_at、ended_at、retry_count、cleanup_result、replay_command；
- status、failure_class、residual_risk、supersedes/superseded_by。

证据生产者只能追加记录，不能覆盖历史失败。verifier 必须独立读取原始证据并
重新计算关键 digest；缺少任一必需角色时结果为 EVIDENCE_PENDING。

## 13. 当前测试结论

当前只有本地工程测试证据：实现和 57 个本地测试已完成，静态校验和 CLI 验证已
通过。真实 Temporal/PostgreSQL、生产 sandbox、外部 Provider、浏览器设备、
Golden Repo、负载/Chaos、独立安全审查尚未执行，故所有对应 case 继续保持
NOT_RUN；总体验证状态继续保持 NOT_CERTIFIED。任何计划文本、静态检查、fake
driver、deterministic adapter 或模型输出都不能改变该结论，也不能支持生产认证
或 GA。
