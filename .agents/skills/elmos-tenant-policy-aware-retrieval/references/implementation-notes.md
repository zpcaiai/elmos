# Implementation Notes

- Skill ID: `tenant-policy-aware-retrieval`
- Pack: `03-retrieval-context-engineering`
- Kernel: `K3 Retrieval and Context Kernel`
- Priority: `P0`
- Capability: 在检索前执行租户、项目、角色、地域和敏感级别权限裁剪。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
