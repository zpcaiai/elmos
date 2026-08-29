# Implementation Notes

- Skill ID: `skill-dependency-resolver`
- Pack: `05-skill-foundry-runtime`
- Kernel: `K5 Skill Foundry and Runtime`
- Priority: `P0`
- Capability: 解析 Skill、工具、模型、环境和 Schema 依赖，生成可重复执行闭包。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
