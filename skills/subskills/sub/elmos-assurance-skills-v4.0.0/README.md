# Elmos Assurance & Ethen Independent Audit — Skills Package v4.0.0

**交付日期：2026-09-09 · 交付类型：工业实现契约 + Agent Skills + 可执行参考内核 + 验收规范。**

这不是已部署的 Elmos 产品，不是客户项目 E5 证书，也不是第三方认可/法定认证。本包自己的检查通过，只能说明本包相应文件与参考实现通过了列明的检查。真实仓库改造、数据库/框架原生运行、Lean 内核校验和 Ethen 真实签署必须分别记录证据；未运行项保持 `NOT_RUN`。

## 目标

把四条业务线统一接入可验证的软件交付闭环：

`需求/源仓库 → 接口发现与契约 → 覆盖义务 → 独立测试生成 → 构建 → 冒烟 → 全功能回归 → 差分/性质/变异 → 形式化义务 → 证据封存 → Ethen 审计 → K8 签署 → 持续复验/撤销`。

业务线保持：多语言项目生成、SQL/SQL routine 转换、Spring 老项目现代化、仓库级跨语言转换。认证能力是共享横切扩展，不新增第五条业务线；按既有设计约定不增加原 16 条 canonical routes，接入时仍须先核验真实仓库现状。包版本 v4 不代表将 Elmos Harness v3 整体升级或覆盖。

## 本包最重要的纠偏

1. “全覆盖”只能指**已批准范围内、具有明确分母的覆盖义务全部满足**，不承诺枚举任意输入/全部线程调度。
2. `PASS/FAIL/INCONCLUSIVE` 是判定；`NOT_RUN/RUNNING/TIMED_OUT` 是执行事实，不能混成成功率。
3. 旧系统行为是兼容性证据，不自动高于已批准需求和安全不变量；旧漏洞不应机械保留。
4. Lean 证明的是形式化命题。命题/假设/模型到源码的映射不成立，不能给项目背书。
5. Ethen 默认是一项**需真实身份配置的审计职责**，可由人、机构或独立系统承担。另一个模型不自动获得组织独立性、资格或签署权限。
6. 正式签署留在既有 K8 边界；Builder、Repair、模型、被测仓库永远拿不到签名私钥。
7. 证据绑定 source/target/build/contract/policy/environment/toolchain/tests/data/comparator/rules；更改其中任一受影响项必须失效传播或重跑。
8. 控制平面记录可幂等提交；跨外部系统不宣称无条件 exactly-once。超时后的支付/消息/部署先对账，后重试。

## 快速使用

在解压目录运行：

```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements-reference.txt
python scripts/validate_package.py
python -m pytest -q
python scripts/demo_reference.py
```

`demo_reference.py` 只运行隔离的演示，输出明确的 `DEMO_ONLY_NOT_A_CERTIFICATE`，没有生产签署功能。
`validation/VALIDATION_REPORT.md` 记录本次环境实测范围；依赖文件是本次参考环境的精确版本，不代替生产依赖安全审批与带哈希锁定。

### 接入现有 Elmos 仓库

```bash
# 先预览，再安装。把路径替换为真实 Elmos 根目录。
python scripts/install_skills.py --repo /absolute/path/to/elmos --agent codex
python scripts/install_skills.py --repo /absolute/path/to/elmos --agent codex --apply
```

安装器默认只计划，不覆盖已有 skill，不改用户 AGENTS.md，不执行仓库代码，不安装服务。
Codex 入口安装至 `.agents/skills/`；Claude Code 可选 `--agent claude` 安装至 `.claude/skills/`。
完整包复制到 `.elmos/assurance-package-v4.0.0/`，skill 中参考路径指向该位置。安装后按 `CODEX_START_HERE.md` 执行。

## 阅读顺序

`CODEX_START_HERE.md` → `docs/00-architecture.md` → `docs/01-contracts-and-states.md` → `docs/02-testing-and-metrics.md` → 对应 `domain-packs/*/DOMAIN.md` → `docs/03-ethen-trust.md` → `docs/04-formal-assurance.md` → `roadmap/implementation-batches.yaml`。

每个技能包含 `SKILL.md / manifest.yaml / implementation.yaml / acceptance.yaml / runbook.md`。不要一次把所有技能塞入模型上下文；由 master 按依赖和当前批次加载。

## 包内可执行范围

参考代码执行：输入模式校验、严格 JSON 摘要、测试覆盖义务计算、冒烟集合选择、类型化行比较、证据签名验证/过期/撤销检查、阻断式门禁、租约 fencing 与幂等提交的本地模型、已知缺陷的反例测试。

需要在真实 Elmos 中实现：生产 API/UI、可靠工作流/消息系统、原生语言与数据库适配器、原生回归执行器、Lean 独立复核、真实身份/KMS、商用部署、客户验收。不要把参考内核中的测试信任根接入生产。

## 既有架构兼容

保留 Elmos-owned Router、`ModelExecutionPlan`、`VerifiedSecurityContext`、`CapabilityLease`、结果拦截/提交、executor fencing；LiteLLM/Direct API/OpenRouter 均为可替换执行通道。Ethen 的模型调用也受自己的预算与数据策略约束，不复用 Builder 的记忆、凭据、测试隐藏集或签署权。

本包提供显式 `elmos.assurance/v4` gate profile。与旧 E0–E5 的映射必须经迁移记录批准；不静默重解释历史证书。详见 `docs/06-compatibility.md`。

## 交付索引

- 34个Skills，每个5文件；102个模块原生验收定义。
- 四条业务线分别提供Domain Pack、workflow、Golden Route和6项关键原生验收，共24项。
- 15份JSON Schema与15个明确标注SYNTHETIC的示例；14个控制平面HTTP操作定义。
- `contracts/ASSERTION_AND_NATIVE_RUNNER_CONTRACT.md`：可执行断言IR、wire schema绑定及受控runner计划。
- `migrations/`：12表PostgreSQL参考迁移、RLS/fencing/append-only/outbox与回滚实施约束；原生执行NOT_RUN。
- `formal/`：候选Lean/TLA模型、声明边界及禁止伪造PROVED的检查入口。
- `reference/`和`tests/`：独立可运行参考代码与针对错误放行路径的测试。
- `validation/`：本次实际命令、JUnit、结构检查、演示和边界说明。
- `PACKAGE_CONTENTS.sha256`：包内文件完整性清单，不是外部审计签名或产品认证。

安装后修改`.elmos/assurance-package-v4.0.0/`中的文件会使原始校验和失效，这是预期的。先保存原包作为基线，再把真正实现代码提交到既有Elmos模块；新版本重新生成独立证据与清单，不修改历史证明来追求绿灯。
