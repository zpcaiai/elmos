# Implementation Notes

- Skill ID: `capability-taxonomy-governance`
- Pack: `00-foundation-contracts`
- Kernel: `K0 Cross-Kernel Contracts`
- Priority: `P0`
- Capability: 统一定义能力域、Skill 粒度、风险等级、成熟度、依赖和所有权，防止能力重复与边界漂移。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
