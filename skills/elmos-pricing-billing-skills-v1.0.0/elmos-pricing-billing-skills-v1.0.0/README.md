# Elmos Pricing & Billing Skills Package v1.0.0

面向 Codex、Claude Code 与其他兼容 Open Agent Skills 的**可实施商业级收费系统技能包**。它将已经确定的收费策略固化为：

> **基础订阅 + 预充执行额度/按实际消耗 + 项目封顶价或固定价 + 企业年度合同/BYOK**

内部继续精确记录 Token、缓存、沙箱、测试、存储、网络和第三方成本；对普通用户展示金额、执行额度、费用区间、最大预算、实际结算和机器墙钟 ETA。

## Package scale

- **18 个 Skills**：产品、套餐、账本、计量、估算、报价、项目、订阅、支付、退款、企业、分析、UX、安全、运维、认证和迁移。
- **54 个实施批次**：`B00–B53`。
- **180 条需求**：P0/P1，预置五态追踪表。
- **50 个关键场景**：并发、重放、硬预算、支付、退款、BYOK、迁移、灾备和越权。
- 参考 PostgreSQL DDL、OpenAPI 3.1、AsyncAPI 3.0、JSON Schema、策略 YAML、示例与确定性报价计算器。

## Validate

```bash
cd elmos-pricing-billing-skills-v1.0.0
./validate.sh
```

`validate.sh` 验证技能 frontmatter、名称/目录、依赖 DAG、批次、需求追踪、JSON/YAML、相对引用、脚本权限、SHA-256 和参考报价测试。

**注意**：包验证通过只表示此技能包结构完整，不表示目标 Elmos 仓库已经实现收费系统。

## Install into an Elmos repository

```bash
./install.sh --target /absolute/path/to/elmos --host both
```

可选：

```bash
# 只安装 Codex 项目 Skills
./install.sh --target /path/to/elmos --host codex

# 只安装 Claude Code 项目 Skills
./install.sh --target /path/to/elmos --host claude

# 预览，不写文件
./install.sh --target /path/to/elmos --host both --dry-run

# 有冲突时默认拒绝；确认后才能覆盖
./install.sh --target /path/to/elmos --host both --force
```

安装结果：

```text
<elmos-repo>/
├── .agents/skills/<18 skills>/      # Codex
├── .claude/skills/<18 skills>/      # Claude Code
└── .elmos-billing-kit/              # docs/schemas/policies/manifests/tests/tools
```

安装器不会自动改写目标仓库的 `AGENTS.md` 或 `CLAUDE.md`；可人工审阅 `templates/*.snippet.md` 后合并。

## Start implementation

### Codex

将 `CODEX_IMPLEMENTATION_PROMPT.md` 内容交给 Codex，或直接要求：

```text
Use $elmos-billing-orchestrator. Audit the repository, start at B00, and implement the highest safe batch with executable evidence.
```

### Claude Code

将 `CLAUDE_CODE_IMPLEMENTATION_PROMPT.md` 内容交给 Claude Code，或直接调用：

```text
/elmos-billing-orchestrator audit and implement B00 onward with independent verification.
```

## Recommended implementation order

1. B00–B08：基线、定价、套餐和权益。
2. B09–B16：双分录账本、钱包和不可变用量。
3. B17–B22：P50/P80/P90 估算、机器 ETA、报价和硬预算。
4. B23–B34：项目、订阅、发票、支付、退款和对账。
5. B35–B46：企业/BYOK、毛利、UX、安全和运维。
6. B47–B53：E1–E5 认证、影子、迁移、金丝雀和退役。

## Non-negotiable invariants

- 金额和额度使用整数单位，禁止浮点余额。
- 所有余额变化通过追加式双分录账本；余额投影可重建。
- 每个财务写操作都有租户边界、幂等键、审计和关联 ID。
- 用量事件不可变，重复事件不重复计费，按事件时点费率版本评级。
- 任务必须先估算、报价、接受和预算授权，再执行。
- 达到硬上限前停止新的可计费调用，不允许先超扣后解释。
- Elmos 自主运行机器墙钟 ETA 与人工参考时间严格分离。
- 固定/封顶项目必须冻结仓库、需求、范围和验收；范围变化走 change order。
- 支付事实来自经验证 webhook/API/结算文件，不来自浏览器成功页。
- finalized invoice 和 posted ledger 不可原地修改。
- BYOK 不保存明文密钥；只排除客户自付模型成本，不自动免除平台费。
- 任何‘已实现’声明都必须有 Requirement→source→symbol→test→runtime evidence→commit。

## Important files

| File | Purpose |
|---|---|
| `SKILL_INDEX.md` | 技能路由与依赖 |
| `BATCH_INDEX.md` | 54 批次顺序 |
| `IMPLEMENTATION_CHECKLIST.md` | 全量实施清单 |
| `manifests/requirements.traceability.csv` | 180 条需求证据链 |
| `docs/00-PRODUCT-DECISIONS.md` | 已确定商业规则 |
| `docs/02-ARCHITECTURE.md` | 逻辑架构和信任边界 |
| `schemas/reference-postgres.sql` | 账本、钱包、用量、报价等参考 DDL |
| `schemas/billing.openapi.yaml` | API 合同 |
| `schemas/billing-events.asyncapi.yaml` | 事件合同 |
| `policies/*.yaml` | 价格、计量、预算、退款、BYOK 和迁移策略 |
| `tests/SCENARIO-MATRIX.md` | 50 个场景 |
| `tests/E1-E5-CERTIFICATION.md` | 生产认证 |
| `tools/quote_reference.py` | 可执行报价参考算法 |
| `VALIDATION_REPORT.md` | 本发行包验证说明 |

## Plugin distributions

本发行同时生成：

- 完整实施包：包含安装器、文档、Schema、策略、测试和两个主机 manifest。
- Codex skills-only plugin ZIP：根目录含 `.codex-plugin/plugin.json` 和 `skills/`。
- Claude Code plugin ZIP：根目录含 `.claude-plugin/plugin.json` 和 `skills/`。

## Uninstall

先预览：

```bash
./uninstall.sh --target /path/to/elmos --dry-run
```

确认后：

```bash
./uninstall.sh --target /path/to/elmos --yes
```

卸载器只删除安装 manifest 记录的 Elmos billing skills 与 `.elmos-billing-kit`，不会猜测或删除其他项目文件。
