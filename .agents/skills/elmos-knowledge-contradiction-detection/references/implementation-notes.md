# Implementation Notes

- Skill ID: `knowledge-contradiction-detection`
- Pack: `02-repository-semantic-intelligence`
- Kernel: `K2 Repository Semantic Compiler`
- Priority: `P1`
- Capability: 发现文档、代码、测试、配置与运行事实之间的冲突并定位证据。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
