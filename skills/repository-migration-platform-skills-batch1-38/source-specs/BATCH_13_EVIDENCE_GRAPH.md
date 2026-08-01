# Batch 13：Evidence Graph、独立裁判、红队与持续认证

## 总体目标

把前置 Batch 产生的代码、执行、测试、Proof、Shadow、Canary 和事故结果统一为不可篡改、可追溯、可独立重放和可持续撤销的信任系统。

## 建议仓库结构

```text
evidence-model/
evidence-graph/
immutable-artifact-store/
verification-plane/
certification-authority/
red-team/
continuous-certification/
governance/
```

## 1. Evidence 核心模型

- Artifact/Execution/Observation/Decision/Finding/Review/Certificate/Revocation IR
- Evidence Result：PASS、FAIL、PARTIAL、INCONCLUSIVE、INVALID、REVOKED
- Assumption、Limitation、Freshness、Criticality、Reproducibility、Quality Score
## 2. 不可变存储与签名

- Content-addressed Artifact Store
- Append-only Metadata 与不可变 History
- Artifact/Execution/Finding/Certificate Signatures
- Trusted Timestamp、Transparency Log、Key Rotation/Revocation
## 3. 完整 Lineage

- Source→IR→Target→Build→Execution→Observation→Oracle→Finding→Certificate
- Proof Lineage、Model Usage Lineage、Human Decision Lineage
- Impact Query、Conflict Query、Coverage Gap Query
## 4. 独立裁判

- Builder/Verifier/Oracle/Red Team/CA 强隔离
- Independent Oracle Registry 与 O0–O4 独立等级
- Independent Replay、Cross-Region/Architecture/Runtime Reproduction
## 5. Certification Authority

- Root/Intermediate/Delegated CA
- Certificate Scope、Ceiling、Expiry、Downgrade、Suspension、Revocation
- Certificate Dependency Graph 与 Revocation Cascade
## 6. Red Team 与 Anti-Gaming

- Evidence Forgery、Old Evidence Replay、Normalizer Abuse、Scope Broadening
- Metric Gaming、Waiver Abuse、Role Collision、Split-view Transparency
- 历史 Release 重扫描与持续认证

## 认证体系：EA1–EA5 Evidence Assurance

EA1–EA5 Evidence Assurance 必须绑定精确 Scope、Artifact Hash、环境、版本、Assumptions、Evidence 与有效期。证书必须支持 Expiry、Downgrade、Suspension、Revocation 和 Independent Renewal。

## 主要输出

- Immutable Evidence Graph
- Artifact/Execution/Finding/Certificate Registries
- Transparency Log
- Independent Verifier Runtime
- Certificate Authority
- Historical Rescan Reports
- EA1–EA5 Certificates

## 硬性原则

- 测试通过记录不等于可信 Evidence
- Builder 不能成为自身 Artifact 的最终裁判
- 失败 Attempt 不能因重试而隐藏
- 证书必须绑定精确 Scope
- AI 不得自我认证
- Critical Conflict 未解决时冻结认证

## Definition of Done

```yaml
evidence_graph: operational
immutable_store: pass
builder_verifier_separation: pass
independent_oracles: pass
certificate_lifecycle: pass
red_team: pass
critical_role_conflicts: 0
forged_active_certificates: 0
unresolved_critical_conflicts: 0
final_evidence_root: sealed
```
