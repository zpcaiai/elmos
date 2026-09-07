# Implementation Notes

- Skill ID: `self-play-task-and-test-generation`
- Pack: `08-agentic-training-rl`
- Kernel: `K7 Private Model Foundry / Agent Learning`
- Priority: `P2`
- Capability: 让任务生成器、Coder 和 Tester 协同产生更难且可验证的课程。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
