---
name: test-estate-preservation-gate
description: 比较迁移前后测试发现、执行、跳过、覆盖率和Mutation信号，阻止通过少跑测试获得虚假成功。
---

# B105-S12 — test-estate-preservation-gate

## Objective

比较迁移前后测试发现、执行、跳过、覆盖率和Mutation信号，阻止通过少跑测试获得虚假成功。

本 Skill 必须在目标 ELMOS 仓库中产生真实代码、测试、接口和运行证据。只生成文档、占位类、未调用的 Schema 或伪造 PASS 状态不算完成。

## Implementation scope

**Batch:** 105 — Modernization Demonstration Golden Routes

**Blocking dependencies:**
- `B105-S03`
- `B105-S11`

**Primary implementation modules:**
- `quality/test-preservation/TestEstateComparator.java`
- `adapters/test-reports/`
- `policies/test-preservation.yaml`

实现时先解析目标仓库的真实模块边界；若路径不同，必须在 `IMPLEMENTATION_MAP.md` 记录从上述逻辑模块到实际路径的映射，不得因为路径不同而跳过实现。

## Inputs and outputs

### Inputs
- `baseline test inventory`：必须有版本、租户和主体标识。
- `candidate test reports`：必须有版本、租户和主体标识。
- `coverage/mutation results`：必须有版本、租户和主体标识。

### Outputs
- `TestPreservationDecision`：必须持久化或内容寻址，并可由下游 Skill 验证。
- `before-after metrics`：必须持久化或内容寻址，并可由下游 Skill 验证。
- `missing-test list`：必须持久化或内容寻址，并可由下游 Skill 验证。

机器合同：`contracts/batch-105/B105-S12.json`。

## Repository modules

Codex 必须完成以下落点：

1. 在服务/Runner模块实现核心逻辑，不得只创建Controller或DTO。
2. 在共享Contract模块增加请求、结果、错误与事件Schema。
3. 在持久层增加必要实体、唯一约束、租户约束和幂等键。
4. 在Web端增加状态、错误、证据下钻或审批界面（若本 Skill 有用户交互）。
5. 在CI中增加可重复的单元、集成、负面和契约测试。

## Interfaces and state

### Interfaces
- `POST /api/projects/{id}/gates/test-preservation`
- `event gate.test-preservation.decided`

### Persisted state
- `test_inventory`：必须包含 tenant_id、version、created_at/updated_at，并采用服务端解析的租户身份。
- `test_delta`：必须包含 tenant_id、version、created_at/updated_at，并采用服务端解析的租户身份。
- `test_gate_decision`：必须包含 tenant_id、version、created_at/updated_at，并采用服务端解析的租户身份。

所有写操作必须具备幂等键或乐观版本；跨进程副作用必须通过Outbox/Workflow receipt记录，不能依赖内存状态。

## Execution workflow

1. 标准化JUnit/NUnit/pytest/go test等报告。
2. 比较发现/执行/跳过/失败数量。
3. 按测试ID追踪消失、重命名和新测试。
4. 比较行/分支/Mutation覆盖。
5. 允许经审批的删除但要求替代证据。
6. 保守签发PASS/WARN/FAIL。

每一步必须写出结构化状态与失败原因；重试不得重复创建PR、Endpoint、实例、Commit、证书或其他外部副作用。

## Tests

### Required automated tests
- 1200→430测试即使全绿也FAIL。
- 跳过数增加被拦截。
- 测试重命名可通过映射识别。
- 覆盖率小幅波动按政策判断。
- 报告缺失不得PASS。

### Cross-cutting tests

- Tenant isolation：使用两个租户fixture验证查询和写入隔离。
- Idempotency：相同request id重复执行，外部副作用最多一次。
- Cancellation/retry：在关键副作用前后注入失败，验证补偿和重放。
- Forgery rejection：直接提交伪造 `PASS/certified/destroyed` 字段必须被独立Gate拒绝。
- Evidence freshness：head SHA、镜像或Policy变化后旧证据必须失效。

## Evidence

完成时至少产生：
- `test-inventory-before.json`
- `test-inventory-after.json`
- `test-delta.json`
- `coverage-delta.json`
- `gate-decision.json`

每个Evidence对象必须包含：`subject`、`producer`、`toolVersion`、`sourceCommit`、`createdAt`、`sha256`、`tenantId`、`requestId`。大文件可放对象存储，但索引与摘要必须进入不可变Evidence Fabric。

## Stop and escalate

- 输入主体、Commit、镜像、租户或版本不明确时停止，不得猜测。
- 发现需要扩大网络、Secret、文件系统或云权限时停止并请求Policy审批。
- 现有测试失败或证据不完整时返回 `BLOCKED/UNKNOWN`，不得改写为成功。
- 需要删除测试、降低覆盖率、关闭安全检查或扩大allowlist才能通过时停止。
- Provider/SCM/数据库返回不确定结果时保留receipt并进入可重试或人工升级状态。

## Definition of done

- [ ] 无未解释测试消失。
- [ ] 跳过未增加或有批准。
- [ ] 覆盖率不低于政策。
- [ ] 报告来源可信。
- [ ] Gate结果进入PR检查。
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
