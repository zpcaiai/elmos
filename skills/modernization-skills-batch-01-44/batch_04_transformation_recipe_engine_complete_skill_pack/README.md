# Batch 04 Complete Skill Pack

## Batch 4：跨语言语义映射、Transformation Rule DSL 与 Deterministic Recipe Engine

本压缩包是 Batch 04 的完整 Codex 实施规格，包含总纲、逐 Skill 规范、兼容协议、Schema、策略、示例、综合场景、静态校验工具和包内摘要。

## 根目录文件

- `README.md`：使用说明、目录和交付边界。
- `CODEX_IMPLEMENTATION_PROMPT.md`：可直接交给 Codex 的工程实施提示词。
- `SKILL.md`：Batch 总体架构、契约、工作流与认证门禁。
- `SKILL_INDEX.md`：25 个 Skills 索引。
- `BATCH03_COMPATIBILITY.md`：上游 Batch 与本 Batch 的输入、版本、证书和失效兼容性。
- `IMPLEMENTATION_CHECKLIST.md`：分阶段实现与验收清单。
- `VALIDATION_REPORT.md`：本规格包的实际静态验证结果与限制。
- `PACKAGE_MANIFEST.json`：除 Manifest 自身外的逐文件摘要清单。

## 附加目录

```text
skills/       25 个独立 SKILL.md
schemas/      10 个核心 JSON Schema
policies/     默认安全、证据、执行和认证策略
examples/     输入、输出与参考流程示例
tests/        综合场景与禁止性断言
tools/        包结构、Frontmatter、索引与 Schema 静态校验
```

## 使用方法

1. 先阅读 `SKILL.md`，确认本 Batch 的可信边界、输入输出和证书等级。
2. 按 `SKILL_INDEX.md` 的依赖主线实现，不要从局部 Adapter 或 UI 开始。
3. 将本目录放入目标仓库的 `specs/` 或 `skills/`，把 `CODEX_IMPLEMENTATION_PROMPT.md` 作为 Codex 主提示词。
4. 在每个里程碑运行：

```bash
python tools/validate_package.py
```

该脚本只验证**规格包结构与静态一致性**，不证明运行时代码已经实现。

## 首期参考范围

```text
首条 Route Pack：Java 17 / Spring Boot 3 → C# 12 / ASP.NET Core 8
原生适配：OpenRewrite、jscodeshift/TS AST、Roslyn、Clang/LLVM
正确性等级：C0 Text Patch → C6 Proof-backed Property
```

## 本包明确不证明

- 目标工程已生成或可构建。
- 所有业务行为已等价。
- Agent 生成过程具有确定性。
- 局部形式证明覆盖整个系统。
- 生产数据库切换已执行或批准。
