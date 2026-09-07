# Implementation Notes

- Skill ID: `model-invocation-observability`
- Pack: `12-observability-lineage-finops`
- Kernel: `Cross-Cutting Observability and Economics Plane`
- Priority: `P0`
- Capability: 记录模型版本、参数、Token、缓存、TTFT、Prefill、Decode、重试和结果。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
