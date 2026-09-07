# Implementation Notes

- Skill ID: `semantic-memory-distiller`
- Pack: `04-memory-experience-flywheel`
- Kernel: `K4 Memory and Experience Kernel`
- Priority: `P0`
- Capability: 从多次经历中提炼稳定事实、规则和模式，并保留来源覆盖范围。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
