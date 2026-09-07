# 内部流程：有界Agent子流程

输入：已存在的EvidenceContext、host执行网关、预算、lease和验证器；先读SPEC 7–10。

1. 列出确定性与动态节点，判断现有编排是否已满足；简单问答不增加图。
2. 状态仅存refs与局部进度，固定graph/schema/prompt/tool版本；每次模型调用仅一份费用账本。
3. 先接tutor和bounded_repair。设置round/tool/model/deadline预算及重复错误无进展停止。
4. 教学interrupt恢复前鉴权；过期preview只可回看课程，不能恢复旧执行资源。
5. 修复先规则后模型最小候选，host批准精确base revision/intent digest。
6. stable action_id、唯一retry owner；unknown先对账，fenced旧结果不能提交。
7. LangGraph原生持久恢复必须跨新进程/worker测试；内存Saver或自制状态机不算原生资格。
8. 独立验证决定候选是否合格，禁止改oracle/删失败测试自评成功。
9. 原图版本恢复或明确迁移；冲突写隔离。先只读shadow，再受限候选补丁。
10. 输出NEEDS_INPUT/BLOCKED/NO_PROGRESS/BUDGET_EXHAUSTED等结构化状态，图完成不裁定Run完成。

交付：真实父子流程调用、网关适配、恢复/副作用/撤权/版本测试、预算计量、回滚。
不接受：Agent直接shell/DB、thread_id当权限、checkpoint当time-travel、双重无限重试或自动push。
