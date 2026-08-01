# Precision Migration & Verified Generation Skills

版本：`1.0.0`

这是一个面向 **仓库级后端语言互转、前端跨框架/跨平台互转、数据库精密迁移、失败项目修复、形式化验证、从Skills生成完整项目、影子切流和企业私有化** 的 Codex/Claude Code 通用技能包。

## Package contents

- 44 个 Batch 编排 Skill
- 587 个独立子 Skill
- 1 个全局路由 Orchestrator
- 统一 Behavior Contract、Evidence、Release Gate、Assessment Schema
- 6 个端到端示例工作流
- 安装与完整性校验脚本

## Core principles

1. **模型只生成候选，客观工具拥有否决权。**
2. **没有证据证明正确的行为，默认未验证。**
3. **任何未解释差异，默认阻断发布。**
4. **跨语言方向有向且专用，正向与逆向不合并。**
5. **类型、Effect、State、Observation、Semantic Loss 和 Provenance 全程保留。**
6. **形式证明覆盖受限核心；真实框架与平台行为由双运行、Fuzz、并发、真机和影子流量覆盖。**

## Directory map

```text
precision-migration-skills-batch-01-44/
├── meta/precision-migration-orchestrator/SKILL.md
├── batches/batch-01-.../SKILL.md
│   └── skills/<skill-name>/SKILL.md
├── schemas/
├── docs/
├── examples/
├── catalog.json
├── catalog.csv
├── manifest.json
├── manifest.txt
├── install.py
└── verify_package.py
```

## Installation

将所有独立 Skill 安装到任意技能目录：

```bash
python install.py --target /path/to/skills
```

只安装部分 Batch：

```bash
python install.py --target /path/to/skills --batches 2,3,5,11,28,30,31,41
```

同时安装 44 个 Batch 编排 Skill：

```bash
python install.py --target /path/to/skills --include-batch-orchestrators
```

## Recommended first deployment

个人或小团队优先实现：

- Batch 02：应用现代化评估
- Batch 03：正确率与耗时预测
- Batch 05-07：仓库语义、工具链与沙箱
- Batch 11-13：Transformation Skill、无损转换、候选生成
- Batch 28-32：测试、双运行、失败修复与高级验证
- Batch 41：证据与发布门禁

首个业务闭环建议：

```text
Java 8/11 + Spring Boot 2 + Vue 2
→ Java 21 + Spring Boot 3 + Vue 3
→ API/DB/UI差分
→ 正确性证据
```

数据库闭环建议优先：

```text
Oracle → PostgreSQL
SQL Server → PostgreSQL
MySQL → PostgreSQL
```

## Validation

```bash
python verify_package.py
```

校验内容包括：44个Batch、技能名称唯一、Frontmatter、必需章节、状态词、Manifest和SHA-256摘要。

## Intellectual-property boundary

本包吸收行业公开的优秀设计思想：分阶段现代化评估、可组合Transformation Skill/Recipe、无损语义树、双运行、反例驱动修复和证据门禁。它不包含任何第三方专有实现、源码或内部数据。
