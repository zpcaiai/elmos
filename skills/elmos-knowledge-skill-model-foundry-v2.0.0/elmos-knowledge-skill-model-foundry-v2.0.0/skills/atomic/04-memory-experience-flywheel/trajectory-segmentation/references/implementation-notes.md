# Implementation Notes

- Skill ID: `trajectory-segmentation`
- Pack: `04-memory-experience-flywheel`
- Kernel: `K4 Memory and Experience Kernel`
- Priority: `P1`
- Capability: 把长轨迹切分为规划、定位、修改、验证、修复和发布等可学习片段。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
