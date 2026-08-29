# Implementation Notes

- Skill ID: `capability-gap-and-unknown-mining`
- Pack: `16-self-evolution-release-engineering`
- Kernel: `Learning Flywheel and Release Kernel`
- Priority: `P1`
- Capability: 从失败、人工接管、低置信、客户需求和未覆盖证据中发现能力缺口。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
