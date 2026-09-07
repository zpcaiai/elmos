# Source Manifest 与吸收策略

**固定日期：** 2026-08-21  
**原则：** 本 Skills Package 是独立产品设计，不复制上游源码；实际复用必须重新核验 LICENSE、NOTICE、安全公告和最新 API。

| 来源 | Pin/日期 | 采用方式 | 吸收精华 | 风险/隔离 |
| --- | --- | --- | --- | --- |
| OpenAI Harness Engineering | published 2026-02-11; accessed 2026-08-21 | design-principles-only | repository-as-system-of-record; short AGENTS map; executable plans; mechanical architecture constraints; worktree-local app and observability; agent review; feedback-loop hardening; continuous cleanup | Practice report, not a reusable SDK or direct benchmark for Elmos. |
| OpenAI Symphony | main@8001b52e3062495a16e520e4ceaf8f9de868c4d0 | specification-inspired-independent-implementation | repo-owned WORKFLOW contract; issue reconciliation; isolated persistent workspaces; bounded concurrency; retries/backoff; host-side tools and credential isolation; proof-of-work; dynamic config reload | Engineering preview; adapters and workflow schemas must be versioned. |
| DeepSeek Harness | master@528c682e061696f5a160f363f236ecbf53cbd006 (dsh 0.1.1-rc.1) | adapter-plus-pattern-adoption | Cordis-style reversible services/events; capability seams; append-only session truth; persistence/replay; typed tool pipeline; continuable subagents; LSP; sandbox; approval; provider isolation | Developer preview and release candidate; no core coupling and no silent capability degradation. |
| HKUDS OpenHarness | main@9b2efd795c6aa09f88b0c257d269a9e518da6ae7 | optional-adapter-plus-pattern-adoption | dry-run readiness; provider profiles; permissions and immutable sensitive-path deny; hooks; compaction; MCP reconnect; resume; swarm; autopilot queue/journal/verification and release policies | Feature breadth must be normalized behind Elmos contracts; verify upstream license and API stability before reuse. |
| OpenCode | dev@62cb3f77bd2b4eb3721f286022066de1abe04432 | adapter-plus-product-pattern-adoption | Build/Plan/Explore/Scout roles; action-resource permissions; Session Core/context epochs; LSP; SKILL discovery; plugin hooks; headless OpenAPI server and multi-client runtime | Fast-moving development branch; consume via generated client and compatibility tests. |
| OpenRouter Go SDK | main@dfc04d2d35068f0f2124281c84ebfb076044cda0 (v0.7.64 examples) | provider-adapter-candidate | typed multi-model/provider API access; streaming; retries; provider/model/analytics/guardrail surfaces | Pin SDK; wrap all generated types behind Elmos Model Gateway contracts. |
| OpenRouter TypeScript SDK | main@45e51899073aeaaec255f3dd0dcdad3f397ebaa9 (v1.2.51) | provider-adapter-candidate | typed request/streaming model; BYOK and provider preferences; generated OpenAPI client patterns | Generated API changes can be frequent; use contract tests and compatibility facade. |
| OpenRouter Python SDK | main@a5ec7ec064a91a47e22b37bdbfffc8774e236c97 (v1.1.71) | provider-adapter-candidate | sync/async resource-safe clients; streaming; web-search/server tools; provider policy; file streaming | Generated API changes can be frequent; use contract tests and compatibility facade. |
| OpenRouter Skills | main@f8fdfb73b85a5e94109577a3aebc260f151a6dac | skill-design-and-evaluation-patterns | decision-tree skills; model resolution confidence; availability gates; benchmark/source attribution; resumable eval state; explicit no-fabrication checks | Use as documentation pattern, not as Elmos product truth; runtime data remains live and provider-specific. |
| OpenRouter TypeScript Agent | main@66d7232d53d9881c5842c77f8bc342314724bf3b | runtime-patterns-and-optional-adapter | multi-round usage accounting; stop conditions; deterministic doom-loop detection; sync/background/deferred tools; universal task control; subagent tools; hooks; approvals; tool-set activation; cache-stable dynamic tool choice | Agent package is beta; pin and conformance-test before production. |

## 四种采用方式

1. `design-principles-only`：只吸收工程方法，不形成运行依赖。
2. `specification-inspired-independent-implementation`：以规范思想设计 Elmos 合同，独立实现。
3. `adapter-plus-pattern-adoption`：通过 P01/P06 Adapter 接入，并吸收可证明的通用模式。
4. `provider-adapter-candidate`：可使用官方 SDK，但必须 Pin、Facade、Contract Tests 和回滚。

## 更新策略

- 每次上游升级先在隔离分支运行 Adapter conformance、Security、Session replay 与核心 Benchmark。
- 预览/RC/dev 分支不自动升级；Critical 安全修复例外，但仍需回归。
- 上游新增能力先进入 experimental capability flag，不直接改变默认行为。
- 上游移除/改义能力必须返回 typed incompatibility，不静默模拟。
