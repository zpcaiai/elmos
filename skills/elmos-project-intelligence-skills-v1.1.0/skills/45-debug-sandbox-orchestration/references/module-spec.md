# 调试沙箱、运行环境与会话编排 — Module Specification

## 1. Epic

- **Epic ID**：`EPIC-45`
- **Skill**：`elmos-debug-sandbox-orchestration`
- **批次**：`BATCH-14-online-debug-and-learning`
- **目标**：让用户能够运行和调试项目，同时确保调试代码、表达式、依赖和测试数据无法逃逸到宿主机、其他租户或未授权网络。

## 2. 用户价值

为在线调试创建一次性、可复现、最小权限的运行沙箱。用于 Runtime Profile、构建与启动、资源配额、网络和密钥策略、会话心跳、清理、生产环境禁用与紧急审批。

## 3. 功能需求

| ID | 需求 |
|---|---|
| `REQ-45-01` | 每个会话使用独立运行边界，禁止挂载宿主 Docker Socket 或跨租户共享可写卷。 |
| `REQ-45-02` | 同一 manifest、镜像摘要和输入数据应能重建等价调试环境。 |
| `REQ-45-03` | 生产 attach 默认拒绝；紧急模式需职责分离、到期授权、只读优先和完整审计。 |
| `REQ-45-04` | 会话终止后必须回收进程、端口、卷、凭据、网络策略和 adapter lease。 |
| `REQ-45-05` | 构建、依赖下载、表达式求值和网络访问均受配额、白名单与 kill switch 控制。 |

## 4. API 触点

- `/api/v1/debug/runtime-profiles`
- `/api/v1/debug/workspaces`
- `/api/v1/debug/workspaces/{workspaceId}/attestation`
- `/api/v1/debug/policies/evaluate`

所有 API/WS 必须：

- 绑定 `tenant_id`、`project_id`、`revision_id`、`debug_session_id` 和服务端授权上下文；
- 控制命令携带 `command_id`、序列号、幂等/去重语义和能力检查；
- 支持心跳、断线恢复、超时、取消、终止和明确错误码；
- 不在 URL、错误消息、日志或事件中泄露源代码、变量、凭据和跨租户对象；
- 对变量、事件和时间线提供分页、大小上限、截断与脱敏元数据。

## 5. 主要领域实体

- `RuntimeProfile`
- `DebugWorkspace`
- `DebugTarget`
- `SandboxPolicy`
- `SecretLease`
- `NetworkPolicy`
- `WorkspaceAttestation`

实体必须包含 stable ID、tenant/project/revision scope、adapter/runtime version、created/updated/actor、policy decision、audit/evidence 和生命周期状态。

## 6. 事件与异步工作

建议事件命名：`elmos.project-intelligence.debug.<domain>.<event>.v1`。

- 会话至少区分 requested、provisioning、launching、ready、paused、running、terminating、terminated、failed 和 expired；
- 事件携带引用和脱敏摘要，不携带无限变量树或大段源代码；
- 命令消费者必须按 `command_id` 去重；
- worker/adapter 崩溃必须进入可诊断状态并触发安全清理；
- poison event 进入隔离队列，不能阻塞其他会话。

## 7. UI/交互要求

- 始终显示 project revision、runtime profile、adapter version、环境、权限模式和剩余会话时间；
- 不支持或被策略禁止的命令必须禁用并解释原因；
- 敏感/截断/采样/低置信度数据有明确视觉标识；
- 调试状态能深链到代码、架构、流程、数据、测试和学习任务；
- 键盘操作、屏幕阅读器、高对比度和断线恢复达到可访问性要求。

## 8. 非功能要求

- 定义 provision、launch-to-ready、command、variable expansion、timeline 和 cleanup 的 p50/p95/p99；
- 每个租户、项目和用户有并发、CPU、内存、磁盘、网络、日志、时长和存储配额；
- 会话控制面和运行面隔离，运行时不可直连系统数据库；
- 所有协议、Schema、adapter/runtime image 和 policy 都版本化；
- 会话终止、权限撤销或租约到期后 fail closed。

## 9. 关键指标

- workspace provision latency p95
- cleanup success rate
- sandbox escape findings
- resource quota violations
- reproducible launch rate

## 10. 交付物

- `services/debug-session-orchestrator`
- `workers/debug-sandbox-runner`
- `debug-sandbox-security-report.md`

## 11. 任务清单

| Task | 标题 | 类型 | 优先级 |
|---|---|---|---|
| `ELMOS-PI-45-T01` | 定义语言/框架 Runtime Profile，并绑定构建命令、启动目标、端口、环境、adapter 和镜像摘要 | implementation | P1 |
| `ELMOS-PI-45-T02` | 创建非 Root、只读根文件系统、临时可写层、资源配额、进程限制和系统调用隔离的容器或微型虚拟机 | implementation | P1 |
| `ELMOS-PI-45-T03` | 实现 launch/attach 环境资格策略；生产进程默认不可暂停或附加 | implementation | P1 |
| `ELMOS-PI-45-T04` | 接入 Secrets Broker、短期凭证、合成/脱敏数据集和默认拒绝的出站网络策略 | implementation | P1 |
| `ELMOS-PI-45-T05` | 实现 provision→build→launch→heartbeat→terminate→cleanup→attest 全生命周期和超时回收 | implementation | P1 |
| `ELMOS-PI-45-T06` | 实现表达式/调试控制台策略：默认只读，副作用表达式仅在一次性环境经显式审批后执行 | implementation | P1 |
| `ELMOS-PI-45-T07` | 实现权限、安全、沙箱和不可信输入防护 | security | P1 |
| `ELMOS-PI-45-T08` | 接入日志、指标、Trace、错误分类、资源计量和审计 | observability | P1 |
| `ELMOS-PI-45-T09` | 建立单元、协议合规、集成、E2E、恢复、安全与性能测试 | testing | P1 |
| `ELMOS-PI-45-T10` | 更新 API、事件、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |

## 12. 验收标准

| ID | 验收标准 |
|---|---|
| `AC-45-01` | 跨租户、宿主文件、Docker Socket、特权系统调用和未授权网络访问测试全部 fail closed。 |
| `AC-45-02` | 会话结束后不存在残留进程、端口、凭据或可写工作区。 |
| `AC-45-03` | 未获得 break-glass 授权时生产 attach 请求被拒绝并生成审计事件。 |
| `AC-45-04` | Fork bomb、内存/磁盘耗尽、无限输出和网络滥用被配额与 kill switch 控制。 |
| `AC-45-05` | 固定 manifest 的重复启动得到相同工具链、依赖和入口配置。 |

## 13. 依赖

- `elmos-reference-architecture`
- `elmos-security-threat-model`
- `elmos-deployment-private-cloud`
- `elmos-observability-slo`

## 14. 失败与恢复

- 错误分类为 configuration、build、adapter、protocol、runtime、policy、capacity、permission、replay、unsupported 和 internal。
- 控制命令失败不得自动重复有副作用操作；只读查询可按策略安全重试。
- 断线恢复前验证 session lease、revision、adapter/runtime version 和权限仍有效。
- 取消或超时立即停止新命令，随后执行有界清理并生成 attestation。
- 无法恢复时保留脱敏诊断、审计和 checkpoint，不保留长期 Secret 或无限变量数据。
