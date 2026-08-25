# 调试适配器网关与能力协商 — Module Specification

## 1. Epic

- **Epic ID**：`EPIC-44`
- **Skill**：`elmos-debug-adapter-gateway`
- **批次**：`BATCH-14-online-debug-and-learning`
- **目标**：在不把某一语言调试器能力误认为所有运行时都支持的前提下，为 Elmos 提供版本化、可观测、可隔离的统一调试控制面。

## 2. 用户价值

建设统一调试适配器网关，规范化 DAP、浏览器调试协议和各语言原生调试器差异。用于会话代理、能力协商、断点/栈/变量事件转换、连接恢复和适配器合规测试。

## 3. 功能需求

| ID | 需求 |
|---|---|
| `REQ-44-01` | 每个适配器必须声明实际支持的能力；UI 不得展示或承诺未支持的命令。 |
| `REQ-44-02` | 所有消息绑定 tenant、project、revision、debug_session 与单调递增序列。 |
| `REQ-44-03` | 源码映射必须固定到同一 Project Revision，禁止映射到漂移分支。 |
| `REQ-44-04` | 适配器崩溃、恶意消息或协议失序不得影响网关和其他租户会话。 |
| `REQ-44-05` | 适配器升级必须有兼容矩阵、灰度、回滚和会话版本钉住。 |

## 4. API 触点

- `/api/v1/debug/adapters`
- `/api/v1/debug/adapters/{adapterId}/capabilities`
- `/api/v1/debug/sessions/{sessionId}/transport`
- `/ws/v1/debug/sessions/{sessionId}`

所有 API/WS 必须：

- 绑定 `tenant_id`、`project_id`、`revision_id`、`debug_session_id` 和服务端授权上下文；
- 控制命令携带 `command_id`、序列号、幂等/去重语义和能力检查；
- 支持心跳、断线恢复、超时、取消、终止和明确错误码；
- 不在 URL、错误消息、日志或事件中泄露源代码、变量、凭据和跨租户对象；
- 对变量、事件和时间线提供分页、大小上限、截断与脱敏元数据。

## 5. 主要领域实体

- `DebugAdapter`
- `AdapterVersion`
- `AdapterCapability`
- `ProtocolMessage`
- `SourceMapBinding`
- `AdapterLease`

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

- adapter handshake success rate
- debug command latency p95
- protocol error rate
- reconnect recovery rate
- source-map resolution accuracy

## 10. 交付物

- `services/debug-gateway`
- `debug-adapters/registry.yaml`
- `debug-adapter-conformance-report.md`

## 11. 任务清单

| Task | 标题 | 类型 | 优先级 |
|---|---|---|---|
| `ELMOS-PI-44-T01` | 建立 JVM、Python、.NET、Node/TypeScript、Go、Rust/C++、PHP、Dart/Flutter、Swift/Objective-C 与 Browser 的适配器注册表和版本矩阵 | implementation | P1 |
| `ELMOS-PI-44-T02` | 实现 DAP Session Broker、请求/响应序列关联和 WebSocket 双向传输 | implementation | P1 |
| `ELMOS-PI-44-T03` | 实现 Browser/CDP Bridge、Source Map 解析与前端源文件 revision 绑定 | implementation | P1 |
| `ELMOS-PI-44-T04` | 实现适配器进程生命周期、健康检查、版本钉住、能力协商和优雅关闭 | implementation | P1 |
| `ELMOS-PI-44-T05` | 统一 Breakpoint、Thread、Stack、Scope、Variable、Evaluate、Output、Module 和 Termination 模型 | implementation | P1 |
| `ELMOS-PI-44-T06` | 实现背压、事件去重、断线重连、懒加载变量分页、超大对象截断和协议错误隔离 | implementation | P1 |
| `ELMOS-PI-44-T07` | 实现权限、安全、沙箱和不可信输入防护 | security | P1 |
| `ELMOS-PI-44-T08` | 接入日志、指标、Trace、错误分类、资源计量和审计 | observability | P1 |
| `ELMOS-PI-44-T09` | 建立单元、协议合规、集成、E2E、恢复、安全与性能测试 | testing | P1 |
| `ELMOS-PI-44-T10` | 更新 API、事件、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |

## 12. 验收标准

| ID | 验收标准 |
|---|---|
| `AC-44-01` | Java/Kotlin、Python、Node/TypeScript 和 .NET 四类 P0 适配器通过统一合规套件。 |
| `AC-44-02` | 不受支持的断点、反向执行或内存能力会被明确禁用并显示原因。 |
| `AC-44-03` | 网络短暂中断后会话能恢复，且不会重复执行调试命令。 |
| `AC-44-04` | Source Map 能将前端暂停位置准确定位到固定 revision 的源代码。 |
| `AC-44-05` | 畸形、超大或恶意适配器消息被隔离，其他会话不受影响。 |

## 13. 依赖

- `elmos-reference-architecture`
- `elmos-multilanguage-parsing`
- `elmos-observability-slo`

## 14. 失败与恢复

- 错误分类为 configuration、build、adapter、protocol、runtime、policy、capacity、permission、replay、unsupported 和 internal。
- 控制命令失败不得自动重复有副作用操作；只读查询可按策略安全重试。
- 断线恢复前验证 session lease、revision、adapter/runtime version 和权限仍有效。
- 取消或超时立即停止新命令，随后执行有界清理并生成 attestation。
- 无法恢复时保留脱敏诊断、审计和 checkpoint，不保留长期 Secret 或无限变量数据。
