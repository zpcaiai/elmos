# Implementation Notes

- Skill ID: `test-time-search-and-tree-exploration`
- Pack: `08-agentic-training-rl`
- Kernel: `K7 Private Model Foundry / Agent Learning`
- Priority: `P2`
- Capability: 受预算控制地执行分支搜索、回溯和候选修复。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
