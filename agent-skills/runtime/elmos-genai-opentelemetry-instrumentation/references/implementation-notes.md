# Implementation Notes

- Skill ID: `genai-opentelemetry-instrumentation`
- Pack: `12-observability-lineage-finops`
- Kernel: `Cross-Cutting Observability and Economics Plane`
- Priority: `P0`
- Capability: 为模型、Agent、Tool、MCP、检索和记忆输出统一 Trace、Metric 和 Event。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
