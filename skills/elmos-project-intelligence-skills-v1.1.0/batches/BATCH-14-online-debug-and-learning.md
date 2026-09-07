# BATCH-14-online-debug-and-learning — 在线调试与调试式项目学习

## 目标

在固定 revision、一次性安全沙箱和能力协商的适配器之上，交付“启动→断点→单步→变量/栈→副作用→讲解/学习→记录/回放→分布式或 Source/Target 对照”的真实闭环。

本批次不接受：只做静态 UI、Mock Adapter、开放任意终端、直接连接生产数据库、无沙箱运行、把日志回放宣传为通用 Time Travel、或未执行真实调试测试。

## 前置条件

- `BATCH-03-code-reader-and-explanation` 已具备固定 revision 的代码阅读、导航与讲解；
- `BATCH-04-architecture-flow-data` 已具备 Trace/流程/API/数据关联；
- `BATCH-07-search-impact-governance-analysis` 的安全与权限规则可调用；
- `BATCH-10-scale-and-observability` 已定义 SLO、Trace 和资源指标；
- `BATCH-12-deployment-and-certification` 已有隔离部署、安全扫描和证据门禁；
- 已准备至少 Java/Kotlin、Python、Node/TypeScript、.NET 四个真实 fixture；
- 已冻结本批次 API、事件、Schema、Runtime Profile 和 Debug Policy 版本。

## Skill 执行顺序

| 顺序 | Skill | 目标 | 直接依赖 |
|---:|---|---|---|
| 1 | `elmos-debug-adapter-gateway` | 统一 DAP/CDP 与能力协商 | 多语言解析、参考架构、可观测性 |
| 2 | `elmos-debug-sandbox-orchestration` | 隔离、可复现的运行与调试环境 | 安全、部署、可观测性 |
| 3 | `elmos-online-debug-workbench` | 浏览器断点、单步、变量、时间线和跨视图联动 | Adapter Gateway、Sandbox、Code Reader |
| 4 | `elmos-debug-learning-copilot` | 引导学习、挑战、讲解、Lab 与进度 | Workbench、Code Explanation、Learning Path |
| 5 | `elmos-debug-record-replay` | R0–R3 记录、检查点、回放和对比 | Gateway、Sandbox、Trace、Cache |
| 6 | `elmos-distributed-debug-correlation` | 跨服务/异步因果和 Source/Target 对照 | Workbench、Replay、Trace、Conversion |

## 实施任务

| Task | Skill | 标题 | 类型 | 优先级 |
|---|---|---|---|---|
| `ELMOS-PI-44-T01` | `elmos-debug-adapter-gateway` | 建立 JVM、Python、.NET、Node/TypeScript、Go、Rust/C++、PHP、Dart/Flutter、Swift/Objective-C 与 Browser 的适配器注册表和版本矩阵 | implementation | P1 |
| `ELMOS-PI-44-T02` | `elmos-debug-adapter-gateway` | 实现 DAP Session Broker、请求/响应序列关联和 WebSocket 双向传输 | implementation | P1 |
| `ELMOS-PI-44-T03` | `elmos-debug-adapter-gateway` | 实现 Browser/CDP Bridge、Source Map 解析与前端源文件 revision 绑定 | implementation | P1 |
| `ELMOS-PI-44-T04` | `elmos-debug-adapter-gateway` | 实现适配器进程生命周期、健康检查、版本钉住、能力协商和优雅关闭 | implementation | P1 |
| `ELMOS-PI-44-T05` | `elmos-debug-adapter-gateway` | 统一 Breakpoint、Thread、Stack、Scope、Variable、Evaluate、Output、Module 和 Termination 模型 | implementation | P1 |
| `ELMOS-PI-44-T06` | `elmos-debug-adapter-gateway` | 实现背压、事件去重、断线重连、懒加载变量分页、超大对象截断和协议错误隔离 | implementation | P1 |
| `ELMOS-PI-44-T07` | `elmos-debug-adapter-gateway` | 实现权限、安全、沙箱和不可信输入防护 | security | P1 |
| `ELMOS-PI-44-T08` | `elmos-debug-adapter-gateway` | 接入日志、指标、Trace、错误分类、资源计量和审计 | observability | P1 |
| `ELMOS-PI-44-T09` | `elmos-debug-adapter-gateway` | 建立单元、协议合规、集成、E2E、恢复、安全与性能测试 | testing | P1 |
| `ELMOS-PI-44-T10` | `elmos-debug-adapter-gateway` | 更新 API、事件、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |
| `ELMOS-PI-45-T01` | `elmos-debug-sandbox-orchestration` | 定义语言/框架 Runtime Profile，并绑定构建命令、启动目标、端口、环境、adapter 和镜像摘要 | implementation | P1 |
| `ELMOS-PI-45-T02` | `elmos-debug-sandbox-orchestration` | 创建非 Root、只读根文件系统、临时可写层、资源配额、进程限制和系统调用隔离的容器或微型虚拟机 | implementation | P1 |
| `ELMOS-PI-45-T03` | `elmos-debug-sandbox-orchestration` | 实现 launch/attach 环境资格策略；生产进程默认不可暂停或附加 | implementation | P1 |
| `ELMOS-PI-45-T04` | `elmos-debug-sandbox-orchestration` | 接入 Secrets Broker、短期凭证、合成/脱敏数据集和默认拒绝的出站网络策略 | implementation | P1 |
| `ELMOS-PI-45-T05` | `elmos-debug-sandbox-orchestration` | 实现 provision→build→launch→heartbeat→terminate→cleanup→attest 全生命周期和超时回收 | implementation | P1 |
| `ELMOS-PI-45-T06` | `elmos-debug-sandbox-orchestration` | 实现表达式/调试控制台策略：默认只读，副作用表达式仅在一次性环境经显式审批后执行 | implementation | P1 |
| `ELMOS-PI-45-T07` | `elmos-debug-sandbox-orchestration` | 实现权限、安全、沙箱和不可信输入防护 | security | P1 |
| `ELMOS-PI-45-T08` | `elmos-debug-sandbox-orchestration` | 接入日志、指标、Trace、错误分类、资源计量和审计 | observability | P1 |
| `ELMOS-PI-45-T09` | `elmos-debug-sandbox-orchestration` | 建立单元、协议合规、集成、E2E、恢复、安全与性能测试 | testing | P1 |
| `ELMOS-PI-45-T10` | `elmos-debug-sandbox-orchestration` | 更新 API、事件、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |
| `ELMOS-PI-46-T01` | `elmos-online-debug-workbench` | 实现创建会话向导：revision、runtime profile、入口/测试/场景、数据集、学习模式和资源预算 | implementation | P1 |
| `ELMOS-PI-46-T02` | `elmos-online-debug-workbench` | 在 Monaco 中实现行断点、条件断点、Logpoint、异常/函数/数据断点的能力感知 UI | implementation | P1 |
| `ELMOS-PI-46-T03` | `elmos-online-debug-workbench` | 实现 Continue、Pause、Step Over/Into/Out、Run to Cursor、Restart 和 Terminate 控制栏 | implementation | P1 |
| `ELMOS-PI-46-T04` | `elmos-online-debug-workbench` | 实现 Thread、Call Stack、Scope、Variable、Watch、Evaluate、Module 和 Breakpoint 面板及懒加载 | implementation | P1 |
| `ELMOS-PI-46-T05` | `elmos-online-debug-workbench` | 实现 Output、Log、HTTP/RPC、SQL、Cache、MQ、File I/O、Lock/Coroutine 与状态差异时间线 | implementation | P1 |
| `ELMOS-PI-46-T06` | `elmos-online-debug-workbench` | 把当前 Frame、调用栈和副作用映射到 Code Graph、架构图、流程图、数据资产、测试和证据 | implementation | P1 |
| `ELMOS-PI-46-T07` | `elmos-online-debug-workbench` | 实现权限、安全、沙箱和不可信输入防护 | security | P1 |
| `ELMOS-PI-46-T08` | `elmos-online-debug-workbench` | 接入日志、指标、Trace、错误分类、资源计量和审计 | observability | P1 |
| `ELMOS-PI-46-T09` | `elmos-online-debug-workbench` | 建立单元、协议合规、集成、E2E、恢复、安全与性能测试 | testing | P1 |
| `ELMOS-PI-46-T10` | `elmos-online-debug-workbench` | 更新 API、事件、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |
| `ELMOS-PI-47-T01` | `elmos-debug-learning-copilot` | 实现 Observe、Guided、Challenge、Free 和 Compare 五种学习模式及难度分级 | implementation | P1 |
| `ELMOS-PI-47-T02` | `elmos-debug-learning-copilot` | 从模块、功能、流程、测试或缺陷生成有前置条件、断点、目标和完成条件的 Learning Mission | implementation | P1 |
| `ELMOS-PI-47-T03` | `elmos-debug-learning-copilot` | 解释当前暂停原因、Frame 职责、变量来源、分支条件、下一步候选和可能副作用，并附证据 | implementation | P1 |
| `ELMOS-PI-47-T04` | `elmos-debug-learning-copilot` | 实现苏格拉底式提问、执行前预测、分层 Hint 和显式 Reveal，避免直接泄露挑战答案 | implementation | P1 |
| `ELMOS-PI-47-T05` | `elmos-debug-learning-copilot` | 实现 Checkpoint、Quiz、Score、Notes、Knowledge Card、进度和角色化学习路径联动 | implementation | P1 |
| `ELMOS-PI-47-T06` | `elmos-debug-learning-copilot` | 把已脱敏调试会话发布为可复用 Lab，支持版本绑定、团队分配、评审和 stale 提醒 | implementation | P1 |
| `ELMOS-PI-47-T07` | `elmos-debug-learning-copilot` | 实现权限、安全、沙箱和不可信输入防护 | security | P1 |
| `ELMOS-PI-47-T08` | `elmos-debug-learning-copilot` | 接入日志、指标、Trace、错误分类、资源计量和审计 | observability | P1 |
| `ELMOS-PI-47-T09` | `elmos-debug-learning-copilot` | 建立单元、协议合规、集成、E2E、恢复、安全与性能测试 | testing | P1 |
| `ELMOS-PI-47-T10` | `elmos-debug-learning-copilot` | 更新 API、事件、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |
| `ELMOS-PI-48-T01` | `elmos-debug-record-replay` | 定义 R0 事件时间线、R1 输入/测试重放、R2 检查点恢复、R3 原生反向调试四级能力矩阵 | implementation | P2 |
| `ELMOS-PI-48-T02` | `elmos-debug-record-replay` | 记录调试命令、事件、Frame、变量差异、输出、副作用、Trace 关联和采样/截断元数据 | implementation | P2 |
| `ELMOS-PI-48-T03` | `elmos-debug-record-replay` | 生成带 manifest、内容哈希、签名、加密、脱敏和保留策略的 Replay Bundle | implementation | P2 |
| `ELMOS-PI-48-T04` | `elmos-debug-record-replay` | 实现测试输入重放、环境快照恢复和可验证的 checkpoint 创建/恢复流程 | implementation | P2 |
| `ELMOS-PI-48-T05` | `elmos-debug-record-replay` | 运行时支持时提供 Reverse Continue/Step；不支持时自动降级到 checkpoint/input replay | implementation | P2 |
| `ELMOS-PI-48-T06` | `elmos-debug-record-replay` | 实现 passing/failing、before/after、source/target 两次运行的状态与副作用时间线比较 | implementation | P2 |
| `ELMOS-PI-48-T07` | `elmos-debug-record-replay` | 实现权限、安全、沙箱和不可信输入防护 | security | P2 |
| `ELMOS-PI-48-T08` | `elmos-debug-record-replay` | 接入日志、指标、Trace、错误分类、资源计量和审计 | observability | P2 |
| `ELMOS-PI-48-T09` | `elmos-debug-record-replay` | 建立单元、协议合规、集成、E2E、恢复、安全与性能测试 | testing | P2 |
| `ELMOS-PI-48-T10` | `elmos-debug-record-replay` | 更新 API、事件、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |
| `ELMOS-PI-49-T01` | `elmos-distributed-debug-correlation` | 贯通 browser interaction、traceparent、request_id、message_id、workflow/task_id 和 debug_session_id | implementation | P2 |
| `ELMOS-PI-49-T02` | `elmos-distributed-debug-correlation` | 构建跨服务、线程、协程、消息、定时任务和数据库事务的因果 Session Graph | implementation | P2 |
| `ELMOS-PI-49-T03` | `elmos-distributed-debug-correlation` | 在非生产测试环境实现受控协同断点、超时预算、服务虚拟化和死锁/级联超时保护 | implementation | P2 |
| `ELMOS-PI-49-T04` | `elmos-distributed-debug-correlation` | 在暂停点周围联动 Span、Log、Metric、SQL、Cache、MQ 和外部调用状态 | implementation | P2 |
| `ELMOS-PI-49-T05` | `elmos-distributed-debug-correlation` | 实现 Source/IR/Target 同场景双运行、关键变量/状态/副作用对齐和语义分歧检测 | implementation | P2 |
| `ELMOS-PI-49-T06` | `elmos-distributed-debug-correlation` | 实现测试失败→Trace→服务→Frame→变量/数据→代码→修复/学习任务的深链 | implementation | P2 |
| `ELMOS-PI-49-T07` | `elmos-distributed-debug-correlation` | 实现权限、安全、沙箱和不可信输入防护 | security | P2 |
| `ELMOS-PI-49-T08` | `elmos-distributed-debug-correlation` | 接入日志、指标、Trace、错误分类、资源计量和审计 | observability | P2 |
| `ELMOS-PI-49-T09` | `elmos-distributed-debug-correlation` | 建立单元、协议合规、集成、E2E、恢复、安全与性能测试 | testing | P2 |
| `ELMOS-PI-49-T10` | `elmos-distributed-debug-correlation` | 更新 API、事件、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |

## 参考架构

```text
Browser Debug Workbench
  ├─ Monaco execution markers / breakpoints
  ├─ Threads / Stack / Variables / Watches
  ├─ Timeline: HTTP / SQL / Cache / MQ / File / Concurrency
  ├─ Architecture / Flow / Data synchronized context
  └─ Learning Copilot / Mission / Assessment
             │ WebSocket + versioned commands/events
             ▼
Debug Session API / Gateway
  ├─ DAP Broker
  ├─ CDP Bridge
  ├─ Capability Registry
  ├─ Policy Decision Point
  └─ Audit / Metering / Redaction
             │ lease + signed runtime profile
             ▼
Debug Session Orchestrator
  ├─ Ephemeral container or microVM
  ├─ Adapter Runner + Target Process
  ├─ Secrets Broker / synthetic data
  ├─ Egress / quota / kill switch
  └─ Cleanup attestation
             │
             ├─ Runtime Trace / Project Intelligence Graph
             ├─ Replay Store / Checkpoints
             └─ Distributed Correlation / Source-Target Compare
```

## 验收场景

| AC | Skill | 验收结果 | 自动化 |
|---|---|---|---|
| `AC-44-01` | `elmos-debug-adapter-gateway` | Java/Kotlin、Python、Node/TypeScript 和 .NET 四类 P0 适配器通过统一合规套件。 | required |
| `AC-44-02` | `elmos-debug-adapter-gateway` | 不受支持的断点、反向执行或内存能力会被明确禁用并显示原因。 | required |
| `AC-44-03` | `elmos-debug-adapter-gateway` | 网络短暂中断后会话能恢复，且不会重复执行调试命令。 | required |
| `AC-44-04` | `elmos-debug-adapter-gateway` | Source Map 能将前端暂停位置准确定位到固定 revision 的源代码。 | preferred |
| `AC-44-05` | `elmos-debug-adapter-gateway` | 畸形、超大或恶意适配器消息被隔离，其他会话不受影响。 | preferred |
| `AC-45-01` | `elmos-debug-sandbox-orchestration` | 跨租户、宿主文件、Docker Socket、特权系统调用和未授权网络访问测试全部 fail closed。 | required |
| `AC-45-02` | `elmos-debug-sandbox-orchestration` | 会话结束后不存在残留进程、端口、凭据或可写工作区。 | required |
| `AC-45-03` | `elmos-debug-sandbox-orchestration` | 未获得 break-glass 授权时生产 attach 请求被拒绝并生成审计事件。 | required |
| `AC-45-04` | `elmos-debug-sandbox-orchestration` | Fork bomb、内存/磁盘耗尽、无限输出和网络滥用被配额与 kill switch 控制。 | preferred |
| `AC-45-05` | `elmos-debug-sandbox-orchestration` | 固定 manifest 的重复启动得到相同工具链、依赖和入口配置。 | preferred |
| `AC-46-01` | `elmos-online-debug-workbench` | 用户可从测试、方法或流程入口启动会话并完成断点、单步、变量查看和终止闭环。 | required |
| `AC-46-02` | `elmos-online-debug-workbench` | 当前 Frame 可准确跳转代码，并同步高亮所属模块、流程步骤和数据副作用。 | required |
| `AC-46-03` | `elmos-online-debug-workbench` | 网络、SQL、缓存、消息和文件副作用按时间排序且标注证据来源。 | required |
| `AC-46-04` | `elmos-online-debug-workbench` | 浏览器重连可恢复只读状态和面板，不重复执行上一条控制命令。 | preferred |
| `AC-46-05` | `elmos-online-debug-workbench` | 权限撤销后会话访问立即失效，敏感变量和本地缓存不可继续查看。 | preferred |
| `AC-47-01` | `elmos-debug-learning-copilot` | 当前 Frame 讲解能引用实际变量、调用栈和代码证据，并正确标记推断。 | required |
| `AC-47-02` | `elmos-debug-learning-copilot` | Challenge 模式在 Reveal 前不会泄漏预期分支、变量答案或修复方案。 | required |
| `AC-47-03` | `elmos-debug-learning-copilot` | 代码变更后受影响 Mission/Lab 自动标记 stale，旧结果仍可审计。 | required |
| `AC-47-04` | `elmos-debug-learning-copilot` | 同一 Lab 可用合成数据重复执行，并获得稳定的学习目标和验收结果。 | preferred |
| `AC-47-05` | `elmos-debug-learning-copilot` | 学习进度、笔记和评估遵守用户隐私、可访问性和团队权限规则。 | preferred |
| `AC-48-01` | `elmos-debug-record-replay` | 不支持原生反向执行的运行时明确降级，UI 和报告不产生误导。 | required |
| `AC-48-02` | `elmos-debug-record-replay` | 固定测试、输入和环境的 R1/R2 重放在定义容差内复现关键状态与输出。 | required |
| `AC-48-03` | `elmos-debug-record-replay` | Replay Bundle 的 Secret/PII 扫描无高危泄漏，字段省略有明确标记。 | required |
| `AC-48-04` | `elmos-debug-record-replay` | 损坏、篡改、过期或版本不兼容的 Bundle 在运行前被拒绝。 | preferred |
| `AC-48-05` | `elmos-debug-record-replay` | 超大调试会话按策略分块与截断，仍可浏览摘要和关键检查点。 | preferred |
| `AC-49-01` | `elmos-distributed-debug-correlation` | 一次前端操作能关联到正确的后端请求、服务、数据库和消息链路。 | required |
| `AC-49-02` | `elmos-distributed-debug-correlation` | 异步链路缺少 propagation 时会显示断点和不确定性，而不是伪造因果边。 | required |
| `AC-49-03` | `elmos-distributed-debug-correlation` | 固定 fixture 的 Source/Target 状态或副作用分歧能被定位到对应 Frame 和映射。 | required |
| `AC-49-04` | `elmos-distributed-debug-correlation` | 暂停单个服务不会造成无限死锁、消息租约泄漏或无界资源占用。 | preferred |
| `AC-49-05` | `elmos-distributed-debug-correlation` | 权限过滤后用户看不到未授权服务名称、日志摘要、变量或拓扑边。 | preferred |

## 安全硬门禁

- [ ] 非 Root、只读根、无 Docker Socket、禁止 privileged、进程/CPU/内存/磁盘/日志/网络限制通过。
- [ ] 默认禁止生产 attach；break-glass 路径具备职责分离、到期、只读优先、自动终止和审计。
- [ ] Evaluate/Watch/Breakpoint condition 无法绕过文件、网络、Secret、租户和数据权限。
- [ ] 浏览器永远不获得仓库、云、数据库或对象存储主凭据。
- [ ] 变量、日志、HTTP、SQL、消息、文件与 Replay Bundle 脱敏/保留测试通过。
- [ ] 权限撤销和租约到期能在目标 SLO 内终止访问与会话。
- [ ] cleanup attestation 证明无残留进程、端口、卷、凭据和 adapter lease。

## 可靠性与恢复门禁

- [ ] Gateway/Adapter/Worker/Browser 任一短暂故障不会重复执行控制命令。
- [ ] 会话、命令和事件使用单调序列与去重 ID；状态机无非法跃迁。
- [ ] 断线后只恢复状态，不重放 continue/step/evaluate 等命令。
- [ ] 超时、取消和崩溃都触发有界清理；清理失败进入隔离队列。
- [ ] Replay Bundle 有完整性、版本、过期、权限和兼容性验证。

## 学习体验门禁

- [ ] 讲解引用当前 Frame、变量、代码和项目图谱证据。
- [ ] Observe/Guided/Challenge/Free/Compare 模式行为差异明确。
- [ ] Challenge Reveal 前无答案泄漏。
- [ ] Mission/Lab 绑定 revision，代码变化后 stale 传播正确。
- [ ] 学习者隐私、键盘可操作性和屏幕阅读器测试通过。

## 退出标准

- [ ] 60 条任务均为 done/waived，并附真实实现、测试与证据。
- [ ] 30 个验收场景全部通过，或存在有期限、责任人明确的 waiver。
- [ ] 至少四个 P0 Runtime 完成真实 E2E；每个记录 adapter/runtime digest。
- [ ] `python3 scripts/validate_skillpack.py --strict-jsonschema` 与测试套件通过。
- [ ] `EXECUTION_REPORT.md` 分列系统 wall-clock ETA/actual、资源成本、人工审核和已知不支持能力。
