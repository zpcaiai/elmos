# Batch 05 Complete Skill Pack

## Target Language Lowering、Framework Backend 与 Idiomatic Code Generation

本压缩包是 Batch 5 的完整 Codex 实施规格。它接收 Batch 4 输出的 Transformed CSIR、Target Construction Intent、方向性 Route Pack、语义缺口、Shim、来源映射和验证义务，生成 Java、C#、Node.js/TypeScript、Python、C++、Go、Rust、Vue、React、Flutter 等目标工程。

## 根目录文件

- `README.md`：使用说明、目录和交付边界。
- `CODEX_IMPLEMENTATION_PROMPT.md`：可直接交给 Codex 的工程实现提示词。
- `SKILL.md`：Batch 5 总体架构、契约、工作流和认证标准。
- `SKILL_INDEX.md`：34 个 Skills 索引。
- `BATCH04_COMPATIBILITY.md`：Batch 4 → Batch 5 输入、版本和失效兼容性。
- `IMPLEMENTATION_CHECKLIST.md`：分阶段实现与验收清单。
- `VALIDATION_REPORT.md`：本规格包的实际静态验证结果与限制。
- `PACKAGE_MANIFEST.json`：除 Manifest 自身外的文件摘要清单。

## 附加目录

```text
skills/       34 个独立 SKILL.md
schemas/      核心 JSON Schema
policies/     默认目标惯用性、Agent、Shim、构建和再生成策略
examples/     三条参考路线与目标 Profile 示例
tests/        综合场景与验证约束
tools/        包结构与 Schema 静态校验脚本
```

## 使用方法

### 1. 阅读总纲

先阅读 `SKILL.md`，确定 TTIR、目标 Profile、后端协议、可信边界和 Generation Certificate 等级。

### 2. 选择实现顺序

按 `SKILL_INDEX.md` 中的依赖主线实现。不要先从某个语言 Printer 开始；必须先完成 Target Profile、TTIR、Pass Manager 与 Backend SDK。

### 3. 交给 Codex

将本目录放入目标仓库的设计或规格目录，然后将 `CODEX_IMPLEMENTATION_PROMPT.md` 作为主提示词。Codex 必须读取根目录全部文件及相关子 Skill，分阶段实现并在每阶段运行测试。

### 4. 运行静态校验

```bash
python tools/validate_package.py
```

该校验只验证技能包结构、Frontmatter、索引与 JSON Schema 可解析性，不代表 Batch 5 运行时代码已经实现或通过真实语言工具链。

## 首期产品路线建议

```text
Reference Route A：Java 17 / Spring Boot 3
→ C# 12 / ASP.NET Core 8 / EF Core 8 / PostgreSQL

Reference Route B：Vue 3 / TypeScript / Vite
→ React / TypeScript / Vite

Reference Route C：Vue 3 / TypeScript / Vite
→ Flutter / Dart / Riverpod
```

## 本包明确不证明

- 目标系统与源系统业务行为等价；
- 生产性能等价；
- 数据迁移已成功；
- 生产切换已批准；
- 所有语言与框架组合都已完成生产认证。

这些能力由后续测试恢复、差分验证、Dual Run、性能、安全、数据切换和生产认证 Batch 完成。
