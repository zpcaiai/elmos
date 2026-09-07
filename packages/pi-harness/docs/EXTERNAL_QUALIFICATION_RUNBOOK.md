# PI Harness 5.1 外部门禁执行手册

版本：`5.1.0`

当前外部证据：`NOT_RUN`

当前认证：`NOT_CERTIFIED`

## 1. 用途与权限边界

本手册用于依次执行 P0-G01 至 P0-G08 和 P1-G07。仓库代码负责校验、保存和审计证据，但不会替基础设施管理员、独立验证器、客户代表或发布委员会执行其职责。

以下材料都不能把门禁改为通过：计划、模板、代码存在、Mock、单元测试、本地容器、SDK 导入、Terraform `validate`、实现团队自签名、未绑定精确 RC 的日志。没有真实目标、授权和原始证据时，状态必须保持 `NOT_RUN`。

## 2. 必须先取得的外部输入

执行前由对应责任人提供并登记：

- PostgreSQL staging 的独立数据库/项目、版本、区域、账户、网络入口、迁移身份、应用身份和清理授权；
- Temporal staging 的精确 endpoint、namespace、server/SDK 版本、CA、短期 client certificate/key 和 worker 身份；
- 隔离云账户、区域、provider 版本、最小 IAM、预算、KMS、对象存储、网络和 destroy/rollback 授权；
- IdP staging issuer、audience、JWKS endpoint、测试租户、测试用户/工作负载、CA/CRL 和证书轮换授权；
- 与实现团队不同信任域的独立验证机构、Ed25519 公钥、有效期、撤销状态和 scope；
- 隔离 DR 目标、备份/恢复密钥、书面 RPO/RTO、演练窗口和清理责任人；
- 客户 UAT 租户、客户测试代表、旅程、验收标准、缺陷处置规则和客户签名公钥；
- 生产候选环境、变更工单、发布/回滚负责人、值班人、SLO、canary 阈值和发布委员会公钥。

任一值缺失、歧义、过期、无法验证或指向共享数据环境，停止对应门禁，不推断默认值。

## 3. 冻结一个不可变 RC

先生成 wheel/container/IaC/SBOM 等实际候选制品，再对每个制品计算 SHA-256。创建符合 [release-candidate.schema.json](../schemas/release-candidate.schema.json) 的 JSON 文件。字段必须使用真实值；尖括号占位符不是可执行值。

```json
{
  "schema_version": "elmos.pi-harness.release-candidate/v1",
  "release_id": "<new-uuid>",
  "source_git_sha": "<exact-40-character-git-sha>",
  "package_version": "5.1.0",
  "source_archive_digest": "sha256:<attached-source-archive-sha256>",
  "artifact_digests": {
    "wheel": "sha256:<built-wheel-sha256>",
    "container": "sha256:<published-image-manifest-sha256>",
    "terraform": "sha256:<reviewed-iac-bundle-sha256>"
  },
  "implementation_trust_domain": "<implementation-team-trust-domain>",
  "created_at": "<utc-rfc3339-time>",
  "frozen_by": "<authorized-release-manager-identity>",
  "limitations": []
}
```

所有 CLI 输入、ledger root 和原始证据都必须使用绝对、非符号链接路径。初始化一个全新的受限目录：

```bash
elmos-pi-harness qualification-init \
  --ledger-root /absolute/immutable/pi-harness-5.1-rc-ledger \
  --release-manifest /absolute/input/release-candidate.json
```

初始化后 `release.json` 不可替换。同一个 root 只绑定一个 RC；代码变更或制品 digest 变化必须创建新 RC 和新 ledger。

## 4. 每项门禁的统一记录流程

### 4.1 真实执行

由已授权外部 runner 执行门禁，保存 provider-native 原始日志、测试结果、环境快照、授权记录、清理/回滚结果。然后创建符合 [external-gate-result.schema.json](../schemas/external-gate-result.schema.json) 的结果文件。

只有真实运行成功可以写 `EXECUTED`。失败写 `FAILED`；超时、结果不确定、provider 返回未知或无法确认清理时写 `UNKNOWN`。三者都固定 `certified:false`。

```bash
elmos-pi-harness qualification-record \
  --ledger-root /absolute/immutable/pi-harness-5.1-rc-ledger \
  --result /absolute/input/P0-G01-result.json \
  --raw-evidence /absolute/raw/P0-G01-migration.log \
  --raw-evidence /absolute/raw/P0-G01-rls-negative.json
```

`--raw-evidence` 顺序必须与结果文件中的 `raw_evidence_digests` 完全一致。导入前会重新计算 SHA-256；数量、顺序或内容不一致都会拒绝，且不会写入状态事件。

### 4.2 独立验证

独立验证器从不可变存储取得原始证据和 RC，使用独立执行路径复核。其签名 receipt 必须符合 [signed-verification.schema.json](../schemas/signed-verification.schema.json)，scope 为 `external_gate:<gap-id>`，subject 为执行结果 digest，并精确绑定环境、授权、runner、时间窗和全部原始证据 digest。

信任库必须符合 [verifier-trust-store.schema.json](../schemas/verifier-trust-store.schema.json)，由实现团队之外的信任管理员维护。执行者与验证者不能属于同一 trust domain。

```bash
elmos-pi-harness qualification-verify \
  --ledger-root /absolute/immutable/pi-harness-5.1-rc-ledger \
  --receipt /absolute/verifier/P0-G01-verification.json \
  --trust-store /absolute/trust/current-verifier-trust-store.json
```

只有签名有效、key 未撤销且在有效期内、role 包含 `independent_verifier`、scope/subject/环境完全匹配且 verdict 为 `VERIFIED`，状态才进入 `INDEPENDENTLY_VERIFIED`。`REJECTED` 进入 `FAILED`，`INCONCLUSIVE` 进入 `UNKNOWN`。

### 4.3 客户或发布接受

P1-G07 必须由 `customer_authority` 角色签署；P0-G08 必须由 `release_authority` 签署。其他门禁若组织要求额外接受，则由 `acceptance_authority` 签署。接受者必须同时独立于实现团队和独立验证者，其 receipt scope 为 `external_gate_acceptance:<gap-id>`，subject 为该门禁最新独立验证事件 digest。

```bash
elmos-pi-harness qualification-accept \
  --ledger-root /absolute/immutable/pi-harness-5.1-rc-ledger \
  --receipt /absolute/authority/P1-G07-customer-acceptance.json \
  --trust-store /absolute/trust/current-verifier-trust-store.json
```

## 5. 逐门禁执行顺序

在每次外部执行/验证后，把当前 ledger 快照写入独立管理的 S3 Object Lock bucket。配置须符合 [immutable-evidence-s3.schema.json](../schemas/immutable-evidence-s3.schema.json)，bucket 必须启用 versioning、精确 KMS 和足够长的 Object Lock retention：

```bash
elmos-pi-harness qualification-archive \
  --ledger-root /absolute/immutable/pi-harness-5.1-rc-ledger \
  --configuration /absolute/config/immutable-evidence-s3.json \
  --authorization-id '<approved-archive-operation>' \
  --actor-id '<archive-workload-identity>'
```

该命令逐个归档 release、events 和 raw objects，最后写入 snapshot manifest；receipt 绑定 S3 VersionId、SHA-256、KMS、lock mode 和 retain-until。provider timeout 后只允许读取并核对精确对象来 reconciliation；无法观测时返回未知并阻止自动重试。Terraform 已声明独立 Object Lock bucket，但只有真实账户中的 `plan/apply/runtime` 证据才能清除 P0-G03/P0-G05 的 `NOT_RUN`。

### P0-G01 PostgreSQL staging

1. 在专用 staging 数据库执行 001/002 checksum-locked migration。
2. 以 `NOSUPERUSER NOBYPASSRLS` 应用角色验证所有读写路径。
3. 执行错租户、缺 tenant context、错 project、并发 lease、幂等、死锁/断连负测。
4. 验证备份 digest、加密、隔离恢复和清理。
5. 记录执行结果，再由独立验证器复核。

专用 staging 目标或数据库管理员授权缺失时保持 `NOT_RUN`；本地 PostgreSQL 容器不替代该门禁。

### P0-G04 IdP/mTLS

1. 验证 issuer/audience/JWKS、operator/workload/auditor 和 tenant/project binding。
2. 验证双向 TLS、SPIFFE identity、短期证书、轮换、过期和 CRL 撤销。
3. 执行无 token、错 issuer、错 audience、错租户、证书重放和 caller-supplied tenant spoofing 负测。
4. 保存 IdP、ingress 和应用审计原始日志，完成独立复核。

真实 issuer、CA/CRL、测试身份或授权缺失时保持 `NOT_RUN`。

### P0-G02 Temporal staging

1. 连接精确 TLS endpoint/namespace，启动独立 worker identity。
2. 执行 create/pause/resume/cancel/retry/checkpoint 和 artifact 发布旅程。
3. 注入 worker crash/replacement、late callback、重复 activity、短断网和数据库短断。
4. 对实际 history 执行 deterministic replay，验证 generation fencing 与幂等。
5. 保存 Temporal native history、worker 日志、数据库状态和 replay 输出，完成独立复核。

本地 dev server 不替代真实 Temporal staging，外部 endpoint/certificate 缺失时保持 `NOT_RUN`。

### P0-G03 云 Provider

1. 对精确 provider/account/region/version 生成并审查 plan。
2. 独立审批后在隔离账户 apply，验证 runtime、IAM、网络、KMS、对象存储、日志、配额和成本。
3. 执行 canary、rollback、destroy 和 orphan cleanup。
4. 对 timeout/unknown result 只执行 reconciliation，不盲目重试。
5. 保存 provider-native 与 normalized evidence，完成独立复核。

有效短期凭证、区域、预算和 apply/destroy 授权缺失时保持 `NOT_RUN`；`terraform validate` 不算云执行。

### P0-G05 独立验证器

1. 使用与实现团队不同的组织、身份、凭证、trust domain 和 holdout workload。
2. 复核 RC、artifact、环境、授权、原始证据、replay 和清理。
3. 注入篡改、错 RC、错环境、过期、撤销、自证和缺字段 receipt，全部应失败关闭。
4. 由外部信任管理员保存公钥、role、scope、有效期和撤销记录。

实现团队本地生成的测试 key 只能证明代码路径，P0-G05 仍保持 `NOT_RUN`。

### P0-G06 灾备

1. 依据批准场景捕获 PostgreSQL、artifact、Temporal、配置、证书/密钥引用和审计数据。
2. 在隔离目标执行恢复，验证租户隔离、数据/event digest、未完成任务、lease、幂等和 orphan cleanup。
3. 记录完整时间线和实测 RPO/RTO；失败或部分恢复不能写成功。
4. 由独立验证器复核备份、恢复和残留资源。

隔离恢复目标、密钥权限、演练窗口或书面 RPO/RTO 缺失时保持 `NOT_RUN`。

### P1-G07 客户 UAT

1. 客户代表在客户 UAT 租户执行 create → monitor → pause/resume → worker-loss recovery → artifact/evidence export。
2. 覆盖 owner/operator/auditor，记录支持升级和缺陷处置。
3. 独立验证器复核运行结果。
4. 客户 `customer_authority` 对最新验证事件签署接受 receipt。

内部产品人员不能代替客户签署；客户、旅程或签名权缺失时保持 `NOT_RUN`。

### P0-G08 生产部署与回滚

1. 验证已发布制品 digest、签名、SBOM/provenance、配置、权限和变更工单。
2. 执行 canary、SLO 观察、告警确认和逐步 promotion。
3. 至少执行一次批准的 rollback，并验证数据、事件、artifact、身份和审计无污染。
4. 独立验证器复核；`release_authority` 签署接受 receipt。

程序只可输出 `READY_FOR_HUMAN_DECISION`。最终认证必须由仓库之外的授权委员会完成，不能向 ledger 写入 `CERTIFIED`。

## 6. 每次检查都重新验证信任库

```bash
elmos-pi-harness qualification-status \
  --ledger-root /absolute/immutable/pi-harness-5.1-rc-ledger \
  --trust-store /absolute/trust/current-verifier-trust-store.json
```

状态命令会重新读取完整 hash chain、重新计算所有 raw object digest，并用当前信任库检查 receipt 的 key、scope、role、有效期和撤销状态。不提供当前信任库时，历史签名事件会显示 `live_trust_store_revalidation_required` 并阻塞决定。

即使所有要求都满足，唯一允许的最高输出是：

```json
{
  "qualification_decision": "READY_FOR_HUMAN_DECISION",
  "certification": "NOT_CERTIFIED",
  "certified": false,
  "blockers": ["external_production_certification_authority_required"]
}
```

## 7. 当前执行结论

仓库已具备上述执行、验证和审计入口，但当前没有已登记的真实外部 target、授权、外部 runner、独立 verifier、客户签署或生产发布证据。因此 PostgreSQL staging、Temporal、Cloud Provider、IdP/mTLS、独立验证、DR、客户 UAT 和生产部署仍全部为 `NOT_RUN`，认证为 `NOT_CERTIFIED`。
