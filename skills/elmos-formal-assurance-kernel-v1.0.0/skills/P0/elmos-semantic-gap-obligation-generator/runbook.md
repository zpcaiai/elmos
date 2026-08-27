# Runbook — Semantic Gap Obligation Generator

## 服务目标

- Skill：`elmos-semantic-gap-obligation-generator`
- 优先级：`P0`
- 默认失败模式：**fail closed**
- 顶层账号并发：**3**
- ETA：仅机器 wall-clock seconds
- SLO：P95 orchestration overhead < 2 s excluding verifier runtime

## 告警

| 告警 | 触发 | 初步动作 |
|---|---|---|
| `FormalProofUnknownRateHigh` | 15m 内 UNKNOWN 比例超过策略阈值 | 检查公式增长、timeout、solver 健康和路由回退 |
| `FormalEvidenceStale` | P0 证据过期或依赖摘要变化 | 冻结对应发布门并生成最小重验计划 |
| `FormalStatusInflationAttempt` | bounded/unknown 被映射为 proved/pass | 拒绝写入，保全审计日志，升级安全事件 |
| `FormalCounterexampleSpike` | 同一规则/模型反例突增 | 停用相关转换规则，回滚到最后可信版本 |
| `FormalCrossTenantAccessDenied` | 跨租户访问或缓存碰撞 | 保留证据，轮换受影响 token/key，执行隔离审计 |
| `FormalVerifierSupplyChainDrift` | adapter image/signature/SBOM 改变 | 隔离 adapter，撤销相关证据，重新固定版本 |

## 排障流程

1. 从 `trace_id` 定位 `proof_run`、`proof_obligation`、`formal_spec` 和 `assumption_hash`。
2. 验证 source/target/model/TCB 摘要是否与提交时一致。
3. 检查 verifier adapter 的版本、签名、资源限制、退出码和原始日志。
4. 对 `UNKNOWN_*` 先缩小义务、增加不变量或选择交叉证明器；禁止直接放宽门禁。
5. 对 `REFUTED_WITH_COUNTEREXAMPLE` 重放 witness，生成永久回归测试，再进入修复循环。
6. 对证据损坏或 owner/fencing 冲突，拒绝覆盖原记录，创建新 run。
7. 任何人工豁免必须走 `elmos-waiver-governance`，包含期限与补偿控制。

## 主要风险

- 证明器超时或内存耗尽
- 语义适配器/模型与真实运行时漂移
- 证据或反例包含客户敏感信息
- 有界结论被错误提升

## 降级策略

- 第三方证明器不可用：仅对允许的非 P0 义务转为替代 verifier 或 `RUNTIME_MONITORED`。
- Artifact Store 不可用：停止提交成功状态；本地临时结果不构成证据。
- Event Bus 不可用：持久化 outbox，恢复后按幂等事件 ID 发布。
- PostgreSQL 只读/故障：停止创建新 proof run，保留正在执行的 sandbox，禁止无记录完成。
- 高负载：按 criticality 排队，绝不突破 account concurrency 或 credit reservation。

## 恢复验证

```bash
python3 scripts/validate_package.py
python3 -m unittest discover -s reference-kernel/tests -v
python3 scripts/run_reference_kernel_demo.py
python3 scripts/check_p05_gate.py --evidence examples/scenarios/p05-evidence.json
```

外部证明器、PostgreSQL、OPA、Kubernetes 和真实客户仓库的检查必须在目标环境单独执行并保存证据。
