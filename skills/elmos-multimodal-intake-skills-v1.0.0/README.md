# Elmos 多模态输入、长上下文与项目包接入 Skills v1.0.0

这是一个可直接交给 Codex 或 Claude Code 执行的生产级 Skills Package，共 **50 个独立 Skill**。它把此前关于 Elmos 的以下需求统一为可实施契约：

- 接受音频、图片、PDF、Word、Markdown、TXT、日志等多模态输入；
- 支持本地文件夹、多个文件夹、ZIP、TAR、TAR.GZ、TGZ、GZIP 项目包；
- 保留目录、页码、段落、时间戳、图片框、代码行和符号等来源证据；
- 当前基线与 Codex 同级长上下文，但能力必须由模型注册表动态发现，禁止散落硬编码；
- 原始项目语料可远大于活动上下文，通过索引、分层地图、结构化压缩、检查点和重新水化持续执行；
- 上传、解析、解压、索引和 Agent 工作流可断点恢复，客户端断线不取消服务端任务；
- 多租户隔离、恶意文件隔离、Prompt Injection 防护、归档炸弹与路径穿越防护；
- 机器执行时间、模型费用、计算成本、来源覆盖和测试证据均可观测、可审计。

## 立即开始

1. 阅读 [`START_HERE.md`](START_HERE.md)。
2. 在现有 Elmos 仓库根目录运行安装脚本：
   ```bash
   bash scripts/install.sh --target /path/to/elmos --both
   ```
3. 让编码 Agent 阅读仓库根目录的 `AGENTS.md` 或 `CLAUDE.md`。
4. 从 `docs/IMPLEMENTATION_ROADMAP.md` 的 Phase 0 开始；不要一次性盲目实现全部 50 项。
5. 每个 Skill 完成前运行：
   ```bash
   python3 scripts/validate_package.py
   ```
6. 使用 `templates/ACCEPTANCE_REPORT.md` 保存真实测试证据。

## 目录

```text
.
├── skills/                     # 唯一规范源，50 个 Skill
├── .agents/skills/             # Codex 仓库级即用镜像
├── .claude/skills/             # Claude Code 仓库级即用镜像
├── docs/                       # 需求、架构、数据模型、API、安全和路线图
├── schemas/                    # 9 个 JSON Schema
├── policies/                   # 文件、归档、上下文、路由和保留策略
├── evals/                      # 触发、功能、安全、长上下文验收
├── scripts/                    # 安装、校验与重打包
├── templates/                  # ExecPlan、ADR、验收报告
├── AGENTS.md                   # Codex 项目总控
├── CLAUDE.md                   # Claude Code 项目总控
├── package.yaml
└── manifest.json
```

## 50 个 Skills 的分组

| 分组 | 编号 | 内容 |
|---|---:|---|
| 多模态接入与理解 | 01–20 | 上传、文件识别、安全沙箱、ASR、OCR、视觉、PDF、Word、统一 IR、来源链、融合、检索 |
| 持久执行、成本、UI 与治理 | 21–28 | 检查点恢复、机器 ETA、成本、可观测、评测、工作台、API/SDK、保留与 Agent 集成 |
| Codex 同级动态长上下文 | 29–40 | 能力注册、预算、计量、排序、压力、结构化压缩、恢复、水化、长期记忆、仓库地图、完整性 |
| 文件夹与归档项目包 | 41–50 | 文件夹树、断点上传、清单、安全解压、炸弹/穿越防御、项目识别、分类、符号索引、增量更新、审查 UI |

完整目录见 [`docs/SKILL_CATALOG.md`](docs/SKILL_CATALOG.md)。

## 关键边界

### 三种容量必须分开

```text
原始语料容量：对象存储与租户配额控制，可远大于模型窗口
活动上下文容量：单次模型调用实际装载内容，由 ModelCapabilitySnapshot 决定
项目长期记忆：索引、图谱、检查点和历史证据，可跨任务长期保存
```

### 不允许静默降级

超过活动上下文时必须显式执行排序、压缩、阶段拆分或重新水化；不得截断开头、忽略后半个压缩包或假装读取了全部仓库。

### 输入阶段绝不执行项目代码

解析 PDF/Office/归档/代码仓库时，不运行宏、PDF JavaScript、`npm install`、`postinstall`、Makefile、Dockerfile、Shell、动态库或任何用户程序。构建和测试必须进入另一个受控执行沙箱。

## 当前长上下文基线

包内将 **1,050,000 tokens 总上下文、128,000 tokens 最大输出**记录为 `2026-08-19` 的 Codex 对齐基线；它仅用于默认配置和兼容测试。生产运行必须通过 `elmos-model-capability-discovery` 建立模型能力快照，并在模型切换或能力变化后重新计算预算。

## 完成定义

任何 Skill 只有在以下条件均满足时才可标记完成：

- 真实实现已接入现有仓库，不是 TODO、Mock 或文档占位；
- 数据迁移、API、事件、权限、幂等、回滚和可观测性齐全；
- 单元、集成、端到端、性能、安全和故障恢复测试按适用范围执行；
- 测试输出、Trace、机器运行时间和成本证据已保存；
- 关键需求和最终结论均可回到原始文件位置；
- 未解决风险和限制被如实记录。
