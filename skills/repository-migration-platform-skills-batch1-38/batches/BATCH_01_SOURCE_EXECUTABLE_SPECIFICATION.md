# Batch 01：Migration Constitution与Source Executable Specification

## Goal

冻结唯一Source基线，恢复仓库、构建、运行、配置、依赖、业务能力与已知失败，形成后续迁移不可变输入。

## Inputs

- Source repository或不可变快照；
- 构建/测试命令；
- 运行与部署信息；
- 业务与合规约束；

## Outputs

- Repository snapshot；
- Source executable specification；
- Project fingerprint；
- Dependency/build/runtime graphs；
- Baseline evidence；

## Execution Flow

1. 发现仓库与模块；
2. 冻结Commit、依赖和工具链；
3. 运行原始Build/Test并保留既有失败；
4. 恢复运行时、配置、数据和外部依赖；
5. 生成可执行规格与迁移Manifest；

## Verification

- 快照可重复；
- Clean checkout可重建基线；
- 未知项显式登记；
- 既有失败不可被误判为迁移回归；

## Stop Conditions

- Snapshot不完整；
- 关键构建流程未知；
- 动态行为无证据且影响关键语义；

## Gate

`B01 Source Baseline Gate`

## Installable Skill

`agent-skills/runtime/b01-source-executable-specification/SKILL.md`
