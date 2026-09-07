# Implementation Notes

- Skill ID: `structure-recovery-and-ocr-fallback`
- Pack: `01-knowledge-ingestion-governance`
- Kernel: `K1 Knowledge Fabric`
- Priority: `P1`
- Capability: 优先结构化解析，在必要时受控启用 OCR，并记录置信度和人工复核点。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
