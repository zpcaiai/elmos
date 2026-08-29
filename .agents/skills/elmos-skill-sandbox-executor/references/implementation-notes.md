# Implementation Notes

- Skill ID: `skill-sandbox-executor`
- Pack: `05-skill-foundry-runtime`
- Kernel: `K5 Skill Foundry and Runtime`
- Priority: `P0`
- Capability: 在受限环境中执行脚本与工具，施加文件、网络、CPU、内存和时间限制。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
