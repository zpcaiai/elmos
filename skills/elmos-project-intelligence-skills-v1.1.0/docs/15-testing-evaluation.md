# 测试与 AI 评测策略

## 1. 测试金字塔

### 单元/属性测试

- Parser、ID、Schema、Graph edge；
- Evidence confidence；
- Rule DSL；
- Cache key/invalidation；
- Artifact merge；
- Diagram profile；
- Cost/ETA model。

### 契约测试

- OpenAPI/AsyncAPI；
- Git/Trace/Model/Graph/Renderer Adapter；
- 事件 Schema；
- Object Store；
- OIDC/RBAC。

### 集成测试

- Repository→Revision→Parse→Graph；
- Graph→Architecture/Flow/Data；
- Evidence→Diagram/Document/PPT；
- Job pause/resume/cancel；
- Git PR 幂等；
- Backup/restore。

### E2E

- 开发者理解陌生项目；
- 架构师发现循环依赖；
- 产品经理生成能力图和流程；
- 安全人员生成敏感 DFD；
- Elmos 转换前后对比；
- 文档/PPT 再生成保护人工内容。

## 2. 黄金仓库矩阵

- Java/Spring；
- Kotlin；
- Python/FastAPI/Django；
- C#/.NET；
- Go；
- Rust；
- C++；
- PHP/Laravel；
- TypeScript/React/Vue/Node；
- Objective-C/Swift；
- Flutter/Dart；
- 多语言 RPC/FFI；
- Monorepo；
- 微服务+消息+多数据库；
- 故意包含反射、动态路由、代码生成和错误配置。

## 3. AI 指标

| 能力 | 指标 |
|---|---|
| 项目问答 | answer correctness、citation correctness、abstention |
| 代码讲解 | fact precision、coverage、risk separation |
| 架构发现 | node/edge precision/recall、aggregation quality |
| 流程发现 | step/branch/state/side-effect recall |
| 功能图 | capability purity、traceability coverage |
| 文档/PPT | claim support、consistency、staleness、format QA |
| 影响分析 | high-recall affected set、path explanation |
| 风险/建议 | evidence quality、actionability、false-positive |

## 4. 安全测试

- 注释/README Prompt Injection；
- 同形 Unicode；
- Zip Slip/Bomb；
- SVG XSS；
- PlantUML include；
- Graph query DoS；
- Cross-tenant ID enumeration；
- Cache poisoning；
- Egress/SSRF；
- Secret in logs/model input；
- Replayed webhook；
- Duplicate PR/usage event。

## 5. 发布门禁

- P0 Story 自动化覆盖；
- 主路径 E2E 通过；
- schema/contract compatibility；
- 性能无超预算回退；
- AI 黄金集无显著回退；
- 高危安全为零；
- 恢复/幂等演练通过；
- 文档/图表/PPT 结构验证通过；
- 证据完整；
- 认证标准达到目标等级。

## Debug 专项测试

- DAP/CDP adapter capability 和协议合规；
- 四个 P0 Runtime 的真实 launch/断点/step/stack/variables/Evaluate/terminate E2E；
- Source Map、断点重定位和 revision 深链；
- WebSocket 断线、乱序、重复消息和 adapter/worker kill；
- 沙箱逃逸、Docker Socket、特权、egress、Secret、跨租户、资源滥用；
- 默认只读 Evaluate 与审批后的副作用表达式；
- Replay 完整性、版本、脱敏、确定性评分和 R0–R3 降级；
- Guided/Challenge 答案泄漏、证据引用、stale Mission 和学习隐私；
- 分布式 Trace/消息因果和 Source/Target 语义差异 fixture。
