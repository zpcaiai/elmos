# 实现路线

此路线描述 Elmos 主仓的实现顺序，不以人工人天作为系统运行 ETA。

## P0-A：可执行底座

- Job/Step/Attempt/Checkpoint/Artifact 数据模型；
- Environment-owned authority、sandbox、lease/fencing；
- repository snapshot；
- Maven/Gradle/Ant baseline runner；
- artifact store；
- package/schema/policy loader；
- wall-clock/cost telemetry。

完成门：可对大型仓库执行可暂停、恢复、取消的只读扫描，断电后继续。

## P0-B：仓库取证

- module/build/runtime topology；
- framework/version fingerprint；
- effective config；
- effective route table；
- dependency/Jakarta compatibility graph；
- Repository Evidence Graph。

完成门：混合仓库 route owner 与部署拓扑可审计，未知项显式。

## P0-C：语义前端

- Struts1 RequestProcessor/ActionForm/Action/Forward；
- Struts2 package/interceptor/ValueStack/Result；
- Servlet descriptor/filter/listener/dispatch；
- JSP/TLD/Tiles；
- binding/state/security/transaction/effects/concurrency；
- Legacy Web Semantic IR。

完成门：代表性 fixture 的 IR 与手工 oracle 一致。

## P0-D：规划与确定性改写

- preserve-first planner；
- Spring Boot 4 target architecture；
- conversion wave；
- compatibility shim；
- AST/symbol/config rewrite；
- Struts1/2/Servlet target generators；
- Jakarta/dependency migration；
- semantic source map/change set。

完成门：样例仓可达到 E2/E3，重跑幂等且可逆。

## P0-E：差分验证和修复

- contract/sequence mining；
- source/target runners；
- observation bus；
- HTTP/view/session/DB/effect/security oracles；
- trace correlation；
- mismatch root cause；
- bounded repair；
- impact regression。

完成门：fixture 中植入的语义差异均可检出，修复不扩散。

## P0-F：生产认证

- E0–E5 gate engine；
- SBOM/security/performance；
- deployment/runbook；
- shadow/canary/rollback；
- evidence bundle；
- Golden Route scorecard。

完成门：至少一个真实授权仓库完成 E4，之后再扩大到商业 Golden Route 矩阵。

## P1

- JSP→Thymeleaf/React/Vue 独立 wave；
- EAR 拆分和云原生部署；
- session modernization；
- JNDI/resource modernization；
- advanced mutation/fault synthesis；
- 多租户组织策略和审批流；
- IDE 中的 evidence/source-map 可视化。

## P2

- 从 Java Legacy Web 泛化到其他 repository conversion domain packs；
- 用 E4/E5 结果训练/检索 validated pattern cache；
- 自动生成迁移架构文档、图、PPT 和审计材料；
- 形式化关键状态机/事务不变量。
