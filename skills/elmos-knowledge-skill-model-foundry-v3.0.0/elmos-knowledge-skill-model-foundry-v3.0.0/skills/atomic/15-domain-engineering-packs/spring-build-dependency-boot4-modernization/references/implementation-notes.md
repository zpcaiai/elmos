# Implementation Notes

- Skill ID: `spring-build-dependency-boot4-modernization`
- Pack: `15-domain-engineering-packs`
- Kernel: `Domain Packs over K1-K8`
- Priority: `P0`
- Capability: 升级构建、依赖、Jakarta 命名空间、容器和 Spring Boot 4 配置。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
