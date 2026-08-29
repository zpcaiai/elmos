# Implementation Notes

- Skill ID: `environment-and-answer-leakage-audit`
- Pack: `08-agentic-training-rl`
- Kernel: `K7 Private Model Foundry / Agent Learning`
- Priority: `P0`
- Capability: 检测测试答案、未来提交、缓存、共享工作区和网络造成的评测泄漏。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
