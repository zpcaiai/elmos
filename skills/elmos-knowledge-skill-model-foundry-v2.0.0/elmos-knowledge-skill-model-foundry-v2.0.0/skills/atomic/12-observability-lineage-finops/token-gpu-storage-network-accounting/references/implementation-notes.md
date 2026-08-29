# Implementation Notes

- Skill ID: `token-gpu-storage-network-accounting`
- Pack: `12-observability-lineage-finops`
- Kernel: `Cross-Cutting Observability and Economics Plane`
- Priority: `P0`
- Capability: 核算输入输出 Token、缓存、GPU 秒、存储、网络和第三方工具费用。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
