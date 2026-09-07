# Implementation Notes

- Skill ID: `training-cost-energy-estimator`
- Pack: `07-private-model-foundry`
- Kernel: `K7 Private Model Foundry`
- Priority: `P1`
- Capability: 预测并核算 GPU 时、Token、存储、网络、能耗和单能力边际成本。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
