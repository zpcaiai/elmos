# Debug Adapter、Runtime 与能力矩阵

## 1. 设计原则

1. 统一控制协议不等于统一运行时能力。
2. Adapter 的能力必须在会话握手时协商和版本钉住。
3. UI、API、学习任务和营销材料只能引用实际通过合规测试的能力。
4. Attach、Evaluate、Memory、Disassembly、Hot Reload 和 Reverse Debug 采用更严格策略。

## 2. 优先级矩阵

| Runtime | 优先级 | 协议/桥接 | 基础能力 | 高级能力策略 |
|---|---|---|---|---|
| Java/Kotlin JVM | P0 | DAP adapter | launch、非生产 attach、断点、异常、线程、栈、变量、Watch、step | data/method breakpoint、hot swap 按 adapter |
| Python | P0 | DAP adapter | launch、非生产 attach、断点、异常、线程、栈、变量、Watch、step | 子进程/异步与性能按 adapter |
| Node/TypeScript | P0 | DAP adapter | launch、attach、source map、断点、logpoint、栈、变量、step | worker/child process 按 profile |
| .NET/C# | P0 | DAP adapter | launch、非生产 attach、断点、异常、线程、栈、变量、step | hot reload/data breakpoint 按 adapter |
| Browser JS/TS | P0 | CDP bridge | page target、source map、断点、console、network、栈、变量 | DOM/event/XHR breakpoint 按浏览器策略 |
| Go | P1 | DAP adapter | launch、非生产 attach、断点、goroutine、栈、变量、step | data breakpoint 按 adapter |
| Rust/C++ | P1 | DAP/native bridge | launch、非生产 attach、线程、栈、变量、step | memory/disassembly 可选，表达式更严格 |
| PHP | P1 | DAP adapter | request launch、断点、异常、栈、变量、step | 长连接/队列按 profile |
| Dart/Flutter | P1 | DAP adapter | launch、isolate、断点、栈、变量、step | hot reload 可选且不可掩盖状态漂移 |
| Swift/Objective-C | P2 | DAP/native bridge | 受控 launch、线程、断点、栈、变量、step | 依赖宿主/签名/模拟器，单独资源池 |

## 3. Capability 枚举

基础：`launch`、`attach_nonprod`、`line_breakpoints`、`conditional_breakpoints`、`exception_breakpoints`、`threads`、`stack`、`scopes`、`variables`、`evaluate_readonly`、`step`、`output`。

可选：`logpoints`、`function_breakpoints`、`data_breakpoints`、`instruction_breakpoints`、`memory`、`disassembly`、`hot_reload`、`restart_frame`、`native_reverse_debug`、`multi_process`、`coroutine_view`。

## 4. Adapter 合规套件

- 握手、能力声明和版本；
- launch/terminate/cleanup；
- 断点验证与移动；
- pause/continue/step 序列；
- threads/stack/scopes/variables 分页；
- Evaluate 策略与副作用测试；
- Source Map 与固定 revision；
- 输出、异常、进程退出；
- 断线重连和消息去重；
- 畸形消息、超大变量、adapter 崩溃；
- Secret/PII 脱敏；
- 资源和超时门禁。

## 5. 生产调试政策

生产环境默认只开放：Trace、日志、Metric、Profiling、只读快照和脱敏 Replay 导入。直接 attach/pause 必须由企业显式启用，并至少具备双人审批、严格时间窗、只读/无副作用表达式、禁止全链路暂停、资源保护、自动终止和全量审计。默认产品套餐不得把生产 attach 作为常规功能。
