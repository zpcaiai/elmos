# Implementation Notes

- Skill ID: `experiment-proposal-and-causal-analysis`
- Pack: `16-self-evolution-release-engineering`
- Kernel: `Learning Flywheel and Release Kernel`
- Priority: `P2`
- Capability: 自动提出消融与对照实验，估计改动的因果收益而非相关性。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
