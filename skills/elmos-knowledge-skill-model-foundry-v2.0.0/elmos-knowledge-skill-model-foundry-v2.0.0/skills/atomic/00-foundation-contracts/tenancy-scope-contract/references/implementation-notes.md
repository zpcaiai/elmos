# Implementation Notes

- Skill ID: `tenancy-scope-contract`
- Pack: `00-foundation-contracts`
- Kernel: `K0 Cross-Kernel Contracts`
- Priority: `P0`
- Capability: 明确平台、组织、租户、项目、仓库、分支、任务和用户各级数据与能力作用域。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
