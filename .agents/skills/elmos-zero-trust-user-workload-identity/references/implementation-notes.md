# Implementation Notes

- Skill ID: `zero-trust-user-workload-identity`
- Pack: `11-security-privacy-compliance`
- Kernel: `Cross-Cutting Trust Plane`
- Priority: `P0`
- Capability: 对用户、Agent、服务、工具、训练作业和部署实例实施可验证身份。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
