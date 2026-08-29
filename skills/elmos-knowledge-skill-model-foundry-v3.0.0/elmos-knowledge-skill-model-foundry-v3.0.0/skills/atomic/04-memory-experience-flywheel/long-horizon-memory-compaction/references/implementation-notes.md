# Implementation Notes

- Skill ID: `long-horizon-memory-compaction`
- Pack: `04-memory-experience-flywheel`
- Kernel: `K4 Memory and Experience Kernel`
- Priority: `P1`
- Capability: 分层压缩长任务历史，保留决策、未决风险、工具结果哈希和恢复锚点。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
