# Implementation Notes

- Skill ID: `customer-success-quality-signals`
- Pack: `13-commercial-multitenant-platform`
- Kernel: `Commercial Control Plane`
- Priority: `P1`
- Capability: 识别采用、失败、复核负担、节省时间和续费风险，但不越权采集内容。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
