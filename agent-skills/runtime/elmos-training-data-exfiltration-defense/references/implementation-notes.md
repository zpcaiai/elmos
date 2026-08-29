# Implementation Notes

- Skill ID: `training-data-exfiltration-defense`
- Pack: `11-security-privacy-compliance`
- Kernel: `Cross-Cutting Trust Plane`
- Priority: `P0`
- Capability: 阻止 Prompt、日志、Trace、Adapter 和输出泄露训练或客户数据。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
