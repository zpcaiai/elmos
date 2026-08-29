# Implementation Notes

- Skill ID: `repair-pattern-extraction`
- Pack: `04-memory-experience-flywheel`
- Kernel: `K4 Memory and Experience Kernel`
- Priority: `P1`
- Capability: 学习失败签名到补丁策略、验证步骤和适用条件的映射。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
