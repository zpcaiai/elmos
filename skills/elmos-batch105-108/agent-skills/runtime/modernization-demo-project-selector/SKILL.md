---
name: modernization-demo-project-selector
description: 对公开或客户仓库进行可演示性评分，选择既真实、又可在受控时间内形成前后对比的现代化样本。
---

# B105-S01 — modernization-demo-project-selector

## Objective

对公开或客户仓库进行可演示性评分，选择既真实、又可在受控时间内形成前后对比的现代化样本。

本 Skill 必须在目标 ELMOS 仓库中产生真实代码、测试、接口和运行证据。只生成文档、占位类、未调用的 Schema 或伪造 PASS 状态不算完成。

## Implementation scope

**Batch:** 105 — Modernization Demonstration Golden Routes

**Blocking dependencies:**
- `B104-S16`

**Primary implementation modules:**
- `services/control-plane/.../demo/ProjectSelectorService.java`
- `services/control-plane/.../demo/DemoCandidateRepository.java`
- `apps/web/src/features/demo-candidates/`

实现时先解析目标仓库的真实模块边界；若路径不同，必须在 `IMPLEMENTATION_MAP.md` 记录从上述逻辑模块到实际路径的映射，不得因为路径不同而跳过实现。

## Inputs and outputs

### Inputs
- `RepositoryRef`：必须有版本、租户和主体标识。
- `license policy`：必须有版本、租户和主体标识。
- `target audience`：必须有版本、租户和主体标识。
- `time/cost budget`：必须有版本、租户和主体标识。

### Outputs
- `DemoCandidateScorecard`：必须持久化或内容寻址，并可由下游 Skill 验证。
- `selection decision`：必须持久化或内容寻址，并可由下游 Skill 验证。
- `rejection reasons`：必须持久化或内容寻址，并可由下游 Skill 验证。

机器合同：`contracts/batch-105/B105-S01.json`。

## Repository modules

Codex 必须完成以下落点：

1. 在服务/Runner模块实现核心逻辑，不得只创建Controller或DTO。
2. 在共享Contract模块增加请求、结果、错误与事件Schema。
3. 在持久层增加必要实体、唯一约束、租户约束和幂等键。
4. 在Web端增加状态、错误、证据下钻或审批界面（若本 Skill 有用户交互）。
5. 在CI中增加可重复的单元、集成、负面和契约测试。

## Interfaces and state

### Interfaces
- `POST /api/demo-candidates/score`
- `GET /api/demo-candidates/{id}`
- `event demo.candidate.scored`

### Persisted state
- `demo_candidate`：必须包含 tenant_id、version、created_at/updated_at，并采用服务端解析的租户身份。
- `candidate_signal`：必须包含 tenant_id、version、created_at/updated_at，并采用服务端解析的租户身份。
- `candidate_decision`：必须包含 tenant_id、version、created_at/updated_at，并采用服务端解析的租户身份。

所有写操作必须具备幂等键或乐观版本；跨进程副作用必须通过Outbox/Workflow receipt记录，不能依赖内存状态。

## Execution workflow

1. 读取仓库元数据并固定默认分支SHA。
2. 检测语言、框架、构建、测试、API、页面和数据库。
3. 检查许可证、活跃度、规模和敏感内容。
4. 运行轻量静态探测，不执行不可信代码。
5. 按真实性、可构建性、可见接口、迁移差距、演示价值评分。
6. 生成选择/拒绝决定并保留可解释特征。

每一步必须写出结构化状态与失败原因；重试不得重复创建PR、Endpoint、实例、Commit、证书或其他外部副作用。

## Tests

### Required automated tests
- 公开Spring Boot 2项目获得可解释高分。
- 无许可证项目被拒绝。
- 无测试且无可见服务的仓库不得进入Golden Route。
- 伪造语言信号不覆盖构建文件证据。
- 租户A不能读取租户B候选。

### Cross-cutting tests

- Tenant isolation：使用两个租户fixture验证查询和写入隔离。
- Idempotency：相同request id重复执行，外部副作用最多一次。
- Cancellation/retry：在关键副作用前后注入失败，验证补偿和重放。
- Forgery rejection：直接提交伪造 `PASS/certified/destroyed` 字段必须被独立Gate拒绝。
- Evidence freshness：head SHA、镜像或Policy变化后旧证据必须失效。

## Evidence

完成时至少产生：
- `candidate-scorecard.json`
- `repository-fingerprint.json`
- `license-decision.json`
- `selection-decision.json`

每个Evidence对象必须包含：`subject`、`producer`、`toolVersion`、`sourceCommit`、`createdAt`、`sha256`、`tenantId`、`requestId`。大文件可放对象存储，但索引与摘要必须进入不可变Evidence Fabric。

## Stop and escalate

- 输入主体、Commit、镜像、租户或版本不明确时停止，不得猜测。
- 发现需要扩大网络、Secret、文件系统或云权限时停止并请求Policy审批。
- 现有测试失败或证据不完整时返回 `BLOCKED/UNKNOWN`，不得改写为成功。
- 需要删除测试、降低覆盖率、关闭安全检查或扩大allowlist才能通过时停止。
- Provider/SCM/数据库返回不确定结果时保留receipt并进入可重试或人工升级状态。

## Definition of done

- [ ] 评分规则版本化。
- [ ] 每个分值可追溯到证据。
- [ ] 拒绝原因机器可读。
- [ ] 未执行仓库代码。
- [ ] 至少3类候选fixture通过。
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
