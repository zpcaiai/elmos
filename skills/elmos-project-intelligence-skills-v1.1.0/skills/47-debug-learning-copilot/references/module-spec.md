# 调试学习 Copilot 与互动实验 — Module Specification

## 1. Epic

- **Epic ID**：`EPIC-47`
- **Skill**：`elmos-debug-learning-copilot`
- **批次**：`BATCH-14-online-debug-and-learning`
- **目标**：帮助新开发者通过真实执行理解项目，而不是被动阅读答案；所有讲解必须基于当前 Frame、变量、代码和项目图谱证据。

## 2. 用户价值

把在线调试转化为项目学习过程。用于观察、引导、挑战、自由和对照模式，生成调试任务、逐层提示、变量来源讲解、预测题、测验、知识卡与学习进度。

## 3. 功能需求

| ID | 需求 |
|---|---|
| `REQ-47-01` | 讲解必须区分运行事实、静态推断和教学建议，并链接 Frame/变量/代码证据。 |
| `REQ-47-02` | Challenge 模式在用户 Reveal 前不得把答案写入提示、日志摘要或隐藏 UI 数据。 |
| `REQ-47-03` | 学习任务绑定 revision；相关代码变化后必须标记 stale 并生成重校验任务。 |
| `REQ-47-04` | 复用 Lab 使用合成/脱敏数据，不携带原会话密钥、个人信息或客户数据。 |
| `REQ-47-05` | 学习进度属于用户私有数据，团队只看到授权的汇总和作业结果。 |

## 4. API 触点

- `/api/v1/debug/learning/missions`
- `/api/v1/debug/learning/missions/{missionId}`
- `/api/v1/debug/learning/sessions/{sessionId}/prompts`
- `/api/v1/debug/learning/progress`
- `/api/v1/debug/labs`

所有 API/WS 必须：

- 绑定 `tenant_id`、`project_id`、`revision_id`、`debug_session_id` 和服务端授权上下文；
- 控制命令携带 `command_id`、序列号、幂等/去重语义和能力检查；
- 支持心跳、断线恢复、超时、取消、终止和明确错误码；
- 不在 URL、错误消息、日志或事件中泄露源代码、变量、凭据和跨租户对象；
- 对变量、事件和时间线提供分页、大小上限、截断与脱敏元数据。

## 5. 主要领域实体

- `LearningMission`
- `LearningStep`
- `LearningHint`
- `Assessment`
- `LearnerProgress`
- `KnowledgeCard`
- `DebugLab`

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

- mission completion rate
- evidence-citation correctness
- hint usage distribution
- prediction accuracy improvement
- stale lab rate

## 10. 交付物

- `services/debug-learning`
- `apps/insight-web/src/modules/debug-learning`
- `debug-learning-evaluation-report.md`

## 11. 任务清单

| Task | 标题 | 类型 | 优先级 |
|---|---|---|---|
| `ELMOS-PI-47-T01` | 实现 Observe、Guided、Challenge、Free 和 Compare 五种学习模式及难度分级 | implementation | P1 |
| `ELMOS-PI-47-T02` | 从模块、功能、流程、测试或缺陷生成有前置条件、断点、目标和完成条件的 Learning Mission | implementation | P1 |
| `ELMOS-PI-47-T03` | 解释当前暂停原因、Frame 职责、变量来源、分支条件、下一步候选和可能副作用，并附证据 | implementation | P1 |
| `ELMOS-PI-47-T04` | 实现苏格拉底式提问、执行前预测、分层 Hint 和显式 Reveal，避免直接泄露挑战答案 | implementation | P1 |
| `ELMOS-PI-47-T05` | 实现 Checkpoint、Quiz、Score、Notes、Knowledge Card、进度和角色化学习路径联动 | implementation | P1 |
| `ELMOS-PI-47-T06` | 把已脱敏调试会话发布为可复用 Lab，支持版本绑定、团队分配、评审和 stale 提醒 | implementation | P1 |
| `ELMOS-PI-47-T07` | 实现权限、安全、沙箱和不可信输入防护 | security | P1 |
| `ELMOS-PI-47-T08` | 接入日志、指标、Trace、错误分类、资源计量和审计 | observability | P1 |
| `ELMOS-PI-47-T09` | 建立单元、协议合规、集成、E2E、恢复、安全与性能测试 | testing | P1 |
| `ELMOS-PI-47-T10` | 更新 API、事件、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |

## 12. 验收标准

| ID | 验收标准 |
|---|---|
| `AC-47-01` | 当前 Frame 讲解能引用实际变量、调用栈和代码证据，并正确标记推断。 |
| `AC-47-02` | Challenge 模式在 Reveal 前不会泄漏预期分支、变量答案或修复方案。 |
| `AC-47-03` | 代码变更后受影响 Mission/Lab 自动标记 stale，旧结果仍可审计。 |
| `AC-47-04` | 同一 Lab 可用合成数据重复执行，并获得稳定的学习目标和验收结果。 |
| `AC-47-05` | 学习进度、笔记和评估遵守用户隐私、可访问性和团队权限规则。 |

## 13. 依赖

- `elmos-online-debug-workbench`
- `elmos-code-explanation`
- `elmos-onboarding-learning-path`
- `elmos-project-intelligence-graph`

## 14. 失败与恢复

- 错误分类为 configuration、build、adapter、protocol、runtime、policy、capacity、permission、replay、unsupported 和 internal。
- 控制命令失败不得自动重复有副作用操作；只读查询可按策略安全重试。
- 断线恢复前验证 session lease、revision、adapter/runtime version 和权限仍有效。
- 取消或超时立即停止新命令，随后执行有界清理并生成 attestation。
- 无法恢复时保留脱敏诊断、审计和 checkpoint，不保留长期 Secret 或无限变量数据。
