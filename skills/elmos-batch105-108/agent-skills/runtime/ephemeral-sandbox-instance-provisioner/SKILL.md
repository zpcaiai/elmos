---
name: ephemeral-sandbox-instance-provisioner
description: 按Run创建每任务隔离微VM/沙箱，注入最小身份、资源、文件和网络策略，并返回可续租实例。
---

# B106-S10 — ephemeral-sandbox-instance-provisioner

## Objective

按Run创建每任务隔离微VM/沙箱，注入最小身份、资源、文件和网络策略，并返回可续租实例。

本 Skill 必须在目标 ELMOS 仓库中产生真实代码、测试、接口和运行证据。只生成文档、占位类、未调用的 Schema 或伪造 PASS 状态不算完成。

## Implementation scope

**Batch:** 106 — Polyglot Ephemeral Preview Runtime

**Blocking dependencies:**
- `B106-S08`
- `B106-S09`

**Primary implementation modules:**
- `runtime/sandbox/SandboxProvisioningService.java`
- `private-runner/internal/sandbox/provider.go`
- `infra/sandbox/`

实现时先解析目标仓库的真实模块边界；若路径不同，必须在 `IMPLEMENTATION_MAP.md` 记录从上述逻辑模块到实际路径的映射，不得因为路径不同而跳过实现。

## Inputs and outputs

### Inputs
- `OCIImageRef`：必须有版本、租户和主体标识。
- `RuntimeManifest`：必须有版本、租户和主体标识。
- `tenant/run identity`：必须有版本、租户和主体标识。

### Outputs
- `SandboxInstance`：必须持久化或内容寻址，并可由下游 Skill 验证。
- `lease token`：必须持久化或内容寻址，并可由下游 Skill 验证。
- `provisioning receipt`：必须持久化或内容寻址，并可由下游 Skill 验证。

机器合同：`contracts/batch-106/B106-S10.json`。

## Repository modules

Codex 必须完成以下落点：

1. 在服务/Runner模块实现核心逻辑，不得只创建Controller或DTO。
2. 在共享Contract模块增加请求、结果、错误与事件Schema。
3. 在持久层增加必要实体、唯一约束、租户约束和幂等键。
4. 在Web端增加状态、错误、证据下钻或审批界面（若本 Skill 有用户交互）。
5. 在CI中增加可重复的单元、集成、负面和契约测试。

## Interfaces and state

### Interfaces
- `POST /api/runtime-runs`
- `event sandbox.provisioned`

### Persisted state
- `runtime_run`：必须包含 tenant_id、version、created_at/updated_at，并采用服务端解析的租户身份。
- `sandbox_instance`：必须包含 tenant_id、version、created_at/updated_at，并采用服务端解析的租户身份。
- `sandbox_lease`：必须包含 tenant_id、version、created_at/updated_at，并采用服务端解析的租户身份。

所有写操作必须具备幂等键或乐观版本；跨进程副作用必须通过Outbox/Workflow receipt记录，不能依赖内存状态。

## Execution workflow

1. 分配全局Run ID和幂等键。
2. 校验镜像签名、租户配额和Policy。
3. 创建每任务隔离实例与只读根文件系统。
4. 挂载最小临时卷并注入短期身份。
5. 应用CPU/内存/PID/磁盘和egress限制。
6. 启动进程并返回租约/Provider实例映射。

每一步必须写出结构化状态与失败原因；重试不得重复创建PR、Endpoint、实例、Commit、证书或其他外部副作用。

## Tests

### Required automated tests
- 同一幂等键不创建重复实例。
- 配额超限拒绝。
- 镜像签名无效拒绝。
- 实例不能访问云metadata。
- 租户隔离网络测试通过。

### Cross-cutting tests

- Tenant isolation：使用两个租户fixture验证查询和写入隔离。
- Idempotency：相同request id重复执行，外部副作用最多一次。
- Cancellation/retry：在关键副作用前后注入失败，验证补偿和重放。
- Forgery rejection：直接提交伪造 `PASS/certified/destroyed` 字段必须被独立Gate拒绝。
- Evidence freshness：head SHA、镜像或Policy变化后旧证据必须失效。

## Evidence

完成时至少产生：
- `provisioning-receipt.json`
- `sandbox-policy.json`
- `instance-identity.json`
- `resource-allocation.json`

每个Evidence对象必须包含：`subject`、`producer`、`toolVersion`、`sourceCommit`、`createdAt`、`sha256`、`tenantId`、`requestId`。大文件可放对象存储，但索引与摘要必须进入不可变Evidence Fabric。

## Stop and escalate

- 输入主体、Commit、镜像、租户或版本不明确时停止，不得猜测。
- 发现需要扩大网络、Secret、文件系统或云权限时停止并请求Policy审批。
- 现有测试失败或证据不完整时返回 `BLOCKED/UNKNOWN`，不得改写为成功。
- 需要删除测试、降低覆盖率、关闭安全检查或扩大allowlist才能通过时停止。
- Provider/SCM/数据库返回不确定结果时保留receipt并进入可重试或人工升级状态。

## Definition of done

- [ ] 每Run独立隔离。
- [ ] 身份短期且最小权限。
- [ ] 资源限制生效。
- [ ] 无裸Provider凭证。
- [ ] 实例可被Reaper定位。
- [ ] 单元、集成、负面、租户隔离、幂等和失败注入测试已在目标仓库实际执行。
- [ ] 相关接口已由至少一个真实调用路径使用，不存在未接线的占位实现。
- [ ] Evidence 已由独立验证器接受，伪造成功fixture被拒绝。
- [ ] `./validate.sh` 及目标仓库构建/测试命令均通过。

## Codex execution contract

Codex应按以下顺序工作：

```text
1. Inspect actual repository architecture and write IMPLEMENTATION_MAP.md.
2. Compile this Skill contract and resolve blocking dependencies.
3. Add failing tests and negative fixtures first.
4. Implement schema, persistence, core service/runner, interface and UI wiring.
5. Run focused tests, then full regression and security/tenant tests.
6. Produce real evidence from executed commands.
7. Run the independent conservative gate.
8. Commit only when every Definition of Done item has evidence.
```
