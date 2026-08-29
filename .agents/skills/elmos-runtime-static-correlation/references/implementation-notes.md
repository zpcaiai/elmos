# Implementation Notes

- Skill ID: `runtime-static-correlation`
- Pack: `02-repository-semantic-intelligence`
- Kernel: `K2 Repository Semantic Compiler`
- Priority: `P1`
- Capability: 把生产 Trace、SQL、异常和性能热点映射回静态语义实体。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
