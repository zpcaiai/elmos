---
name: elmos-architecture-documentation
description: 从统一图谱和证据生成项目概览、架构、模块、流程、API、数据、安全、部署、测试、运维、ADR、尽调和迁移文档。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: artifacts
  title_zh: 架构与项目文档生成
  batch: BATCH-06-documents-presentations-reports
  owner: elmos-project-intelligence
---

# 架构与项目文档生成

## 目标

建立多文档、可引用、可增量更新、可人工维护的项目知识体系。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- Project Intelligence Graph
- Evidence Graph
- 模板/受众/语言
- 已有文档与锁定内容

## 必须输出

- Markdown/DOCX/PDF/HTML 文档集
- 文档索引
- claim/evidence map
- staleness report

## 执行流程

1. 选择文档类型、受众、深度和模板。
2. 生成事实大纲并验证覆盖与证据。
3. 生成正文、图表引用、表格、风险和未知项。
4. 为关键 claim 建立证据链接。
5. 与已有文档执行段落级三方合并。
6. 导出格式并生成可访问性、链接和一致性检查。

## 实施要求

- 默认生成项目概览、业务能力、系统架构、模块目录、流程、API、数据、安全、部署、可观测、测试、开发、运维、风险、技术债和路线图。
- 支持中文、英文、双语。
- 每个章节绑定 revision 和 generator version。
- 事实、推断、未知、建议采用明确标识。
- 支持 docs-as-code 和 PR。

## 安全与可信度约束

- 不得把建议描述成当前实现。
- 不得覆盖人工锁定段落。
- 生成文档不能包含未授权代码片段或秘密。
- 引用失效必须阻断“已验证”状态。

## 依赖技能

- `elmos-evidence-provenance`
- `elmos-diagram-rendering`

## 预期交付物

- `docs/generated/`
- `document-manifest.json`

## 完成定义

- [ ] 文档关键 claim 证据覆盖率达到阈值。
- [ ] 内部链接和代码深链有效。
- [ ] 代码变更只更新受影响章节。
- [ ] 人工内容在再生成后保留。
- [ ] 导出 Markdown/DOCX/PDF 的结构一致。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
