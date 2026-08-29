# Implementation Notes

- Skill ID: `experience-value-scoring`
- Pack: `04-memory-experience-flywheel`
- Kernel: `K4 Memory and Experience Kernel`
- Priority: `P0`
- Capability: 按正确性、稀缺性、泛化性、证据完整度和训练权利评估经验价值。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
