# 技术决策与 Build/Buy 边界

## ADR-001：先做专用代码阅读工作台，不做完整在线 IDE

**选择**：Vue 3 + Monaco + Elmos 专用右侧证据/架构/流程面板。  
**原因**：P0 价值是阅读、理解、验证和 Artifact 生成，而不是通用开发环境。  
**后续**：需要终端/LSP/调试器时，可接 Theia 或独立 Workspace。

## ADR-002：解析事实优先使用确定性工具

**选择**：Tree-sitter、编译器前端、LSP、Schema 解析；LLM 负责聚合、解释和弱推断。  
**原因**：降低幻觉，提高定位和增量能力。

## ADR-003：统一 Project Intelligence Graph

**选择**：代码、架构、功能、流程、数据、API、安全、测试和证据统一模型。  
**原因**：避免图表、文档、PPT 和问答各自生成不一致事实。

## ADR-004：证据与图谱分离但关联

**选择**：Graph 是可重建投影；Evidence/Claim 是审计核心。  
**原因**：图存储可替换，证据不能因投影重建而丢失。

## ADR-005：Diagram Spec 为图表权威源

**选择**：中立 JSON/YAML Spec，渲染器是适配器。  
**原因**：支持多格式、可编辑、稳定 ID 和增量合并。

## ADR-006：Artifact 追加版本 + 人工 Override

**选择**：自动生成基线、人工 patch、新自动版本三方合并。  
**原因**：解决文档和图表再生成覆盖人工内容的问题。

## ADR-007：长任务使用 Durable Workflow

**选择**：Temporal 或等价可靠工作流。  
**原因**：暂停、恢复、重试、取消、检查点和 Workflow versioning。

## ADR-008：存储职责分离

- PostgreSQL：事实元数据、权限、任务、Artifact、Claim/Audit；
- Object Store：Blob/IR/二进制；
- Graph：可重建关系投影；
- Search：可重建检索投影；
- Redis：短期缓存/租约。

## ADR-009：模型和供应商可替换

- Model Router；
- Graph/Search/Renderer/Git/Trace Adapter；
- Domain Pack 不依赖厂商；
- 支持外部 API、企业专属和本地模型。

## ADR-010：机器 ETA 与人工时间严格分列

**原因**：用户需要知道 Elmos 自身多久能完成分析/生成/转换，不是开发团队需要几个人日。

## ADR-011：在线调试采用 Gateway + Ephemeral Sandbox

**选择**：Monaco Debug UI → 统一 DAP/CDP Gateway → 一次性容器/微型虚拟机 → 版本钉住 Adapter/Target。  
**原因**：避免浏览器直连调试器、避免将任意命令终端引入主产品，并获得能力协商、租户隔离、资源配额、审计和可恢复性。

## ADR-012：回放采用 R0–R3 能力分级

**选择**：事件时间线、输入重放、检查点恢复和原生反向调试分级。  
**原因**：不同语言和运行时差异巨大，统一宣称 Time Travel 会造成错误承诺和不可验证实现。

## ADR-013：生产调试默认使用观测与安全回放

**选择**：生产环境默认不允许 attach/pause；优先 Trace、日志、Metric、Profiling、只读快照和脱敏 Replay。  
**原因**：在线暂停可能造成级联超时、锁持有、消息租约和数据泄漏。
