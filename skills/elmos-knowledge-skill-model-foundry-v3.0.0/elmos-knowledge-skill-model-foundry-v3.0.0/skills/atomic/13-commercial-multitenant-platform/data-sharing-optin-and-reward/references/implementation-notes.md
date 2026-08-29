# Implementation Notes

- Skill ID: `data-sharing-optin-and-reward`
- Pack: `13-commercial-multitenant-platform`
- Kernel: `Commercial Control Plane`
- Priority: `P0`
- Capability: 让客户选择是否贡献匿名经验，并记录回报、范围和撤回。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
