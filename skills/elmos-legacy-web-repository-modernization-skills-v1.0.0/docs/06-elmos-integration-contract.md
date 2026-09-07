# Elmos 集成契约

## 1. Job Request

```yaml
source:
  repository:
  ref:
  credentialsRef:
target:
  framework: spring-boot
  versionLine: "4.x"
  java: 21
strategy:
  mode: preserve-first
  view: preserve
  security: preserve
  packaging: auto
  cutover: plan-only
equivalence:
  mode: strict
  criticalRoutes: []
environments:
  sourceBaseline:
  targetSandbox:
authority:
  profileRef:
limits:
  maxParallelUnits: 3
  maxRepairIterations: 5
```

## 2. Job Response

必须快速返回：

```yaml
jobId:
state:
snapshotState:
machineEta:
costEstimate:
nextGate:
artifactIndex:
```

## 3. Step Contract

```yaml
step:
  id:
  skillId:
  transformationUnitId:
  deterministicInputHash:
  policySnapshotHash:
  ownerEnvironmentId:
  leaseId:
  fencingToken:
  attempt:
  timeout:
  retryPolicy:
  inputArtifacts:
  outputSchemas:
```

## 4. Artifact Contract

所有 skills 使用统一 envelope，见各 `SKILL.md`。Artifact 发布过程：

```text
upload staging
→ compute digest
→ schema validation
→ register metadata
→ atomic publish
→ emit event
```

## 5. Gate Contract

```yaml
gate:
  id:
  type: automatic|approval
  inputs:
  rules:
  status: pending|passed|failed|waived
  evidenceRefs:
  waiver:
    reason:
    approver:
    expiresAt:
```

Critical security/transaction/data-loss gate 不应允许普通用户 waiver；需组织 policy。

## 6. Model/Tool Policy

- deterministic parser/recipe 优先；
- 模型只读取当前 transformation unit 相关证据；
- 不允许模型凭记忆决定当前 Spring/依赖版本；
- prompt、model、temperature/tool schema/version 写入 provenance；
- tool call 使用 Environment-owned authority；
- 生成 patch 进入 sandbox，未验证不得写主分支。

## 7. Git 输出

推荐：

```text
elmos/migration-manifest/
elmos/evidence/
elmos/reports/
```

目标代码提交策略：

- 一个基础设施/compatibility commit；
- 每 transformation unit 一个或少量语义清晰 commit；
- 测试与转换同 commit 或紧邻；
- 最终清理 legacy 依赖单独 commit；
- 不生成一个无法审查的 giant commit。

## 8. CI/CD 门

最低：

```text
package validate
source baseline reproduction
target compile
target startup
schema/migration
static semantic coverage
generated + existing tests
differential suites
security/SBOM
performance critical routes
/livez /readyz /metrics /version
rollback rehearsal
```
