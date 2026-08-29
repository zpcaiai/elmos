# Implementation Notes

- Skill ID: `commercial-margin-and-unit-economics`
- Pack: `13-commercial-multitenant-platform`
- Kernel: `Commercial Control Plane`
- Priority: `P0`
- Capability: 计算单任务、单租户、业务线和模型组合的收入、成本与毛利。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
