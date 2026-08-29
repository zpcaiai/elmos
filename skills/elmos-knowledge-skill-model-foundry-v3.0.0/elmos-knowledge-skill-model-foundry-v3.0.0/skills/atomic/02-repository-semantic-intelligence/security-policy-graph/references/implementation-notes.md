# Implementation Notes

- Skill ID: `security-policy-graph`
- Pack: `02-repository-semantic-intelligence`
- Kernel: `K2 Repository Semantic Compiler`
- Priority: `P0`
- Capability: 关联身份、角色、权限、路由、数据对象、过滤器和安全配置。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
