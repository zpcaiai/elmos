# Implementation Notes

- Skill ID: `progressive-skill-disclosure`
- Pack: `05-skill-foundry-runtime`
- Kernel: `K5 Skill Foundry and Runtime`
- Priority: `P0`
- Capability: 只暴露 Meta-Skill 目录，激活后再加载原子 Skill 和必要资源。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
