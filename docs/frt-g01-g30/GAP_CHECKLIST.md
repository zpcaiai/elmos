# FRT G01–G30 代码与证据缺口清单

> 当前代码审计：2026-08-05。权威实现为 `frt-runtime.ts`、
> `frt-semantic-handlers.ts`、`directional-route.ts`、六类 source IR
> extractor、外部证据协议和保守门禁。目录存在或 manifest 存在本身不算功能完成。

## 结论

- 472/472 Skills 已注册到 23 个明确的 typed handler kind。
- 472/472 Skills 均有独立 capability key 与内容寻址 execution-contract digest；契约覆盖
  精确输入/输出、五个 API、六个 Surface、证据角色、obligation 与外部权限边界。
- 23/23 handler kind 均有可执行代码；旧的 metadata-only fallback 已删除，未知
  handler 直接失败。
- 其中 18 个原缺失 kind 由 `frt-semantic-handlers.ts` 实现：输入契约、领域算法、
  typed artifact、blocking Finding 和外部证据边界均为代码路径，不是状态回显。
- 30/30 有向前端路径均能从 Vue 2、Vue 3、React、微信小程序、ArkUI、Flutter
  源码提取当前受支持的 typed UI Interaction IR，并生成六类目标工程。未建模语义
  必须以注册 typed gap 阻断。
- 2,832 个 surface manifest 绑定到共享实现；这是共享 Runtime 架构，不是 2,832
  份重复代码。每个 runtime/test manifest 均指向实际 handler 与对应测试文件。
- 所有 Run 按 organization/tenant/workspace/project/account/environment/release 精确隔离；
  同租户跨 Workspace 读取、变更与幂等碰撞均失败关闭。
- 本地代码门禁可达到 `READY_FOR_EXTERNAL_GATE`。生产仍为 `NOT_CERTIFIED`。

## 23 类 handler 的代码状态

| handler kind | Skills | 主要可执行产物 |
|---|---:|---|
| `governance` | 12 | 不变量、模块边界、provenance、release decision |
| `estate_discovery` | 13 | workspace inventory、framework/toolchain discovery |
| `semantic_ir` | 13 | UI semantic graph、typed IR |
| `typed_contract` | 13 | 六类 source contract extraction |
| `migration_planning` | 13 | exact target migration plan |
| `source_generation` | 13 | 六类 target profile、架构与 skeleton files |
| `build_toolchain` | 15 | typed nodes、file allocation、import graph、typed holes、diagnostics、repair convergence |
| `test_automation` | 13 | component contract 与生成测试 |
| `delivery_pipeline` | 14 | state/effect/lifecycle/async/cleanup/cancellation map |
| `design_system` | 14 | route/form/API/storage/permission application-boundary contracts |
| `mobile_client` | 14 | UI/token/i18n/RTL/a11y/motion semantic baseline |
| `cross_platform` | 14 | platform capability matrix、bridge/security gaps |
| `directional_route` | 30 | source-derived typed IR 与 target project generation |
| `route_orchestration` | 31 | 30-route registry、corpus selection、equivalence gate fragment |
| `compatibility` | 15 | pack dependency、overlay、conflict resolution |
| `advanced_verification` | 19 | proof obligations、tool adapters、counterexample IR、evidence graph |
| `runtime_operations` | 24 | registry、durable jobs、RBAC、quota、deployment plan |
| `product_workflow` | 85 | requirement trace、state machine、Saga compensation、journey coverage |
| `administration` | 20 | capability/role/operation matrix、audit、bulk rollback |
| `performance_capacity` | 20 | workload、p95/p99/error/throughput、budget violations |
| `resilience_dr` | 20 | bounded failure scenarios、RTO/RPO、restore/DR plan |
| `security_privacy` | 23 | attack surface、zero-tolerance findings、privacy/SBOM gaps |
| `production_readiness` | 24 | SLO、runbook、alert、canary/rollback、production readiness model |

合计：472 Skills，23 kinds。所有新领域 handler 都会在缺少必需 typed input 时返回
blocking `FRT_HANDLER_INPUT_REQUIRED`；`EXECUTE` 不再把空输入排成 runner 成功候选。

## 已关闭的旧缺口

- `EXECUTE` 的 durable lifecycle、claim、lease、heartbeat、complete、retry、cancel、
  audit、restart recovery 已实现。
- 每个原始 Skill 声明的 create/read/verify/findings/evidence 五个 Skill-scoped HTTP
  操作已实现；VERIFY 绑定终态 subject run、result digest 与 source snapshot。
- Runner completion、artifact reference、evidence candidate、独立 verifier 签名、记录级
  撤销、producer/verifier key-role separation 已实现。
- Vue 2、Vue 3、React、小程序、ArkUI、Flutter source extractor 已接入所有 30 路；
  声明 IR 与源码不一致会阻断。
- React、Vue 2、Vue 3、小程序、Flutter 本地目标工具链通过；Flutter 支持 offline-cache
  与 online cold-cache 两条可复现路径。
- Web Console 的 Next.js/PostCSS/Sharp 生产依赖漏洞已清零；413 请求体拒绝不再并发触发
  `EPIPE`。
- JSON Schema 清单、gate evidence bytes/SHA-256、浏览器矩阵和支持矩阵已同步。
- 当前修订的五类本地浏览器 profile 均通过适用旅程：桌面 Chrome 5/5，桌面 Firefox
  4/4、桌面 WebKit 4/4（两者各有一个只在 Chromium 串行执行的 lifecycle skip），
  Pixel 7 Chromium 2/2、iPhone 15 WebKit 2/2（移动端各有三个预期 desktop-only skip）。
  Firefox 151.0 与 WebKit 26.5 已真实安装、launch，并通过联合非视觉质量检查。
- 外部证据的 prepare、dispatch、collect、DLP、sign、verify、bind 与独立性约束已有
  可执行代码；仓库内容不能选择 shell 命令。
- 外部资格生成器已经产出 15 个精确用例，并执行了严格 preflight：Firefox、WebKit
  桌面/移动、ArkUI/hvigor、独立视觉、人工 AT、物理设备、客户仓库、独立 holdout、
  bounded proof、正式性能、渗透、Chaos/DR、生产观测和客户验收均有固定 adapter、
  证据角色、指标、声明与明确 blocker。当前 3/15 为
  `READY_FOR_AUTHORIZED_EXECUTION`、12/15 为 `BLOCKED_PRECONDITION`；15/15 external
  state 仍为 `NOT_RUN`。
- 15/15 adapter ID 已通过无 fallback 的显式 allowlist 执行本地代码契约；报告与精确
  plan/preflight SHA 绑定。当前环境结果为 3 个 `READY_FOR_LOCAL_EXECUTION`、1 个
  `BLOCKED_TOOLCHAIN` 加 11 个 `REQUIRES_EXTERNAL_AUTHORITY`，不会提升任何 external state。
- 9 类外部 campaign 均有 closed typed parameters：未知字段、任意命令、scope 扩大、
  plan/case/adapter 漂移、secret value 和降低安全/独立性下限都会在授权准备前失败。
- 28 个本地完整性测试已执行：typed parameters、全部 9 个外部检查的签名正/负记录、
  15 用例计划/preflight/adapter 与 observation 重算防篡改、iOS 物理设备证据最小化，
  以及 repository gate 的摘要、路径、字节数、签名和独立性约束。
  这些是代码验证，不是外部执行证据。

## 仍然不能由本地代码伪造的状态

以下不是 typed handler 缺失，而是需要指定环境、组织或人员真正执行并签名：

- ArkUI DevEco/hvigor 原生构建；
- 独立视觉基线批准、人工辅助技术会话、物理设备人工验收；
- 真实客户仓库和物理隔离 holdout；
- qualified Lean/SMT/model-checker 运行与独立 proof review；
- 代表性性能/容量、Chaos/HA/DR、渗透/隐私/供应链执行；
- 生产观测、值班/回滚演练、客户验收和独立认证 authority。

这些检查继续保持 `NOT_RUN`，并使最终状态保持 `NOT_CERTIFIED`。外部 Runner
返回 `PASSED` 也必须同时满足：预授权、exact profile/source digest、所需 raw evidence
roles、零容忍阈值、executor/verifier/approver 三方 Ed25519 签名、跨组织独立性、时序、
有效期、撤销和 DLP 校验。

全局生产边界同时固定为 `production_operation_authorized=false`；本地测试、候选截图、
模拟浏览器、设备清单候选或签名测试 fixture 都不能改变该值。

## 验收命令

```bash
cd engines/frontend-client-engine && pnpm test
python3 tooling/integrate_frt_g01_g30.py --check
python3 scripts/frt/validate_frt_platform.py
python3 scripts/frt/external_qualification.py generate
python3 scripts/frt/external_qualification.py preflight
python3 scripts/frt/external_qualification.py exercise
python3 scripts/frt/external_qualification.py check
python3 scripts/frt/external_qualification.py check-preflight
python3 scripts/frt/external_qualification.py check-execution
(cd scripts/frt && python3 -m unittest test_external_campaign_parameters.py test_external_evidence.py test_external_qualification.py test_run_frt_gate.py -v)
python3 scripts/batch32/run_client_gate.py client-packs/frt-g01-g30-platform
```

只有 `scripts/frt/run_frt_gate.py` 可产生 FRT repository decision；只有 Batch 32 gate
可决定 client pack readiness。两者都不能替代外部 authority 或生产认证。
