# Implementation Notes

- Skill ID: `source-freshness-and-expiry`
- Pack: `01-knowledge-ingestion-governance`
- Kernel: `K1 Knowledge Fabric`
- Priority: `P0`
- Capability: 跟踪知识有效期、版本适用范围、失效日期、最后验证时间和刷新 SLA。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
