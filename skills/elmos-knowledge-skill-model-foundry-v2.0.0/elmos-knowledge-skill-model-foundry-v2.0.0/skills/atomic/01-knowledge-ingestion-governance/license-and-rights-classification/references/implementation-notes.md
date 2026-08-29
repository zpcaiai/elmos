# Implementation Notes

- Skill ID: `license-and-rights-classification`
- Pack: `01-knowledge-ingestion-governance`
- Kernel: `K1 Knowledge Fabric`
- Priority: `P0`
- Capability: 识别许可证、客户合同限制、训练许可、再分发权限和归属义务。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
