# Elmos Online Debug Learning Studio — 详细需求

## 1. 产品定位

在线调试是在线代码阅读器的受控运行扩展，不是向浏览器开放任意 Shell 或生产主机。它把“看代码”升级为：

```text
选择固定 Revision / 测试 / 流程
→ 创建一次性沙箱
→ 启动或附加调试目标
→ 断点 / 单步 / 栈 / 变量 / Watch
→ 观察 HTTP、SQL、缓存、消息、文件和并发副作用
→ 联动代码、架构、流程、数据和测试
→ AI 引导提问与项目讲解
→ 保存检查点 / 回放 / 调试实验
→ 生成学习进度、故障证据或 Source/Target 差异
```

## 2. 用户场景

### 新人理解陌生项目

- 从“用户下单”业务流程启动一个已准备好的 Debug Lab；
- Elmos 自动在 Controller、领域服务、Repository 和事件发布点放置教学断点；
- 用户先预测下一步，再单步观察调用栈、变量和数据库副作用；
- 当前 Frame 同步高亮架构组件、流程节点和数据表；
- 完成后生成知识卡和下一条学习路线。

### 开发者定位缺陷

- 从失败测试、异常日志或 Trace 打开在线调试；
- 对比 passing/failing 两次运行；
- 找到变量第一次分歧、错误分支和外部副作用；
- 将会话保存为脱敏 Replay Bundle，附到 Issue/PR。

### Elmos 转换验证

- 使用相同 fixture 同时运行 Source 与 Target；
- 对齐函数/Frame、关键变量、SQL、事件和响应；
- 标记 Semantic IR 映射后的首个行为分歧；
- 生成自动修复任务与行为等价证据。

## 3. 调试模式

| 模式 | 目标 | AI 行为 | 用户控制 |
|---|---|---|---|
| Observe | 快速观看一次执行 | 讲解当前状态和副作用 | 可暂停、下钻 |
| Guided | 按步骤学习项目 | 提问、提示、解释、检查目标 | 完整单步 |
| Challenge | 训练代码理解和排障 | 只给分层 Hint，Reveal 前不泄漏答案 | 完整单步与作答 |
| Free | 普通开发调试 | 按需解释，不主动打断 | 完整授权范围内控制 |
| Compare | 比较两次运行或 Source/Target | 对齐状态并解释首个分歧 | 同步导航与差异筛选 |

## 4. 调试功能

### 会话创建

- 项目、仓库、分支、Commit/Revision；
- Runtime Profile、工具链镜像、依赖锁；
- 入口：测试、Main、API、CLI、Cron、Consumer、页面交互、已保存场景；
- 数据：合成数据、脱敏快照、fixture、虚拟外部服务；
- 模式、时长、CPU/内存/磁盘/网络预算；
- adapter capabilities 与不支持能力说明。

### 控制与断点

- Continue、Pause、Step Over/Into/Out、Run to Cursor、Restart、Terminate；
- 行断点、条件断点、Logpoint、异常断点；
- 函数、数据、指令、协程/线程断点只在 adapter 支持时出现；
- Hit Count、断点组、临时断点和按学习步骤启用；
- 断点绑定 revision/symbol/source-map，代码变化后重新验证。

### 状态面板

- Threads/Goroutines/Isolates/Coroutines；
- Call Stack、Scopes、Variables、Watches、Modules；
- 对象按需展开，显示类型、来源、脱敏、截断与更新时间；
- 表达式默认只读；有副作用表达式必须显式审批且仅限一次性环境；
- 当前变量可追溯到参数、配置、数据库、消息或上一个 Frame。

### 副作用时间线

- HTTP/RPC 请求与响应摘要；
- SQL、事务、锁和受影响行摘要；
- Cache read/write/invalidate；
- MQ publish/consume/ack/retry/DLQ；
- 文件、对象存储和外部 API；
- 线程、协程、Future、锁等待；
- 所有事件带时间、来源、Trace、Frame、证据和脱敏状态。

## 5. 调试学习

### 实时讲解

每次暂停可以回答：

- 为什么停在这里？
- 当前方法在业务流程中负责什么？
- 这几个变量从哪里来，哪些已经改变？
- 下一条可能走哪个分支，依据是什么？
- 继续执行会产生什么数据库、缓存、消息或网络副作用？
- 当前代码与架构文档、流程图、测试的对应关系是什么？

输出必须标记 `Observed`、`Confirmed`、`Inferred`、`Unknown` 和 `Teaching Tip`。

### Learning Mission

每个任务包含：

- revision、目标角色、难度、前置知识；
- 业务目标、入口、数据集和安全策略；
- 预设断点、步骤、预测题、Hint 和 Reveal；
- 完成条件、评分 Rubric 和证据；
- 版本 stale 规则；
- 可复用 Lab 的脱敏与审批状态。

## 6. 回放能力等级

- **R0 Event Timeline**：回看事件和状态摘要，不表示能够反向执行；
- **R1 Input/Test Replay**：在重建环境中重新运行同一输入或测试；
- **R2 Checkpoint Restore**：恢复 Elmos 管理的工作区/运行时检查点；
- **R3 Native Reverse Debug**：仅对明确支持且通过合规测试的运行时开放。

任何 UI、文档和营销材料都必须显示实际等级，禁止把 R0/R1 描述为通用 Time Travel Debugging。

## 7. 分布式调试

- 前端事件→API→服务→数据库/缓存→消息→后台任务；
- 通过 traceparent/request_id/message_id/workflow_id 等显式上下文建立因果边；
- 缺少上下文时允许低置信度时间推断，但必须标记；
- 受控测试环境可使用有界协同暂停，设置租约、自动恢复和死锁保护；
- 生产故障优先使用 Trace、日志、快照和安全回放，不暂停全链路；
- 支持 Source/Target 相同 fixture 的状态和副作用对照。

## 8. 安全基线

- 每会话独立容器或微型虚拟机；非 Root、只读根、无 Docker Socket、资源/进程限制；
- 默认禁止外网，只允许依赖仓库或虚拟服务白名单；
- Secret Broker 发放短期凭证，服务端脱敏后才能进入浏览器；
- 默认使用合成/脱敏数据，不直连生产数据库；
- Debug Console 不是 Shell；Evaluate 默认只读；
- 生产 attach 默认拒绝，break-glass 需双人审批、到期、只读优先和审计；
- 权限撤销、租约到期或浏览器断开超过策略阈值后自动终止；
- Replay Bundle 加密、签名、限时下载和保留期删除。

## 9. 语言与能力策略

- P0：JVM、Python、Node/TypeScript、.NET、Browser JavaScript；
- P1：Go、Rust/C++、PHP、Dart/Flutter；
- P2：Swift/Objective-C 和受控远程/Kubernetes 调试；
- 每个 adapter 在运行时上报能力，平台按能力协商展示 UI；
- Function/Data/Memory/Disassembly/Hot Reload/Reverse Debug 均为可选能力，不能统一承诺。

## 10. 数据模型

核心实体包括：`DebugSession`、`DebugTarget`、`RuntimeProfile`、`DebugAdapter`、`AdapterCapability`、`Breakpoint`、`DebugCommand`、`ThreadState`、`StackFrame`、`VariableSnapshot`、`RuntimeSideEffect`、`DebugCheckpoint`、`ReplayBundle`、`LearningMission`、`LearnerProgress` 和 `SemanticDivergence`。

所有实体绑定 tenant/project/revision、runtime/adapter/policy version、actor、生命周期、审计和 retention。

## 11. SLO 建议

| 指标 | 初始目标 |
|---|---|
| 已缓存 Runtime Profile 创建到 ready p95 | ≤ 30 s |
| 常规调试命令往返 p95 | ≤ 300 ms（不含目标程序自身停顿） |
| 变量首屏展开 p95 | ≤ 500 ms |
| 浏览器重连恢复 p95 | ≤ 3 s |
| 会话终止到资源清理 p95 | ≤ 60 s |
| 权限撤销到访问失效 p95 | ≤ 5 s |
| Adapter 合规 P0 | 100% 必选能力通过 |
| Replay Secret/PII 高危泄漏 | 0 |

目标应按部署环境、语言和资源层级校准，而不是作为无条件承诺。

## 12. 完成定义

- 至少四个 P0 运行时完成真实 E2E；
- 浏览器能启动、断点、单步、查看变量/栈/副作用并安全终止；
- 调试讲解引用真实 Frame、变量和项目证据；
- 沙箱逃逸、跨租户、网络、Secret、资源滥用和生产 attach 测试通过；
- R0–R3 能力不混淆；
- 断线、adapter/worker 崩溃和 cleanup 失败有恢复/隔离；
- Source/Target 对照能定位至少一种真实语义差异；
- 任务、AC、Schema、API/事件和追踪矩阵全部通过技能包校验。
