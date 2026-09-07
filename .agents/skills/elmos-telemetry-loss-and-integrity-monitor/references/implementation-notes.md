# Implementation Notes

- Skill ID: `telemetry-loss-and-integrity-monitor`
- Pack: `12-observability-lineage-finops`
- Kernel: `Cross-Cutting Observability and Economics Plane`
- Priority: `P0`
- Capability: 检测丢失、重复、乱序、篡改和采样偏差，避免错误运营结论。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
