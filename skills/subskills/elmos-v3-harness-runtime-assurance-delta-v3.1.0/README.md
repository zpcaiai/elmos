# Elmos v3 Harness Runtime Assurance Delta v3.1.0

这是 **Elmos Proof-Driven Agentic Harness / Repository Semantic Compiler v3.0.0** 的纯增量 Skills Package。

它不复制原有 8-Kernel、5 个 Domain Pack、115 个旧 Skill 映射或 ETGB 数据；安装后组合版本为 **v3.1.0**，原有 16 个 routable Skill 数量保持不变。

## 增量目标

把 2026-08-25 至 2026-08-28 的 Harness Runtime 契约变化收敛进 K1/K4/K5/K6/K7/K8：

1. Tool Result `RAW_RESULT → RESULT_INTERCEPT → RESULT_COMMIT → PUBLISH/MODEL`；
2. 每个 Step 独立的 model-specific finalized `ExecutionPlan`；
3. Canonical `PermissionProfile` 的无损 Resume/Replay；
4. Invocation-scoped `CapabilityLease`；
5. Host-minted `VerifiedSecurityContext`；
6. Environment/Attachment-owned Authority；
7. Remote Executor generation/fencing；
8. Workspace ownership/lease；
9. Harness transport/version/capability negotiation；
10. Skill trust domain 与 signed provenance；
11. Registered durable plugin events；
12. Typed external ingress；
13. Subagent model execution spec。

## 安装

```bash
./scripts/install.sh /path/to/elmos
# 或直接指向已解包的 v3.0.0 package root
./scripts/install.sh /path/to/elmos/packages/elmos-v3
```

安装器会：验证 Delta、核对精确 v3.0.0 基线、逐文件哈希备份、合并 manifest、重算 `FILES.sha256`，并运行组合验证。任何关键映射不精确时 fail closed。

## 验证

```bash
python3 scripts/validate_delta.py
PYTHONPATH=payload/reference-implementation/src   python3 -m unittest discover -s payload/reference-implementation/tests -v
./scripts/test_install_roundtrip.sh   /path/to/elmos-proof-driven-agentic-harness-repository-semantic-compiler-v3.0.0
```

## 卸载

```bash
./scripts/uninstall.sh /path/to/elmos
```

卸载器只删除仍与安装时哈希一致的增量文件；本地已修改文件会保留并报告。被覆盖的基线文件从逐文件备份恢复。

## 诚实边界

本包交付机器契约、Skills、Schema、策略、数据库迁移、Adapter profiles、参考内核、安装/回滚和测试；它不声称真实 Codex/DeepSeek provider、PostgreSQL、OPA、远程 Executor 或客户大型仓库已经完成目标环境认证。
