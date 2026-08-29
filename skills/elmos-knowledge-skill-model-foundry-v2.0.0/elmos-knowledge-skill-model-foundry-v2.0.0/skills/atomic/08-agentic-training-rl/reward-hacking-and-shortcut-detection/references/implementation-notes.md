# Implementation Notes

- Skill ID: `reward-hacking-and-shortcut-detection`
- Pack: `08-agentic-training-rl`
- Kernel: `K7 Private Model Foundry / Agent Learning`
- Priority: `P0`
- Capability: 识别删除测试、硬编码答案、扩大权限、绕过验证和污染环境等投机行为。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
