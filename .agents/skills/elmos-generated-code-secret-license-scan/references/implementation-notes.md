# Implementation Notes

- Skill ID: `generated-code-secret-license-scan`
- Pack: `11-security-privacy-compliance`
- Kernel: `Cross-Cutting Trust Plane`
- Priority: `P0`
- Capability: 对生成代码、配置、依赖和文档执行秘密、许可证与版权检查。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
