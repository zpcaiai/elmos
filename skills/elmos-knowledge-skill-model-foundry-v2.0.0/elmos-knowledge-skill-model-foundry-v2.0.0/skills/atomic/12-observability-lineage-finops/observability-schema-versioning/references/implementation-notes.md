# Implementation Notes

- Skill ID: `observability-schema-versioning`
- Pack: `12-observability-lineage-finops`
- Kernel: `Cross-Cutting Observability and Economics Plane`
- Priority: `P1`
- Capability: 管理遥测 Schema 演进、采集端兼容和历史查询迁移。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
