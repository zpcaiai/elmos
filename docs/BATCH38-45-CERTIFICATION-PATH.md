# Batch 38–45 认证路径

从一个空 pack 到一份可信的 `CERTIFIED` 门禁结果，中间每一步的产物、命令和责任人。

工具链入口只有三个脚本：

| 脚本 | 职责 |
|---|---|
| `scripts/mature_product_toolkit.py` | 契约校验、pack 脚手架、候选打分、差距清单、证据清单、认证请求、fail-closed 门禁 |
| `scripts/batch43_schema_compatibility_check.py` | Batch 43 的真实可执行检查：版本化 Schema 面的兼容性 |
| `scripts/mature_product_run_context.py` | 捕获一次真实运行的 artifact、environment 与 provenance |

## 一个 pack 里的产物

脚手架 `make batchNN-scaffold PACK=<key> OWNER=<owner>` 会按模板生成全部契约文件。

**门禁直接读取的四件（closed schema，不可扩展字段）**

| 文件 | 作用 |
|---|---|
| `program.json` | 冻结范围、责任人、覆盖的 Skill ID |
| `evidence.json` | claim 的机器记录：状态、证据引用、来源引用、外部操作授权 |
| `certification.json` | 认证状态与门禁强制的 3 个指标 |
| `gate-result.json` | 门禁运行结果，由 `gate` 子命令写入 |

**范围与度量契约**

| 文件 | 作用 |
|---|---|
| `pack.json` | packType、真实 artifact/environment 摘要、绑定的前置批次 |
| `profile.json` | 风险等级、是否要求 holdout 与代表性负载、全部指标阈值与零容忍项 |
| `support-matrix.json` | 本批每个 Skill 的支持状态与证据引用（capabilityId 用 enum 锁死，漏一个校验就失败） |
| `metrics.json` | 度量台账。`measured=false` 与 `value=0` 是两件事——前者是没人量过 |
| `zero-tolerance.json` | 每个零容忍项的评估结果，`evaluated=false` 视同未通过 |
| `claims.json` | claim 的人类可读陈述、范围与**局限性**。`evidence.json` 是 closed schema，装不下这些 |
| `candidates.json` | 候选工作项与五维打分 |
| `residual-risks.json` | 未关闭的残余风险与责任人 |

**证据与信任链**

| 路径 | 作用 |
|---|---|
| `artifact/`、`environment/` | 被认证的字节本身，以及产生它的工具链 |
| `evidence/<role>/<id>.json` | 证据文件。role 必须是 manifest schema 允许的 8 种之一 |
| `holdout/`、`representative/` | 各恰好一个非空语料文件 |
| `evidence-manifest.json` | 由 `manifest` 子命令从磁盘计算 |
| `certification-request.json` + `.sig` | 由 `request` 子命令生成，再由离线密钥签名 |

## 命令序列

```bash
# 1. 看清差距（随时可跑，不改变任何状态）
make batch43-gaps PACK=elmos-platform-product-lifecycle

# 2. 排序待办
make batch43-score PACK=elmos-platform-product-lifecycle WRITE=1

# 3. 跑真实检查，产出执行证据
make batch43-evidence PACK=elmos-platform-product-lifecycle

# 4. 组装证据清单（下面列的两项断言必须显式给出）
python3 scripts/mature_product_toolkit.py manifest --batch 43 \
  mature-product-packs/batch43/<pack> \
  --artifact <pack>/artifact/schema-surface.json \
  --environment <pack>/environment/toolchain.json \
  --executor ci-runner@example --verifier independent@example \
  --authorization AUTH-XXX --replay-command "..." \
  --started-at <ISO> --finished-at <ISO> \
  --attest-verifier-independent --attest-corpus-independence

# 5. 生成认证请求，并用离线密钥签名
python3 scripts/mature_product_toolkit.py request --batch 43 <pack> --key-id <keyId>
openssl dgst -sha256 -sign <private-key.pem> \
  -out <pack>/certification-request.sig <pack>/certification-request.json

# 6. 跑门禁（必须提供外部可信存储）
make batch43-gate PACK=<pack> TRUST_STORE=<path/to/trust-store.json>
```

## 机器不能替你做的四件事

`manifest` 子命令会拒绝在这些前提缺失时生成清单，这是刻意的：

1. **验证人独立性** —— `--attest-verifier-independent`。执行人与验证人必须是不同身份，且验证人确实独立复现过。
2. **语料作者隔离** —— `--attest-corpus-independence`。holdout 与代表性负载在实现阶段不可见，文件系统证明不了这一点。
3. **问责审批** —— `certification.approvedBy` 必须包含 `program.owner`，且这些人必须出现在 manifest 的 `approvals` 里。
4. **签名** —— 认证密钥必须与执行人不同，且在信任存储中被授权给该批次。私钥不进仓库。

## 当前进度

Batch 43 的 `b43-schema-surface-compatibility` 是唯一一条带真实证据的 claim：

- 检查了 606 个 Schema，其中 527 个与基线版本逐字段比对，0 个破坏性变更，79 个是新增（无基线可比）
- 证据文件：`evidence/execution/b43-schema-compatibility-run.json`（真实运行输出）与 `evidence/provenance/batch43-schema-compatibility-provenance.json`（版本、工具摘要、可复现性判定）
- 该 claim 的局限性写在 `claims.json` 里：只覆盖声明式 Schema 面，运行时 API、SDK、runner 协议与数据库迁移兼容性仍是 NOT_RUN；没有独立验证人复现过

其余批次的 pack 已有真实范围、打过分的待办和残余风险登记，但没有任何证据，因此状态一律 `NOT_RUN`。
完整差距清单见 `docs/BATCH38-45-GAP-INVENTORY.md`，由 `gaps` 子命令确定性生成。
