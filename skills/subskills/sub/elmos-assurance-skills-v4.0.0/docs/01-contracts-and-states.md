# 契约、状态机、不可变绑定

## 1. RevisionSet

必须绑定：source或原始需求摘要、target source、实际build artifact、contract、scope、policy、toolchain、environment、test suite、fixture/data、comparator、rule set。Git commit不能替代容器/二进制摘要；同一commit在不同依赖和构建脚本下可产生不同产物。
引用格式 `sha256:<lowercase hex>` 或schema规定的裸hex，禁止混用。参考内核使用裸64位hex。

Scope与plan须经独立的控制平面批准。客户端不能通过提交更宽松policy、空obligations、自己的root keys来获得认证。可信验证配置从服务部署/受控policy存储读取，不来自被测repo。

## 2. ContractSnapshot

每条接口具有：稳定ID、协议、方向、版本、来源、路径/操作、schema、前置条件、身份/角色/租户、结果、状态转移、可观察副作用、错误、幂等性、时序、预算、兼容规则和需求关联。

`declared`、`observed`、`inferred`、`approved_normative`分别保存。静态缺失+运行时发现不是自动规范；运行时没观察到也不是不存在。发现算法记录扫描完整性、动态路由/反射盲点、编译条件、插件清单与审批排除。

Approval基于完整snapshot hash，不是基于页面标题。合同更新生成新版本，使受影响tests/proofs/evidence失效。

## 3. 四种正交状态

- 执行：QUEUED / RUNNING / PASSED / FAILED / TIMED_OUT / CANCELLED / INFRA_ERROR / NOT_RUN。
- 验证结论：PASS / FAIL / INCONCLUSIVE。
- 义务：REQUIRED / APPROVED_NOT_APPLICABLE / OPTIONAL；critical不得无审批豁免。
- 证书：DRAFT / ISSUED / SUSPENDED / REVOKED / EXPIRED / SUPERSEDED。

timeout不自动是语义错误。若deadline本身是验收要求，超限可为FAIL；若执行器故障则是INCONCLUSIVE。即使恢复重试PASS，也保留首次失败并判断flake。

## 4. 运行状态机

NEW→SCOPED→CONTRACT_APPROVED→PLANNED→BUILDING→SMOKE→REGRESSION→ADVANCED→SEALED→AUDITING→DECIDED。
失败候选经授权 REPAIRING→新RevisionSet→新run；不能修改SEALED run。
取消通过CANCEL_REQUESTED→CANCELLING→CANCELLED，提升fencing epoch，停止新作业，等待/对账已开始的副作用。
AUDITING后有代码变化必须回到新run，而不是保留原review批准。

## 5. Gate profile `elmos.assurance/v4`

本profile新增，不默默替换历史v3定义。

| level | 本profile必须的证据 |
|---|---|
| E0 | 资产/工具链/构建/环境可重建；完整性 |
| E1 | 已批准接口/需求/风险范围；覆盖分母与Oracle |
| E2 | 启动、依赖与关键业务路径冒烟 |
| E3 | 全部已批准功能/状态/权限/事务/副作用回归 |
| E4 | 适用差分/性质/变形/fuzz/变异/非功能风险门槛 |
| E5 | 风险规定的形式化义务 + Ethen独立审计 + 全部前置证据 + K8授权签署 |

E5不能意味着整个程序都被形式化证明。每张证书另列 formal_claims、model_bound、assumptions与未涵盖属性。仅E0构建通过也不得显示“软件正确”。

## 6. 通用执行合同

Task/Attempt携带 VerifiedSecurityContextRef、CapabilityLeaseRef、ModelExecutionPlanRef、deadline、tenant/project/run/step、fencingEpoch、retryBudget、idempotencyKey。
恢复时保留原权限上限，同时重验当前授权/吊销/期限；过期lease不得复活，换发必须记录链，不能继承过宽权限。
传输可at-least-once；持久结果 `(tenant,run,step,epoch,idempotencyKey)`幂等。外部effect用effect key+outbox/inbox+对账/补偿。Ambiguous outcome阻断自动重发。

## 7. 错误分类

CONTRACT_DRIFT / SCOPE_INCOMPLETE / ORACLE_CONFLICT / UNSUPPORTED_SEMANTICS / TEST_FAILURE /
INFRA_UNAVAILABLE / FLAKY_CRITICAL / EVIDENCE_TAMPERED / EVIDENCE_STALE / REVISION_MISMATCH /
PROOF_UNKNOWN / PROOF_AXIOM_DENIED / AUDITOR_NOT_CONFIGURED / AUDITOR_CONFLICT /
SIGNER_UNAVAILABLE / LEASE_EXPIRED / FENCE_REJECTED / BUDGET_EXHAUSTED / SIDE_EFFECT_UNKNOWN。
服务同时给machine code、stage、retryable、remediation、traceId；不返回密钥/源码正文。
