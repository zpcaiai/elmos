# Implementation Notes

- Skill ID: `api-abi-and-schema-compatibility`
- Pack: `09-evaluation-proof-certification`
- Kernel: `K8 Formal Assurance and Evidence`
- Priority: `P0`
- Capability: 验证 API、ABI、消息、序列化、数据库 Schema 和迁移兼容性。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
