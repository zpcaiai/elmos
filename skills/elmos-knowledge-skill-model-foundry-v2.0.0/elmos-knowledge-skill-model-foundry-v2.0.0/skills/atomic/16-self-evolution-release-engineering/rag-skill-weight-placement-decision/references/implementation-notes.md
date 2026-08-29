# Implementation Notes

- Skill ID: `rag-skill-weight-placement-decision`
- Pack: `16-self-evolution-release-engineering`
- Kernel: `Learning Flywheel and Release Kernel`
- Priority: `P1`
- Capability: 按变化频率、精确性、权限、成本和泛化性决定能力落点。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
