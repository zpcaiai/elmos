# Implementation Notes

- Skill ID: `redteam-blueteam-learning-loop`
- Pack: `14-human-governance-operations`
- Kernel: `Human Assurance Plane`
- Priority: `P1`
- Capability: 将攻击发现、修复、验证和新测试纳入持续改进。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
