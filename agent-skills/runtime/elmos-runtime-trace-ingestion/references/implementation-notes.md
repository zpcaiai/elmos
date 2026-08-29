# Implementation Notes

- Skill ID: `runtime-trace-ingestion`
- Pack: `01-knowledge-ingestion-governance`
- Kernel: `K1 Knowledge Fabric`
- Priority: `P1`
- Capability: 接入 Trace、Metric、Log、Profile、SQL 与消息链路，并与静态代码实体关联。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
