# Implementation Notes

- Skill ID: `api-contract-ingestion`
- Pack: `01-knowledge-ingestion-governance`
- Kernel: `K1 Knowledge Fabric`
- Priority: `P0`
- Capability: 摄取 OpenAPI、AsyncAPI、GraphQL、Proto、IDL 和事件 Schema，生成版本化 API 知识对象。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
