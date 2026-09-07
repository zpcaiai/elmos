# Implementation Notes

- Skill ID: `spring-legacy-inventory-and-version-graph`
- Pack: `15-domain-engineering-packs`
- Kernel: `Domain Packs over K1-K8`
- Priority: `P0`
- Capability: 识别 Struts、Servlet、Spring、JSP、依赖、容器、Java 版本和混合技术栈。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
