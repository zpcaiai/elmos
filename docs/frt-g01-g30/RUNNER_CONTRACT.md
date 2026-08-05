# FRT External Runner Contract

> 适用范围：`engines/frontend-client-engine` 的 FRT 控制面（`frt-runtime.ts` / `frt-server.ts`）。
> 本文只定义 runner 与控制面之间的契约，不假设 runner 用什么语言实现。`apps/runner-agent` 目前对 FRT 零感知，按本契约实现即可接入。

## 0. 一句话

控制面**只记录**、**不认证**。runner 上报完成之后，run 走到终态、产物和证据被登记，但 `certificateFragment.certification` 仍是 `NOT_CERTIFIED`、`eligibleForBatchGate` 仍是 `false`。要过批次门禁必须另外发一次 `action: "VERIFY"` 的 run，并带上**独立验证过**的证据。

## 1. 生命周期

```text
run(EXECUTE)  ──►  QUEUED        outcome=PROPOSAL_READY_FOR_RUNNER
   claim      ──►  RUNNING       签发 lease
   heartbeat  ──►  RUNNING       续约（仅持有者，过期不可复活）
   complete   ──►  SUCCEEDED     outcome=RUNNER_EXECUTION_RECORDED
              └─►  FAILED        outcome=RUNNER_EXECUTION_FAILED
              └─►  BLOCKED       outcome=BLOCKED_BY_RUNNER_ATTESTATION / BLOCKED_BY_RUNNER_EVIDENCE
   （租约过期）──►  BLOCKED       outcome=BLOCKED_BY_LEASE_EXPIRED
   retry      ──►  QUEUED        仅限终态的 EXECUTE run
```

每一步都是 CAS：请求里的 `expectedVersion` 必须等于上一步返回的 `version`，否则 `409 FRT_RUN_VERSION_CONFLICT`。**重复提交同一次 complete 会因版本冲突被拒**，这就是幂等保证。

审计事件序列示例：`RUN_CREATED → RUN_CLAIMED → RUN_HEARTBEAT → RUN_COMPLETED`。

## 2. HTTP 面

独立进程，默认 `127.0.0.1:8089`（`ELMOS_FRT_PORT` / `ELMOS_FRT_HOST`）。与 `server.ts` 的无鉴权引擎面**刻意分离**——那一侧零鉴权，两种信任模型不共用进程。

| 方法 | 路径 | 权限 |
|---|---|---|
| GET | `/engine/v1/frt/health` | 无 |
| GET | `/engine/v1/frt/catalog` `?batch=&query=` | `frt:read` |
| GET | `/engine/v1/frt/routes` | `frt:read` |
| POST | `/engine/v1/frt/batches/{G01..G30}/plan` | `frt:plan` |
| POST | `/engine/v1/frt/skills/{skillId}/runs` | `frt:run`（`VERIFY` 另需 `frt:evidence`） |
| GET | `/engine/v1/frt/runs/{runId}` | `frt:read` |
| GET | `/engine/v1/frt/runs/{runId}/audit` | `frt:read` |
| POST | `/engine/v1/frt/runs/{runId}/{claim\|heartbeat\|cancel\|retry}` | `frt:run` |
| POST | `/engine/v1/frt/runs/{runId}/complete` | `frt:run` + `frt:evidence` |

鉴权：`Authorization: Bearer <identity token>`，格式与 `verifyFrtIdentityToken` 一致（`base64url(envelope).base64url(ed25519 signature)`，`IDENTITY` 信任用途）。

**令牌是租户的唯一权威来源。** 创建 run 时请求体 `context` 的 7 个 scope 字段必须与令牌 claims 逐一相等，且 `context.requestedBy` 必须等于 `claims.subject`；不符返回 `403 FRT_SCOPE_MISMATCH` / `403 FRT_ACTOR_MISMATCH`。读取与状态迁移一律以令牌里的 `organizationId`/`tenantId` 为准，请求体说什么都不算。

体量上限：创建 run 16 MiB，其余 64 KiB。

## 3. 租约

见 `schemas/frt-g01-g30/run-lease.schema.json`。

- `claim` 签发租约，TTL 默认 900s，可按次指定，硬边界 `[30, 86400]`。
- **只有持有者能续约**，且**过期的租约不能复活**——必须让控制面回收后 `retry`，否则一个卡死又活过来的 runner 会静悄悄重新拿到权威。
- 建议心跳间隔取 `TTL / 3`。每次心跳都会 bump `version`，runner 必须把心跳返回的 `version` 带进下一次调用。
- 控制面启动时以及 `sweepExpiredLeases()` 被调用时回收过期租约。**租约仍在有效期内的 RUNNING 不会被打扰**，所以重启一个实例不会误杀另一个实例上正在健康执行的 runner。

## 4. 完成上报

见 `schemas/frt-g01-g30/runner-completion.schema.json` 与 `run-completion-request.schema.json`。

签名：对本对象**去掉 `signature` 字段后**的规范化 JSON（`canonicalFrtJson`：对象键按 `localeCompare` 升序、无空白）做 Ed25519 签名，base64url 编码。校验用途是 `RUNNER`，因此信任库里对应的 key 必须在 `purposes` 里包含 `"RUNNER"`。

会**阻断** run 的情况：

| 情况 | finding |
|---|---|
| 签名/时效/信任 key 不通过 | `FRT_RUNNER_ATTESTATION_INVALID` |
| 产物重名 | `FRT_RUNNER_ARTIFACT_NAME_DUPLICATED` |
| 产物缺 digest / URI 为空 / byteCount ≤ 0 | `FRT_RUNNER_ARTIFACT_INTEGRITY_INVALID` |
| 证据 `executor` 不是本 runner | `FRT_RUNNER_EVIDENCE_EXECUTOR_MISMATCH` |
| 证据 `verifier` 等于 executor 或等于本 runner | `FRT_INDEPENDENT_VERIFIER_MISSING` |
| 证据的 `keyId` 与 runner 证明的 `keyId` 相同 | `FRT_EVIDENCE_SIGNER_NOT_INDEPENDENT` |
| 证据 `synthetic: true` | `FRT_SYNTHETIC_EVIDENCE_NON_AUTHORITATIVE` |
| 证据无法按内容寻址解析或签名不符 | `FRT_EVIDENCE_ATTESTATION_INVALID` |
| 同一 role 重复上报 | `FRT_EVIDENCE_ROLE_DUPLICATED` |

**证明未通过时，`customerCodeExecuted` 与 `productionOperationExecuted` 会被强制写回 `false`**，且不采纳任何上报的证据——未经证明的"我执行过"不作数。

`exitStatus: "FAILED"` 本身不阻断：如实上报失败是一次合法的完成，run 进入 `FAILED`，`customerCodeExecuted` 仍可为 `true`（确实执行了，只是失败了）。

## 5. 产物库与证据流水

### 5.1 产物库

内容寻址，限定在 `ELMOS_FRT_ARTIFACT_ROOT` 之下。**对象路径由 digest 派生**，所以调用方给的名字既撞不了也逃不出根目录；同样的字节重复写是 no-op 而非静默覆盖；对象写入后不可变（先写临时兄弟文件再 rename，读者永远看不到半个对象）。读取时重新算 digest 并与路径比对，不符即 `FRT_ARTIFACT_DIGEST_MISMATCH`。

URI 是普通 `file:` URL，所以只要把 artifact root 也列进 `ELMOS_FRT_EVIDENCE_ROOTS`，证据解析器直接就能解析产物，不需要第二套 resolver。

未配置时是 `DenyAllFrtArtifactStore`（fail-closed）。此时 EXECUTE 仍会返回提案，但会带一条**非阻断**的 `FRT_ARTIFACT_STORE_NOT_CONFIGURED`——把「没落盘」显式说出来，而不是假装落了。

方向路径生成成功时，控制面会把目标工程写进产物库，`artifacts.materializedArtifacts` 形如：

```json
{
  "bundle": { "name": "frt-1301-target-workspace", "uri": "file://...", "digest": "sha256:...", "byteCount": 1234 },
  "files":  [ { "name": "src/App.tsx", "uri": "file://...", "digest": "sha256:...", "byteCount": 512 } ]
}
```

以后换对象存储只需换 `FrtArtifactStore` 的实现，运行时不动。

### 5.2 证据：candidate 与 verifier 分离

**runner 不持有 EVIDENCE 密钥，因此它想自签也没钥匙。** 流程拆成两步：

```ts
// runner：把构建日志物化进产物库，产出未签名的 candidate
const candidate = evidenceCandidateFromBytes({
  role: "TARGET_BUILD", executor: "runner-alpha", state: "PASSED",
  bytes: buildLog, store,
});

// 独立 verifier：持另一把 key，把 candidate 签成 FrtEvidenceReference
const evidence = signEvidenceAsVerifier(candidate, {
  verifier: "verifier-independent", authority, keyId: verifierKeyId,
  issuedAt, expiresAt, privateKey: verifierPrivateKey,
});
```

`state` 必须如实填——`NOT_RUN` 和 `INCONCLUSIVE` 都是合法的 candidate，由门禁去拒，这正是它们存在的意义。

**独立性的判定标准是密钥，不是名字。** 只查 `verifier !== executor` 是不够的：持有证据密钥的 runner 只要填两个不同的名字就绕过去了。所以运行时额外强制**证据的 `keyId` 必须 ≠ runner 证明的 `keyId`**。这样「谁来当 verifier」由密钥分发决定，代码只负责认「不是同一把钥匙」。

### 5.3 信任库角色

角色词表与 `scripts/precision_migration/trust.py` 对齐，全平台用同一套说法描述签名权限：

| 角色 | 用途 | 对应内部 purpose |
|---|---|---|
| `identity-issuer` | 会话令牌 | `IDENTITY` |
| `evidence-authorizer` | 签证据 | `EVIDENCE` |
| `gate-evidence-authorizer` | 签前置证书 | `CERTIFICATE` |
| `execution-attester` | 签 runner 完成上报 | `RUNNER` |

`execution-attester` 是 FRT 新增的——precision migration 没有"给自己的执行作证"的 runner。

**结构性约束：信任库加载时就拒绝同时持有 `execution-attester` 与任一 attesting 角色（`evidence-authorizer` / `gate-evidence-authorizer`）的密钥**，报 `FRT_TRUST_KEY_ROLE_CONFLICT`。这样"执行者不能给自己签证据"是信任库的不变量，所有路径自动继承，不必在每个调用点重写检查。调用点的 `keyId` 比较降级为纵深防御的第二道。

如果现有部署里有这样一把"全能 key"，加载会直接失败——这是有意的 fail-closed，问题暴露在启动而不是审计时。

**记录级撤销**：`revokedRecordIds` 与 precision migration 的 `revoked_record_ids` 同义。证据以自身 `digest` 为 record id，完成上报以其载荷 digest 为 record id，证书以 `artifactDigest` 为 record id。一条坏记录可以精确作废，**不必吊销签过其余一切的密钥**。

### 5.4 与 precision migration 的兼容边界

角色词表与**底层签名约定现已统一**，两边可以共用一个信任库文件。

统一的三条约定（`canonicalFrtJson` 与 `trust.py` 的 `canonical_bytes` 必须逐字节一致）：

1. **键序为 Unicode 码点序。** 曾经 FRT 用 `localeCompare`，`trust.py` 用 `sort_keys`。这不只是与 Python 不一致——`localeCompare` 依赖运行时 locale：实测 82 个 locale 里有 8 个（az、cs、sk、lv、lt、uz、cy、es 传统排序）会重排 8 组签名载荷中的 4 组，也就是同一份证据在 en-US 主机上签、在捷克语主机上验会失败。现两边都是码点序。
2. **签名编码为 base64url。** `trust.py` 的 `decode_signature()` 同时接受标准 base64，便于过渡。
3. **非 ASCII 原样 UTF-8，不转义。** 这条原先没被识别出来：Python 的 `json.dumps` 默认 `ensure_ascii=True`，会把非 ASCII 写成 `\uXXXX`，而 `JSON.stringify` 输出字符本身。任何含中文、emoji 的载荷都会因此分叉。现 `trust.py` 显式传 `ensure_ascii=False`。

差分验证：中文、emoji、代理对（`𝄞`）、危险键名（`_x`/`Zulu`/`a-b`/`a1`/`aA`/`ab`）等 7 组向量上 JS 与 Python 输出逐字节一致。回归测试见 `test/frt-runtime.test.ts` 的
"canonical JSON is code-point ordered and matches the Python trust implementation"，其中冻结了三条 parity 向量。

**遗留边界（当前不可达）**：JS 的关系运算符比较 UTF-16 码元，Python 的 `sort_keys` 比较码点。两者仅在键名含辅助平面字符（U+10000 及以上）时分歧——这类字符在 JS 里排在 U+E000..U+FFFF 之前、在 Python 里排在之后。所有签名载荷的键都是 schema 限定的 ASCII 标识符，故触及不到；一旦把任何键名 pattern 放宽到非 ASCII，必须两边同时换成显式码点比较。

**迁移影响**：切换当时两边都没有已签发的记录（信任库未配置、472 个 Skill 全 `NOT_CERTIFIED`、30 条路径证据全 `NOT_RUN`），因此没有重签成本。日后若在上述 8 个 locale 的主机上产生过签名，那些签名在统一后不再验证通过，需要重签。

## 6. 最小接入示例

```bash
# 1. 创建 EXECUTE run（通常由 Console 或编排侧发起）
curl -sX POST "$FRT/engine/v1/frt/skills/FRT-1301/runs" \
  -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d @execute-request.json           # → 202, {"runId":"...","version":1,"state":"QUEUED"}

# 2. runner 领取
curl -sX POST "$FRT/engine/v1/frt/runs/$RUN/claim" \
  -H "authorization: Bearer $RUNNER_TOKEN" -H 'content-type: application/json' \
  -d '{"schemaVersion":"1.0","expectedVersion":1}'   # → 200, version=2, lease{...}

# 3. 长任务续约（TTL/3）
curl -sX POST "$FRT/engine/v1/frt/runs/$RUN/heartbeat" \
  -H "authorization: Bearer $RUNNER_TOKEN" -H 'content-type: application/json' \
  -d '{"schemaVersion":"1.0","expectedVersion":2}'   # → 200, version=3

# 4. 上报完成
curl -sX POST "$FRT/engine/v1/frt/runs/$RUN/complete" \
  -H "authorization: Bearer $RUNNER_TOKEN" -H 'content-type: application/json' \
  -d @completion-request.json        # → 200, state=SUCCEEDED
```

CLI 等价物（同一套校验，走本地 run store）：

```bash
frt-cli claim    --organization ORG --tenant T --run $RUN --actor runner-1 --request transition.json
frt-cli complete --organization ORG --tenant T --run $RUN --actor runner-1 --request completion-request.json
```

## 7. 尚未实现（runner 侧接入前需要知道）

- **证据没有自动采集**：`evidenceCandidateFromBytes` 提供了物化与描述的机制，但「跑完构建自动把日志转成 candidate」这一步仍需 runner 自己接。控制面不会替你采集。
- **verifier 签名服务未落地**：`signEvidenceAsVerifier` 是库函数，谁来运行它、密钥怎么分发和轮换，仍是部署决定。
- **令牌 nonce 未做重放跟踪**：`verifyFrtIdentityToken` 校验签名与时效，但不记录 nonce，短时间内的重放依赖 5 分钟有效期兜底。
- **产物库无生命周期管理**：对象只写不删，没有 GC、配额或保留策略。
- **VERIFY 路径的密钥独立由信任库结构保证，而非逐点检查**：`action: "VERIFY"` 里手工提交的证据仍只在调用点查 `executor !== verifier`，但因为信任库已禁止一把密钥兼具执行与证明角色，执行者本就拿不到能签证据的密钥。若将来引入不经信任库的证据来源，需要补回逐点检查。
