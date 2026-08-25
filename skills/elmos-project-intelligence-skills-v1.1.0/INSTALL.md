# 安装与使用

## 环境要求

- Python 3.10+
- 安装脚本本身仅使用 Python 标准库；完整校验建议安装 `scripts/requirements.txt`。
- 目标 Elmos 仓库需可写；安装器不会默认覆盖已有同名技能。

## 安装完整包

```bash
cd elmos-project-intelligence-skills-v1.1.0
python3 scripts/install_skillpack.py \
  --repo /path/to/elmos \
  --target both \
  --profile full
```

安装结果：

```text
/path/to/elmos/
├── .agents/skills/elmos-*/       # Codex
├── .claude/skills/elmos-*/       # Claude Code
└── .elmos/skillpacks/elmos-project-intelligence/
    ├── docs/
    ├── batches/
    ├── schemas/
    ├── contracts/
    ├── templates/
    ├── examples/
    ├── backlog/
    ├── skillpack.yaml
    ├── AGENTS.md
    └── CLAUDE.md
```

## 安装指定 Profile

```bash
# 代码阅读器、导航、讲解和问答
python3 scripts/install_skillpack.py --repo /path/to/elmos --target both --profile reader

# 架构、流程、数据、图表与治理
python3 scripts/install_skillpack.py --repo /path/to/elmos --target both --profile architecture

# 文档、PPT 和报告工厂
python3 scripts/install_skillpack.py --repo /path/to/elmos --target both --profile artifacts

# 生成/转换/翻新联动
python3 scripts/install_skillpack.py --repo /path/to/elmos --target both --profile conversion

# 私有化与企业治理
python3 scripts/install_skillpack.py --repo /path/to/elmos --target both --profile enterprise
```

可用 Profile：`bootstrap`、`reader`、`architecture`、`artifacts`、`debug`、`conversion`、`enterprise`、`full`。

## 仅安装一个 Host

```bash
python3 scripts/install_skillpack.py --repo /path/to/elmos --target codex --profile full
python3 scripts/install_skillpack.py --repo /path/to/elmos --target claude --profile full
```

## 冲突策略

默认遇到同名技能即失败，不会静默覆盖。审阅差异后使用：

```bash
python3 scripts/install_skillpack.py --repo /path/to/elmos --target both --profile full --force
```

安装器先写临时目录，再以目录级替换提交；失败时不会留下半个技能目录。

## 验证

```bash
python3 -m pip install -r scripts/requirements.txt
python3 scripts/validate_skillpack.py
python3 -m unittest discover -s tests -v
```

## Codex 调用示例

```text
$elmos-insight-orchestrator 读取 .elmos/skillpacks/elmos-project-intelligence/batches/BATCH-01-ingestion-and-parsing.md，检查现有实现并完成最小垂直切片、测试和证据。
```

## Claude Code 调用示例

```text
/elmos-online-code-reader 检查当前 Elmos 仓库与模块规格差距，直接实现最高优先级 P0 项并运行测试。
```

## 升级与卸载

- 升级前保存目标仓库当前技能目录或提交 Git。
- 使用 `--force` 升级会替换由本包管理的同名技能，不会删除其他技能。
- 卸载只删除明确的 `elmos-*` 技能目录和 `.elmos/skillpacks/elmos-project-intelligence/`；不要批量删除整个 `.agents/skills` 或 `.claude/skills`。

## 安装在线调试与调试学习 Profile

```bash
python3 scripts/install_skillpack.py \
  --repo /path/to/elmos \
  --target both \
  --profile debug
```

实施入口：

```text
$elmos-insight-orchestrator 读取 batches/BATCH-14-online-debug-and-learning.md，先检查现有在线代码阅读器、执行沙箱和语言工具链，再实现固定 revision 的安全调试闭环。
```
