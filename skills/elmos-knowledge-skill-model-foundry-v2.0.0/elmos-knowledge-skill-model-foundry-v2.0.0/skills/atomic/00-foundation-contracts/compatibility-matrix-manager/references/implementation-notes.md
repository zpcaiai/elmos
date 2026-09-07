# Implementation Notes

- Skill ID: `compatibility-matrix-manager`
- Pack: `00-foundation-contracts`
- Kernel: `K0 Cross-Kernel Contracts`
- Priority: `P0`
- Capability: 管理语言、框架、数据库、模型、硬件、驱动、工具和 Skill 的版本兼容矩阵。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
