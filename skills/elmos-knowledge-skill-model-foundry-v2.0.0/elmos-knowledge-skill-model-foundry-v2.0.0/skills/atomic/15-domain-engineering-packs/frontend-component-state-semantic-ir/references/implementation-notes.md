# Implementation Notes

- Skill ID: `frontend-component-state-semantic-ir`
- Pack: `15-domain-engineering-packs`
- Kernel: `Domain Packs over K1-K8`
- Priority: `P0`
- Capability: 抽取组件、Props、状态、响应式、生命周期、样式和可复用逻辑。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
