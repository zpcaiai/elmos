# Implementation Notes

- Skill ID: `preference-optimization-orchestrator`
- Pack: `07-private-model-foundry`
- Kernel: `K7 Private Model Foundry`
- Priority: `P1`
- Capability: 支持 DPO、KTO、ORPO、SimPO 等策略并依据数据与目标选择。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
