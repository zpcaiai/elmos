# Implementation Notes

- Skill ID: `support-diagnostic-bundle`
- Pack: `13-commercial-multitenant-platform`
- Kernel: `Commercial Control Plane`
- Priority: `P0`
- Capability: 在不泄露客户秘密的前提下导出版本、Trace、错误、依赖和健康信息。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
