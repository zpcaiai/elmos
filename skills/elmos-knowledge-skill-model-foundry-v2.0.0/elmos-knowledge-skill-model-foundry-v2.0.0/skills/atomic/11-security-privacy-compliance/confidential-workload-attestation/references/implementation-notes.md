# Implementation Notes

- Skill ID: `confidential-workload-attestation`
- Pack: `11-security-privacy-compliance`
- Kernel: `Cross-Cutting Trust Plane`
- Priority: `P1`
- Capability: 在需要时验证训练和推理环境、镜像和硬件可信状态。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
