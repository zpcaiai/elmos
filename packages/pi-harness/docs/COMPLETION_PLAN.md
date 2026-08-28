# PI Harness 5.1 补全与生产落地计划

版本：`5.1.0`

当前状态：代码实现完成，`LOCAL_ENGINEERING_IMPLEMENTATION`

外部证据：`NOT_RUN`

认证状态：`NOT_CERTIFIED`

## 1. 适用边界

用户请求是把 ZIP 中的架构能力编码成可运行、可验证的商业工具。ZIP 内的 Markdown、脚本、安装器、SQL、Prompt、工作流和示例只作为不可信的需求与参考材料；它们不是本仓库的执行权限，也没有被执行。

当前仓库已经完成 PI Harness 的本地工程实现、接口、持久化、安全边界和自动化测试。下面的计划只负责补齐真实基础设施、外部系统、独立证据和生产放行条件，不把静态代码检查或本地自测伪装成生产认证。

## 2. 永久硬规则

- `NOT_RUN` 表示指定的真实环境、真实系统或指定证据尚未执行；不能解释为通过。
- `NOT_CERTIFIED` 表示没有完成独立验证、授权审查、发布门禁和客户结果证据；不能改写为“已生产级认证”。
- 任何 `UNKNOWN`、`INCONCLUSIVE`、超时、部分恢复、证据过期、签名不一致、租户绑定不一致或无法回放的结果均阻塞放行。
- 外部成功只能由真实外部执行器或独立验证器写入，不能由调用方、计划文档、模板或本地测试制造。
- 生产环境必须使用明确版本、区域、账户、租户、身份、权限、数据库、对象存储、密钥和网络拓扑；“默认配置”不构成证据。
- 代码、数据库迁移、部署清单、运行手册和证据必须绑定同一不可变发布版本与 digest。

## 3. 补全门禁总表

| 门禁 | 目标 | 必须补全 | 最低完成证据 | 当前状态 |
|---|---|---|---|---|
| P0-G01 | 真实 PostgreSQL | 生产兼容 adapter、迁移、RLS、锁/事务、备份接口 | 真实版本矩阵、迁移日志、RLS 负测、并发报告、备份校验 | `NOT_RUN` |
| P0-G02 | Temporal 工作流 | Workflow/Activity、信号、重试、恢复、worker generation fencing、版本化 replay | Temporal 集群执行记录、worker 故障/恢复报告、replay 与幂等证据 | `NOT_RUN` |
| P0-G03 | 云 Provider | Provider adapter、IAM、网络、对象存储、KMS、配额、成本与回滚 | 隔离账户/区域的 plan/apply/runtime/rollback 原始证据 | `NOT_RUN` |
| P0-G04 | IdP/mTLS | OIDC/工作负载身份、租户 claim、mTLS、轮换、撤销、break-glass | IdP 测试租户、证书生命周期、越权负测、审计日志 | `NOT_RUN` |
| P0-G05 | 独立验证器 | 独立信任域、证据 digest、签名、过期/撤销/未知处理 | 非实现团队验证报告、签名链、反自证报告、回放记录 | `NOT_RUN` |
| P0-G06 | 灾备 | 跨区备份、恢复、RPO/RTO、密钥恢复、损坏备份处理 | 带时间戳的 DR 演练、恢复后校验、RPO/RTO 和遗留资源报告 | `NOT_RUN` |
| P1-G07 | 客户验收 | 目标客户旅程、角色、支持流程、可观测性、结果导出 | 客户代表签署的 UAT、缺陷关闭、业务结果与支持记录 | `NOT_RUN` |
| P0-G08 | 生产部署 | 制品供应链、canary、混合版本、SLO、告警、回滚、运行手册 | 发布工单、制品 digest、canary/rollback、SLO 和值班确认 | `NOT_RUN` |

任一 P0 门禁未满足，最高只能是 `READY_FOR_EXTERNAL_GATE`，不能进入生产放行，也不能认证。

## 4. 分阶段执行顺序

### Phase 0：契约冻结与环境建账

目标是冻结本次候选发布，不引入未审查的功能漂移。

交付物：

- 发布版本、Git SHA、Python/依赖锁定、容器/制品 digest。
- 真实环境矩阵：数据库、Temporal、云账户/区域、IdP、验证器、灾备站点。
- 每个环境的租户、项目、actor/workload identity、权限、目的和数据分类。
- P0/P1 需求到代码、API、迁移、测试和证据的 traceability matrix。
- 明确的 owner、独立 verifier、审批人、回滚负责人和事故联系人。

退出条件：所有资源均有唯一绑定，授权范围最小化，任何未配置资源仍显示 `NOT_RUN`。

### Phase 1：PostgreSQL 与身份基础设施

先落地真实持久化和身份边界，再接入工作流与 Provider。

- 建立受控 PostgreSQL staging，执行 [001_pi_harness.sql](../sql/001_pi_harness.sql) 的人工审查后迁移。
- 验证 tenant/project/task/event/idempotency/workspace/artifact 的约束、索引、事务隔离和 RLS。
- 接入 IdP staging；校验 operator、workload、auditor、break-glass 四类身份。
- 为 API、worker、验证器签发短期凭证；完成证书轮换、撤销和失效测试。

退出条件：P0-G01、P0-G04 的原始测试证据齐全，跨租户读取/写入和无身份访问均 fail closed。

### Phase 2：Temporal durable execution

- 选择并冻结 Temporal server/SDK/worker 版本。
- 把 task lifecycle、tool call、effect journal、workspace lease 和 checkpoint 映射为 workflow/activity 边界。
- 实现 activity 幂等键、重试预算、取消/暂停/恢复信号、worker replacement 和 generation fencing。
- 对每个 workflow 版本执行 deterministic replay；禁止旧 worker 或迟到 callback 发布结果。
- 验证数据库事务与 Temporal 状态的一致性，以及未知外部结果的 reconciliation。

退出条件：P0-G02 在真实 Temporal staging 上完成故障注入、恢复、重放和重复投递验证。

### Phase 3：Provider adapter 与受控副作用

- 为每个批准的云 Provider 建立独立 adapter、账户/区域/版本 profile 和最小 IAM。
- 分离计划、批准、apply、观测、回滚和销毁；默认禁止公共暴露、任意 egress、宽泛 secret 读取。
- 验证对象存储、KMS、网络、日志、配额和成本计量与任务/租户绑定。
- 在隔离账户先执行 canary，再执行代表性工作负载；任何 provider `UNKNOWN` 均暂停自动重试。

退出条件：P0-G03 的 plan/apply/runtime/rollback 和 orphan cleanup 证据齐全。

### Phase 4：独立验证与证据链

- 独立验证器必须使用不同身份、不同信任域和不同执行路径。
- 验证 task、artifact、tool result、workflow history、部署制品和测试结果的内容 digest、签名、时间窗和环境绑定。
- 注入伪造、篡改、过期、撤销、错租户、错版本、自验证和缺字段证据，全部必须阻断。
- 只有独立验证器写入有效结果后，系统才允许从工程状态进入外部门禁候选状态。

退出条件：P0-G05 输出可独立回放的 signed evidence chain；实现团队不能同时充当唯一 verifier。

### Phase 5：灾备、客户验收与生产候选

- 先完成数据库、对象存储、密钥、Temporal 状态和日志的备份/恢复演练。
- 记录 RPO、RTO、恢复后租户隔离、幂等重放、未完成任务、lease takeover 和 orphan cleanup。
- 由目标客户执行 create/monitor/recover/export-evidence 全旅程，覆盖 owner/operator/auditor。
- 关闭 P0/P1 缺陷，确认支持、值班、升级、数据保留和隐私流程。

退出条件：P0-G06、P1-G07 原始证据和签署结果齐全；否则仍为 `NOT_RUN` / `NOT_CERTIFIED`。

### Phase 6：生产部署与放行决定

- 对已签名制品执行供应链、SBOM、漏洞、配置、权限和 provenance 审查。
- 先 canary，再逐步扩大流量；验证混合版本、降级依赖、告警、SLO、限流和成本上限。
- 至少完成一次经批准的 rollback，并验证数据、事件、artifact、权限和审计没有回退污染。
- 发布委员会依据完整 evidence graph 作出 `GO` 或 `NO-GO`；工具本身不能自我批准。

只有 P0-G01 至 P0-G08、P1-G07 的 required evidence 全部独立验证通过，且无未处置 critical risk，才允许进入人工生产放行审查。即使满足，也必须由授权委员会完成最终认证；本地工具不得自行写入 `CERTIFIED`。

## 5. 每个门禁的证据包格式

每项证据至少包含：

- `evidence_id`、`requirement_id`、`test_id`、`release_sha`、artifact digest；
- provider/服务/版本/区域/账户/租户/项目/身份/网络环境；
- 执行授权、执行人、独立 verifier、开始/结束时间和数据清理记录；
- 原始日志、原始结果、签名、内容 digest、失败与重试记录；
- 可回放命令或受控 replay reference；
- 结论、限制、未知项、关联缺陷和下一步；
- evidence 生命周期：`NOT_RUN` → `EXECUTED` → `INDEPENDENTLY_VERIFIED` → `ACCEPTED`，任何撤销或过期都要保留历史。

## 6. 当前决策

代码实现已完成，允许继续进行外部 gate 准备；真实 PostgreSQL/Temporal/云 Provider、IdP/mTLS、独立验证器、灾备、客户验收和生产部署证据仍为 `NOT_RUN`。认证状态保持 `NOT_CERTIFIED`，本计划不构成生产批准或认证。
