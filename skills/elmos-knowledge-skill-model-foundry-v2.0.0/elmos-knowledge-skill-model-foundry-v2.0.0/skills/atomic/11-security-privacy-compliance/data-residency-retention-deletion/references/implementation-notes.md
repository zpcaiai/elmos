# Implementation Notes

- Skill ID: `data-residency-retention-deletion`
- Pack: `11-security-privacy-compliance`
- Kernel: `Cross-Cutting Trust Plane`
- Priority: `P0`
- Capability: 按地域、合同、用途和保留期控制数据位置、归档和删除。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
