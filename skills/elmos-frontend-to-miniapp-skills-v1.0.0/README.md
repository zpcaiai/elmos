# Elmos Frontend → MiniApp Skills Package

版本：`1.0.0`  
生成日期：`2026-08-19`  
技能数量：`22`  
任务数量：`40`  
JSON Schema：`14`

这是一个可安装、可验证、可恢复、可审计的 Agent Skills 包，用于指导 Codex 或 Claude Code 在 Elmos 中实现和运行以下转换：

```text
Vue 2/3、React、Flutter、H5、TypeScript/JavaScript、
Taro、uni-app、既有小程序
        ↓
微信小程序、支付宝小程序、抖音小程序、小红书小程序
```

目标输出是可继续开发、可独立编译、可测试、可提交审核的**原生小程序工程**。本包默认禁止以整站 WebView、整页 Canvas 或截图替代原生转换，也禁止静默删除不兼容功能。

> 本包是实现与执行契约，不是已经完成的转换器二进制。它提供 22 个技能、数据契约、能力分类、实施任务、验证脚本和发布门禁，使 Codex/Claude Code 能够在 Elmos 仓库中按一致方法落地代码系统。

## 1. 包内容

```text
.
├── .agents/skills/                 # 22 个 Agent Skills 的唯一源码
├── docs/                           # 架构、路线图、门禁、测试与安全文档
├── schemas/                        # 14 个 Draft 2020-12 JSON Schema
├── fixtures/                       # 与 Schema 一一对应的有效 fixture
├── templates/                      # 转换请求、规则、报告、适配器模板
├── examples/                       # Vue、React、Flutter、多目标示例
├── plans/                          # 里程碑、WBS、风险与发布清单
├── scripts/                        # 安装、验证、哈希、依赖图工具
├── tests/                          # 包结构、Schema、安装卸载等测试
├── AGENTS.md                       # Codex 仓库级引导
├── CLAUDE.md                       # Claude Code 仓库级引导
├── install.sh / install.ps1
├── uninstall.sh / uninstall.ps1
├── verify.sh / verify.ps1
├── skill-manifest.yaml
└── skill-manifest.json
```

## 2. 安装前验证

```bash
cd elmos-frontend-to-miniapp-skills-v1.0.0
python3 -m pip install -r requirements-dev.txt
./verify.sh
```

`verify.sh` 将验证：

- manifest、YAML frontmatter、技能名称与目录一致；
- 22 个技能、40 个唯一任务 ID 和无环依赖图；
- 14 个 JSON Schema 与 14 个 fixture；
- 必需文档、模板和示例；
- secret/私钥模式扫描；
- Codex 与 Claude Code 的安装/卸载 smoke test；
- SHA-256 文件清单。

## 3. 安装到 Elmos 仓库

```bash
./install.sh --project /absolute/path/to/elmos --runtime both
```

可选 runtime：

```bash
./install.sh --project /absolute/path/to/elmos --runtime codex
./install.sh --project /absolute/path/to/elmos --runtime claude
./install.sh --project /absolute/path/to/elmos --runtime both
```

安装位置：

| Runtime | 仓库位置 |
|---|---|
| Codex | `.agents/skills/<skill>/SKILL.md` |
| Claude Code | `.claude/skills/<skill>/SKILL.md` |

`.agents/skills/` 是本包的唯一源码。安装到 Claude Code 时默认复制相同内容，并写入安装清单。不要分别手工维护两份技能。

卸载：

```bash
./uninstall.sh --project /absolute/path/to/elmos --runtime both
```

安装脚本不会覆盖未由本包安装的同名技能，除非显式使用 `--force`；卸载只删除带本包安装标记的目录。

## 4. 使用方式

### Codex

```text
$frontend-to-miniapp-orchestrator
读取 examples/multi-target-all-platforms/conversion-request.yaml，
针对当前仓库生成实施计划和第一阶段代码。
严格执行 docs/ACCEPTANCE-GATES.md，不得静默删除功能。
```

### Claude Code

```text
/frontend-to-miniapp-orchestrator examples/multi-target-all-platforms/conversion-request.yaml
```

也可以直接调用子技能，例如：

```text
$flutter-widget-semantic-reconstructor
$miniapp-privacy-permission-auditor
$miniapp-differential-testing
```

## 5. 默认转换策略

- 输出原生小程序，不以 WebView 为默认方案。
- Flutter 必须经 Dart AST/Widget 语义重建，不做文本替换或整页截图化。
- 所有源节点保留 `source → IR → target` trace。
- 不兼容能力采用 A–E 级分类：
  - A：原生等价
  - B：适配器等价
  - C：需要重构
  - D：需要业务或人工决策
  - E：目标平台当前不能实现
- C/D/E 项必须进入报告，不能生成空实现冒充成功。
- 真实支付、退款、上传、提交审核和正式发布必须经过授权审批。
- 客户端只保存 secret reference，不保存 AppSecret、私钥或 refresh token。

## 6. 推荐实施入口

1. 阅读 `docs/ARCHITECTURE.md`。
2. 按 `docs/FIRST-40-TASKS.md` 建立任务。
3. 先实现 14 个 Schema 与 IR 核心。
4. 先用 `examples/vue3-todo` 打通最小闭环。
5. 再完成 React、Flutter 和四个平台 adapter。
6. 任何“已完成”结论必须由 `miniapp-migration-evidence-reporter` 生成。

## 7. 生产边界

平台 API、账户权限、类目资质、审核规则和官方工具链会变化。本包要求通过版本化 `platform-profile` 与 `capability-registry` 更新，而不是把易变规则散落在生成器中。平台外部条件不可验证时，状态必须是 `blocked` 或 `unknown`，不得推测为成功。

## 8. 归档与完整性

发行包同时提供 ZIP 和 TAR.GZ，并附独立 SHA-256。包内 `CHECKSUMS.sha256` 覆盖除自身之外的所有文件。可使用：

```bash
sha256sum -c CHECKSUMS.sha256
```

macOS 也可使用：

```bash
shasum -a 256 -c CHECKSUMS.sha256
```
