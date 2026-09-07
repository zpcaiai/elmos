# Source → Elmos Capability Matrix

| 来源 | 主要落包 | 吸收能力 | 采用边界 |
| --- | --- | --- | --- |
| OpenAI Harness Engineering | P00/P02/P04/P05/P07 | 仓库记录、短地图、机械约束、Agent 自助观测、Review/反馈、垃圾回收 | 直接工程原则 |
| OpenAI Symphony | P00/P01/P04/P05 | WORKFLOW、reconciler、workspace、并发、backoff、host tools、Proof-of-Work、Workpad | 独立实现+可选兼容 |
| DeepSeek Harness | P01/P02/P04/P05 | Cordis、capability seams、event session、tools、subagents、LSP、sandbox、approval | Adapter+SPI 设计 |
| OpenHarness | P00/P01/P04/P05/P06 | readiness、permissions、hooks、compaction、MCP resume、Autopilot、verification policies | 可选 Adapter+模式 |
| OpenCode | P00/P01/P02/P04 | Plan/Build/Explore/Scout、Session Core、permissions、LSP、skills/plugins、headless API | Adapter+产品体验 |
| OpenRouter SDKs | P01/P06 | 类型化多模型 API、streaming、Provider policy、BYOK/ZDR、analytics/usage | Provider Adapter |
| OpenRouter Skills | P00/P05/P06/P07 | decision tree、模型解析、availability gate、benchmark attribution、resumable eval state | Skill/评测模式 |
| OpenRouter TypeScript Agent | P01/P04/P05/P06 | usage/cost、stop/doom loop、async/deferred、task control、subagent、hooks、tool activation | 运行模式/可选 Adapter |
| Elmos 自有能力 | P02/P03/P05/P07 | Semantic IR、Capability Ledger、转换规则、差分验证、证据门、学习飞轮 | 核心护城河，不外包 |

## 为什么不能简单 Fork

- DeepSeek Harness、OpenCode、OpenHarness 都可能快速变化；核心域绑定会放大升级成本。
- 外部 Harness 的完成语义通常面向通用 coding task，不能替代 Elmos 的 capability/equivalence evidence。
- OpenRouter 是模型与 Provider 控制面，不应该成为 Elmos 唯一路由或数据政策事实源。
- Fork 容易把 Elmos 私有领域逻辑塞进上游内部，最终失去可替换性和清晰所有权。

## Elmos 必须自己掌握

Repository Intelligence、Semantic IR、Archetype、Transformation Rule/Emitter、Requirement/Capability Ledger、Differential Runtime、Completion Gate、Evidence Corpus、Rule Promotion。
