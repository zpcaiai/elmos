# Implementation Notes

- Skill ID: `elmos-trace-semantic-schema`
- Pack: `12-observability-lineage-finops`
- Kernel: `Cross-Cutting Observability and Economics Plane`
- Priority: `P0`
- Capability: 定义 Task、Turn、Environment、Skill、Knowledge、Model、Evidence 和 Cost 属性。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
