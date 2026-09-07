# Implementation Notes

- Skill ID: `counterexample-guided-repair`
- Pack: `09-evaluation-proof-certification`
- Kernel: `K8 Formal Assurance and Evidence`
- Priority: `P1`
- Capability: 把验证器产生的最小反例反馈给修复模型并限制修改范围。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
