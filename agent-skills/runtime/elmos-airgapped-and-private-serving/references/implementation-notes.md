# Implementation Notes

- Skill ID: `airgapped-and-private-serving`
- Pack: `10-serving-routing-inference`
- Kernel: `K8 Serving and Runtime Control`
- Priority: `P0`
- Capability: 支持离线镜像、私有 Registry、无外网依赖、更新包和本地审计。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
