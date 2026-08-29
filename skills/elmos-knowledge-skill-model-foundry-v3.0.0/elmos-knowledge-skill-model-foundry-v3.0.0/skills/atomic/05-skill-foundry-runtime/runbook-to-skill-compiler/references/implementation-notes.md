# Implementation Notes

- Skill ID: `runbook-to-skill-compiler`
- Pack: `05-skill-foundry-runtime`
- Kernel: `K5 Skill Foundry and Runtime`
- Priority: `P1`
- Capability: 把人工 Runbook 转换为带条件、分支、工具、证据和异常处理的工作流。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
