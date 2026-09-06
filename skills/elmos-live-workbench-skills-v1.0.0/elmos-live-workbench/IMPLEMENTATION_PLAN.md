# Codex实施计划：从真实闭环开始

## 执行方式

本包不是要求一次性实现28个大模块。根路由读取本文件后，只加载当前批次依赖的内部SKILL。
同批次工作流仍按compiled-contract中的依赖拓扑执行，而不是按文件名排序。
先扫描实际Elmos仓库、读取其AGENTS/权限/架构规范，建立基线差距表；既有实现优先扩展。
任何代码修改都在当前仓库授权分支/worktree进行，不自行部署公网，不添加主凭据，不删除原实现。

所有任务输出：实际代码路径与revision、测试命令与结果、证据ID、失败/未实现列表、
系统wall-clock、token/资源消耗、人工批准需求。没有真实执行记录不能标done。
若当前环境不提供合格沙箱，将隔离执行标blocked并继续可安全验证的源码/契约部分；不降级到宿主shell。

## B0：盘点与契约冻结

盘点Reader、Graph、IR、ConversionMap、Auth、Harness、Session、Queue、Storage、Tracing与认证入口。
确认当前frontend/backend语言与架构，映射每个workflow现有owner，记录冲突。
冻结交付manifest、SourceAnchor、PreviewSession、ReadinessProof、DebugCommand和RuntimeEvent。
将600秒与安全门禁写入宿主测试，定义provider到期/撤权/清理的可观测接口。
退出：contract review通过，不能只生成文档而不生成可运行contract tests。

## B1：Node/Python的真实运行垂直切片

读取不可变源码；实现最小文件树、选区和带revision深链。
生成/转换交付一个小型Web/API项目，选择真实入口与依赖闭包，独立build和业务冒烟。
接入一个合格隔离provider，私有路由、固定600秒计时、所有连接到期关闭、资源清理收据。
先跑单用户，再加租户隔离、账号并发3槽、取消/崩溃/准备超时和越权负测。
退出：至少Node+Python两条路线通过浏览器/API、真实600秒和安全门禁。

## B2：代码教学与真实DAP

接入debugpy和JS DAP；实现capability negotiation、断点绑定、栈/基础变量、单步和终止。
变量句柄按stop_epoch失效；命令ledger、单控制lease、worker generation与恢复行为真实测试。
实现按行/模块教学、分层架构图与执行证据联动，再做一条Observe/Guided/Challenge课程。
将公开任务与隐藏答案分离；不得用动画模拟调试或以模型回答替代实际断点。
退出：浏览器点断点→暂停→显示实际值→单步→解释同revision代码，完整可录制回放。

## B3：JVM/.NET与转换来源教学

JVM至少Java/Spring实际fixture，Kotlin相关能力单独校验；CoreCLR至少ASP.NET/CLI实际fixture。
对齐调试器位置与源码；检查JDT/source maps/PDB/DWARF等真实依赖条件。
消费已有source→IR→target映射，展示一对多/合成/未映射及语义差异。
完成四族runtime资格矩阵、原生进程/DAP/浏览器/600秒/负测结果汇总。
退出：满足P0放行；候选profile不可通过单改JSON状态升级。

## B4：差分教学与练习

同输入双环境运行、语义检查点对齐、首个差异定位、可复现边界反例。
独立worktree编辑、构建/解释/课程/source map失效；R0时间线+R1输入重跑。
加入有界失败修复、角色学习、键盘/屏幕阅读器完整测试、权限一致的导出/保留/删除。
退出：一个真实高价值转换Golden Route可完成来源讲解、反例观察、修复和重新验证。

## B5：专用实验室

Go/Rust/C++/PHP/Flutter Web按收益逐条扩展；Apple/Windows/Android设备走专用平台资源。
只有满足因果与超时保护条件，才加入跨服务协同暂停或R2/R3高级回放。
高级能力不可反向成为基础阅读和600秒预览的发布依赖。

## 发布硬门禁

执行 `scripts/release_gate.py reports/deployment-qualification.json`，报告必须由真实宿主测试产生。
必需surface包括UI、4族DAP、隔离、多租户、真实600秒、截止撤权、清理与证据准确性。
缺失/not_run/unsupported/failed均阻止“全功能P0工作台”发布。
允许单条已资格路线受控发布，但必须另有准确scope的放行报告，不通过删分母伪造全支持。

## 推荐交给Codex的首条指令

> 阅读本包SKILL.md、INTEGRATION.md和IMPLEMENTATION_PLAN.md。先完成B0，逐项核对实际仓库的
> existing/partial/missing/conflict，并产出不覆盖旧内核的集成差距表。然后按依赖顺序实现B1真实垂直切片，
> 运行可执行测试；在合格provider缺失时明确blocked，不在宿主执行不可信仓库。
> 每完成一批提交具体代码、测试和证据，不以创建文件或TODO占位宣称功能完成。
> 明确区分fake-clock参考测试与真实600秒预览；不改写E0–E5，不自签认证。
