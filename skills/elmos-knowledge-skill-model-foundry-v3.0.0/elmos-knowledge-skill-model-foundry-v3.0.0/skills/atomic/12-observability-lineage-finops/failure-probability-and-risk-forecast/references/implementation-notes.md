# Implementation Notes

- Skill ID: `failure-probability-and-risk-forecast`
- Pack: `12-observability-lineage-finops`
- Kernel: `Cross-Cutting Observability and Economics Plane`
- Priority: `P1`
- Capability: 预测任务节点失败、超预算、需人工和无法认证的概率。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
