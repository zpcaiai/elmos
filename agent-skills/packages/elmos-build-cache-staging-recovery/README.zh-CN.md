# ELMOS 构建缓存、生成文件暂存与断点恢复 Skills 包

版本：**1.0.0**（2026-08-19）

本包已经把你补充的 **“项目生成过程中的文件暂存”** 纳入核心架构，不是简单使用 `/tmp`，而是将每个生成文件纳入可恢复、可校验、可追踪的状态机。

## 已覆盖的核心能力

- 项目快照、Merkle Tree、文件级/符号级增量失效；
- CAS 内容寻址存储、Action Cache、本地/远程多级缓存；
- AST、Semantic IR、映射计划、生成代码、Patch、编译结果、测试结果、自动修复结果和认证证据的中间状态持久化；
- 生成文件完整状态：`RESERVED → WRITING → SEALED → CAS_PROMOTED → TREE_INCLUDED → PUBLISHED`；
- 同文件系统临时写入、摘要计算、`fsync`、原子重命名；
- 完整项目目录组装完成后再原子发布，避免逐文件覆盖导致半成品暴露；
- Worker 宕机、服务重启、网络中断、磁盘写满后的检查点恢复；
- 用户修改保护、生成冲突、三方合并和回滚；
- 本地 SQLite + 文件 CAS；生产 PostgreSQL + S3/MinIO；Redis 仅用于 Lease、热索引和协调；
- 缓存污染防护、租户隔离、来源证明、密钥扫描、GC、可观测性、混沌测试和生产认证。

## 包结构

```text
agent-skills/runtime/<skill-name>/SKILL.md
```

共有 **24 个可执行 Skill**，并包含：

- `manifest.json`：依赖 DAG；
- `AGENTS.md`：Codex/Claude Code 执行规则；
- 完整架构规范；
- JSON Schema、PostgreSQL SQL、OpenAPI、状态机；
- 本地和生产配置模板；
- 可运行参考实现和自动化测试；
- 生产验收矩阵；
- Codex/Claude Code 安装脚本；
- 包完整性校验脚本。

## 安装

```bash
./install.sh --all
```

只安装到 Codex：

```bash
./install.sh --codex
```

只安装到 Claude Code：

```bash
./install.sh --claude
```

## 校验

```bash
./validate.sh
```

执行代码实现前，应依次读取 `AGENTS.md`、`manifest.json`、主规范和所选 Skill 的依赖项。没有测试、故障恢复验证和新鲜证据时，不得宣称完成。
