# Implementation Notes

- Skill ID: `capability-dependency-graph`
- Pack: `00-foundation-contracts`
- Kernel: `K0 Cross-Kernel Contracts`
- Priority: `P1`
- Capability: 建立能力依赖图并计算循环依赖、爆炸半径、升级影响和最小发布闭包。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
