# Implementation Notes

- Skill ID: `provenance-and-lineage-capture`
- Pack: `01-knowledge-ingestion-governance`
- Kernel: `K1 Knowledge Fabric`
- Priority: `P0`
- Capability: 记录来源 URI、提交、作者、解析器、转换步骤、父子对象和派生链。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
