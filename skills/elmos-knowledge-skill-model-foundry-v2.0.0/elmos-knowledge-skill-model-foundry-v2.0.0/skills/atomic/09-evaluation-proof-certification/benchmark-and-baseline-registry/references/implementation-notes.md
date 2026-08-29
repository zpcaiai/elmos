# Implementation Notes

- Skill ID: `benchmark-and-baseline-registry`
- Pack: `09-evaluation-proof-certification`
- Kernel: `K8 Formal Assurance and Evidence`
- Priority: `P0`
- Capability: 管理内部、外部、冻结、实时和客户基准及其可比条件。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
