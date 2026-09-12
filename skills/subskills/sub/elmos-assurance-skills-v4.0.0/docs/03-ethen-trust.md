# Ethen：外部审计职责、独立性和签署

## 1. 身份语义

保留用户给定拼写 `Ethen`，不假定是某个公开产品，也不假定它已经存在、具备认可资质或必然是AI。
配置 `auditor_kind = human | organization | external_system`、subjectId、organizationId、controlDomain、key/identity ref、授权范围、有效期、利益冲突声明。
未配置默认 AUDITOR_NOT_CONFIGURED，E5无法签发。

若Ethen是Elmos作者本人，可以做个人复核/产品责任人审批，但不能标为组织独立的第三方认证。UI与证书区分 `self-reviewed`、`separate-agent`、`separate-control-domain`、`independent-organization`。换一个模型或Prompt仅减少部分同源偏差，不满足组织独立性。

## 2. 五权分离

Builder写候选代码；TestAuthor写公开测试候选；Runner运行被批准测试并产生事实；Ethen挑战/审核；K8Signer按规则签署。
生成/修复无权读隐藏集、改规范批准、改policy、注册根密钥、修改封存证据或发证。
Ethen可提出修复建议但不直接改待认证artifact；一旦参与代码修复，标记冲突，另请符合profile独立性的人/系统复核。

## 3. 审计步骤

核对scope与批准身份 → 独立发现接口（集合不是数量）→ 检查覆盖分母/排除与Oracle → 抽样重建/重跑高风险证据 → 隐藏challenge → 克隆副本盲变异 → proof statement/assumptions/绑定审核 → 缺陷处置 → 签署review decision。

不要把Elmos“为什么认为通过”的推理作为规范；审计必须得到原需求、批准合同、源/目标物、已知缺陷和限制。盲审不应隐瞒事实证据或风险。

## 4. 隐藏集治理

独立bucket/key/worker与访问日志；Builder仅可见已批准的最小反例，不能读seed、完整hidden prompts或下一轮case。
修复暴露的challenge进入public regression并退役；换新的holdout防止过拟合。保留commitment、seed escrow、dataset version、contamination检查和抽样设计。
同一人拥有两套凭据不等于独立机构；审计日志必须记录实际控制关系。

## 5. 人工模式协议

Ethen登录独立身份，读取seal ID，选择审核样本/提出challenge，查看原始证据和规范差异，作出 APPROVE/REJECT/NEEDS_EVIDENCE。
批准绑定 `(tenant, project, run, revisionSetHash, scopeHash, policyHash, evidenceRoot, reviewNonce, expiresAt)`。
双因素/强认证策略由现有IdP执行；server检查audience/nonce/授权与重放，不接受一个前端checkbox或普通JSON名字作真实签名。
审计approval不是最终certificate；K8重新验证授权、撤销列表和全部gate，才签署。

## 6. 系统模式协议

mTLS/workload identity + allowlisted issuer/subject/audience；异步audit job、有deadline与幂等键；报告自定义JSON Schema，产物使用内容寻址。repo中的任意回调URL禁止，需运营配置endpoint registry。
外部系统的LLM只能产生findings与测试建议；deterministic policy评估核验事实。审计服务自身也需校准/隔离/版本记录。

## 7. 原始数据与最小披露

来源授权、客户同意、个人信息脱敏、源码/data classification、地域与保留要求先于发送审计。不能因为名为“外部审计”就复制生产数据库给外部模型。
签名凭据在KMS/HSM或现有授权签署系统，代理只接收key ref；没有该环境本包只形成 unsigned draft。

## 8. 撤销与争议

发现遗漏接口、证据造假、关键新bug、签署密钥泄露或适用环境改变时 suspend/revoke；证书页实时展示status及最新查询时间。
保留appeal、复核者、原始决定与纠正动作，禁止覆盖历史FAIL。
提供的是明确范围的工程保证声明；获得真正外部认可资质需要另行流程，不能借E5命名暗示已有资质。
