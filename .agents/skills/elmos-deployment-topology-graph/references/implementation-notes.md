# Implementation Notes

- Skill ID: `deployment-topology-graph`
- Pack: `02-repository-semantic-intelligence`
- Kernel: `K2 Repository Semantic Compiler`
- Priority: `P1`
- Capability: 恢复服务、容器、端口、队列、数据库、网络策略和区域拓扑。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
