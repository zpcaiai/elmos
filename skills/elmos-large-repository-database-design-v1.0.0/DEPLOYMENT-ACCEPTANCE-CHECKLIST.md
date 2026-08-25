# Elmos 部署验收清单

**原则：** 所有 Critical 项必须完成；任何 `unknown`、`not tested` 或仅有模板证据的项不得标为通过。

## A. Release 与供应链

- [ ] Release manifest 固定版本、Git SHA、镜像 digest、Chart 版本和配置 revision
- [ ] 所有镜像生成 SBOM
- [ ] 所有镜像通过漏洞、Secret、恶意软件和许可证扫描
- [ ] 镜像签名可在集群 admission 或部署前验证
- [ ] 依赖仓库、Builder 和 CI runner 来源可追溯
- [ ] 不使用 mutable tag 作为生产唯一定位

## B. 基础设施

- [ ] DNS、TLS、WAF/Gateway、Webhook endpoint 就绪
- [ ] PostgreSQL 高可用、TLS、加密、PITR 和容量告警
- [ ] Temporal namespace、task queue、Worker compatibility 与告警
- [ ] Redis 明确为非事实源，并验证清空后不丢业务状态
- [ ] 对象存储 bucket、KMS、版本控制、生命周期与 WORM 策略
- [ ] Graph/Index 支持备份、重建与租户隔离
- [ ] OTel Collector、指标、日志、Trace 后端正常
- [ ] OCI Registry 和内部语言包镜像仓库可用

## C. Kubernetes 安全

- [ ] Control Plane 使用 non-root、read-only rootfs、drop ALL、seccomp RuntimeDefault
- [ ] 默认 ServiceAccount token 不自动挂载
- [ ] 禁止 hostPath、Docker socket、hostPID、hostNetwork 和不必要 privileged
- [ ] 默认 deny NetworkPolicy 已应用且 CNI 阻断测试通过
- [ ] Worker egress 经过 allowlist/proxy
- [ ] metadata service、Kubernetes API、管理网段默认不可达
- [ ] 强隔离 Worker 使用指定 RuntimeClass，调度失败不回退
- [ ] 节点池、taint/toleration、nodeSelector、topology spread 正确
- [ ] ResourceQuota、LimitRange、PDB、HPA/KEDA 配置并实测

## D. 身份、Secret 与多租户

- [ ] OIDC/SSO 登录、MFA 和 session 失效验证
- [ ] Platform/Tenant/Project/Admin/Approver/Auditor 角色矩阵通过
- [ ] SCIM（适用时）验证
- [ ] tenant_id 在 API、DB、Object key、Queue、Log、Trace、Evidence 中完整传播
- [ ] PostgreSQL 应用层租户校验和 RLS/附加控制验证
- [ ] Secret 通过 Broker/Workload Identity 获取
- [ ] Worker/Agent 子进程没有长期 Provider、Git、Tracker 或云凭据
- [ ] Secret rotation、吊销和审计演练通过
- [ ] 日志、Trace、Artifact 和错误内容 Secret scan/redaction 通过

## E. Elmos 三平面主链路

- [ ] Control Plane 创建 tenant/project/job/workflow
- [ ] Workflow 编译并冻结 workflow/policy revision
- [ ] Scheduler/Temporal 只调度一次，lease 防双执行
- [ ] P01 Runtime Session/Event 可持久化、恢复和回放
- [ ] P02 生成 Repository Graph、Semantic IR、Capability Ledger
- [ ] P03 生成/转换产物有 source/target lineage
- [ ] P04 按语言、OS、风险、硬件选中正确 Worker Pool
- [ ] P06 路由先应用数据/隐私硬约束，选择理由可解释
- [ ] P05 Verifier 产生完整 Evidence Bundle
- [ ] 只有精确 Evidence revision 的 Gate pass 才能进入 completed/release
- [ ] P07 只接收 verified + authorized 学习条目

## F. 健康、性能与容量

- [ ] startup/readiness/liveness probe 语义正确
- [ ] 优雅终止停止领取新任务并完成 checkpoint/flush
- [ ] API、Scheduler、Runtime Gateway、Router、Verifier 有 SLI/SLO
- [ ] HPA/KEDA 根据 RPS、队列、等待时长等指标扩缩容
- [ ] scale-down 稳定窗口不会破坏长任务
- [ ] 数据库连接池、Temporal poller、对象存储吞吐经过压测
- [ ] 10× 正常流量峰值或合同峰值容量模型已验证
- [ ] noisy-neighbor 与 tenant quota 测试通过

## G. 故障、恢复与幂等

- [ ] 杀死 Web/API Pod，服务可用或按 SLO 降级
- [ ] 杀死 Scheduler leader，lease/leader 正确切换
- [ ] 杀死 Worker，任务从可信 checkpoint 恢复
- [ ] Worker 重启不会重复非幂等副作用
- [ ] Provider 429/5xx/timeout 触发合格 fallback 或 durable wait
- [ ] Temporal/DB/Object Store 短暂故障后恢复
- [ ] Redis 全量丢失后系统可重建缓存
- [ ] Evidence 写失败时 P05 阻断完成
- [ ] no-progress/doom-loop 有界停止并保存状态

## H. 备份、恢复与 DR

- [ ] PostgreSQL backup + PITR 恢复到隔离环境
- [ ] Temporal persistence/Workflow 恢复方案验证
- [ ] Object Store 指定版本恢复并校验 hash
- [ ] 配置、镜像、SBOM、签名和 release manifest 可恢复
- [ ] 随机 Job 的 Ledger、Event、Artifact、Evidence 和 Release lineage 完整
- [ ] 实测 RPO/RTO 记录并符合合同
- [ ] Region/Zone 故障、DNS/Gateway/State cutover 演练
- [ ] DR 演练有行动项、owner 和期限

## I. 升级与回滚

- [ ] API/SPI/Schema compatibility report
- [ ] Database expand/migrate/contract 计划
- [ ] Temporal Worker build/version compatibility
- [ ] Helm diff、RBAC diff、NetworkPolicy diff 已审查
- [ ] 内部租户 canary
- [ ] 低风险租户/1–5% canary
- [ ] stability hold 完成
- [ ] 自动和人工 rollback 演练
- [ ] destructive migration 有 forward-fix，不依赖简单 Helm rollback
- [ ] kill switch 和 last-known-good 有效

## J. 可观测、审计与运营

- [ ] tenant/project/job/run/session/task/tool correlation 完整
- [ ] 原始代码/Prompt 默认不进入普通日志
- [ ] Executive、Operations、Conversion、Security、Model/FinOps Dashboard
- [ ] P0/P1 告警路由、on-call、升级链和客户通知
- [ ] Audit export/WORM（适用）
- [ ] Billing ledger 与 Provider/Compute/Object Store 用量对账
- [ ] ETA 预测与实际持续校准
- [ ] Runbook 已由非作者执行演练

## K. P05 部署完成门

- [ ] exact source revision
- [ ] exact release manifest
- [ ] exact workflow/policy revision
- [ ] exact image digests
- [ ] exact schema/migration revision
- [ ] exact environment and RuntimeClass
- [ ] functional/integration/E2E evidence
- [ ] security/supply-chain/secret evidence
- [ ] performance/capacity evidence
- [ ] recovery/backup/rollback evidence
- [ ] documentation/runbook evidence
- [ ] `GateDecision=pass`

## 最终结论

- [ ] Prototype
- [ ] Pilot
- [ ] E3 Team-ready
- [ ] E4 Production-ready
- [ ] E5 Critical-business-ready

**批准人：**  
**证据包 URI/Hash：**  
**Release Manifest Hash：**  
**残余风险与 Owner：**

## L. 大型仓库运行数据库完成门

- [ ] 11 个 Migration 在 PostgreSQL 16/17 空库全部成功
- [ ] 从最近生产 Schema 到 V090 的升级路径通过
- [ ] 136 张父表、31 个函数、8 个 Read Model 清单与当前版本一致
- [ ] 每个账号恰有 3 个物理槽，原子 Claim/Renew/Release 并发测试通过
- [ ] 旧 Worker 的 lease generation/fencing token 写回被拒绝
- [ ] Run/Session Event 序号与哈希链连续
- [ ] Checkpoint 只能引用 sealed manifest 和 available artifact
- [ ] `UNKNOWN_RESULT` Side Effect 阻止 Run 完成
- [ ] 项目生成/跨库转换的 Requirement/Capability Ledger 非空
- [ ] P05 Gate 精确绑定 source/target/policy/workflow/route/toolchain/environment revision
- [ ] Passing Evidence Bundle 未撤销、未过期且 Artifact 可用
- [ ] 旧 Run 完成不会覆盖 Job 的较新 `current_run_id`
- [ ] 成本/收入/审计账本 append-only 且幂等
- [ ] Machine ETA、HITL wait、human-equivalent hours 分开保存
- [ ] 源码、完整 AST/IR、模型长输出和完整 stdout 未作为 PostgreSQL 大字段保存
- [ ] RLS + FORCE RLS 覆盖所有租户父表
- [ ] 高价值事务函数不对 PUBLIC 开放
- [ ] Backup/PITR 恢复后 `database/tests/invariants.sql` 通过

## 数据库函数 Owner 与 RLS

- [ ] `SECURITY DEFINER` Owner 是 `NOLOGIN + BYPASSRLS` 的专用受控角色；
- [ ] 任何 Login Role 都未继承该 Owner；
- [ ] 所有 SECURITY DEFINER 已撤销 PUBLIC EXECUTE；
- [ ] Control API、Scheduler、Runtime Gateway、Verifier、Deployment Gate 只获得所需函数 EXECUTE；
- [ ] `database/roles/roles-and-grants.example.sql` 已按生产角色名审阅并应用。
