# Implementation Notes

- Skill ID: `tenant-export-delete-and-offboarding`
- Pack: `13-commercial-multitenant-platform`
- Kernel: `Commercial Control Plane`
- Priority: `P0`
- Capability: 完整导出客户资产、吊销访问、删除数据并提供完成证明。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
