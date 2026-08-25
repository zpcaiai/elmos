---
name: elmos-presentation-generation
description: 生成管理层项目介绍、技术评审、新人培训、售前、技术尽调、迁移翻新和生产认证 PPTX。用于可编辑、品牌化、可增量更新的演示材料。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: artifacts
  title_zh: 项目介绍与技术汇报 PPT 生成
  batch: BATCH-06-documents-presentations-reports
  owner: elmos-project-intelligence
---

# 项目介绍与技术汇报 PPT 生成

## 目标

把统一项目事实、图表和指标转为针对受众的可编辑演示文稿，并保留证据和演讲备注。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- 项目图谱与证据
- 演示场景/受众
- 品牌模板
- 页数/语言/保留页面

## 必须输出

- PPTX
- PDF preview
- slide manifest
- speaker notes
- evidence map

## 执行流程

1. 选择演示类型并建立答案优先的故事线。
2. 为每页定义目的、主结论、证据、图表和备注。
3. 生成或复用架构图、流程图和指标图。
4. 使用模板引擎创建可编辑文本、形状、表格和图表。
5. 检查溢出、可读性、引用、品牌和敏感信息。
6. 按 slide stable ID 支持增量更新和人工锁定。

## 实施要求

- 支持 10/20/30 页与管理/技术/产品/客户受众。
- 使用 PPTX 原生可编辑对象；复杂图至少保留 SVG 和源 Spec。
- 每页记录 revision、claim IDs、generator version。
- 可生成中文、英文、双语和演讲备注。
- 支持企业 Logo、字体替代、页脚和保密级别。

## 安全与可信度约束

- 不得用无法核验的市场或项目数字填充。
- 不得把代码截图作为所有技术内容的默认形式。
- 不得覆盖用户锁定页或手工备注。
- 敏感架构和代码必须服从导出策略。

## 依赖技能

- `elmos-architecture-documentation`
- `elmos-diagram-rendering`

## 预期交付物

- `presentations/`
- `slide-manifest.json`
- `pptx-validation-report.md`

## 完成定义

- [ ] 所有文本无溢出且核心页面可编辑。
- [ ] 关键结论有 evidence map。
- [ ] 相同模板重生成能保留锁定页。
- [ ] 不同受众故事线显著不同。
- [ ] PPTX 可被主流 Office 软件正常打开。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
