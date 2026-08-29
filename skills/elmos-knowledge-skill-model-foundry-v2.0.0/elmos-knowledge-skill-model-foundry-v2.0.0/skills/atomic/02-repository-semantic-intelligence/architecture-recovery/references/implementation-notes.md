# Implementation Notes

- Skill ID: `architecture-recovery`
- Pack: `02-repository-semantic-intelligence`
- Kernel: `K2 Repository Semantic Compiler`
- Priority: `P1`
- Capability: 从代码、构建、部署和运行证据恢复模块边界、层次、领域和依赖违规。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
