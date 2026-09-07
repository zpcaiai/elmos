# Implementation Notes

- Skill ID: `cross-language-concurrency-memory-model`
- Pack: `15-domain-engineering-packs`
- Kernel: `Domain Packs over K1-K8`
- Priority: `P0`
- Capability: 映射线程、协程、Actor、锁、原子性、所有权和内存可见性。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
