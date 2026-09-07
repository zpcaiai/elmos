# Implementation Notes

- Skill ID: `knowledge-to-skill-distillation`
- Pack: `16-self-evolution-release-engineering`
- Kernel: `Learning Flywheel and Release Kernel`
- Priority: `P1`
- Capability: 把稳定知识规则转为可执行 Skill，同时保留引用和版本条件。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
