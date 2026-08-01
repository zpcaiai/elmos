# Batch 20：Skill SDK、Skill Runtime、Skill Registry 与产品化封装

## 总体目标

把前十九批能力统一封装为具有 Schema、权限、Sandbox、证据、版本、签名、SBOM、商业授权和持续认证的 Skills 产品生态。

## 建议仓库结构

```text
skill-specification/
skill-sdk/
skill-runtime/
plugin-runtime/
package-manager/
skill-registry/
marketplace/
interfaces/
commercialization/
ecosystem-governance/
```

## 1. Skill Specification

- Skill Manifest、Input/Output/Error/Event/Config Schemas
- Capability、Permission、Side-Effect、Idempotency、Retry、Cancellation、Checkpoint、Cost、Privacy、License Contracts
## 2. Skill SDK 与 Runtime

- Python/Java/C#/Rust/Go/TypeScript/Node/C++/Objective-C/Swift SDK
- Artifact/Evidence/Finding/Counterexample/Tool/Model/Secret/Effect APIs
- Admission、Context、Package Load、Sandbox、Output Validation、Replay、Audit
## 3. Plugin 与 Dependency

- Frontend/Lowering/Emitter/Framework/Dependency/Domain/Validator/UI Hooks
- Plugin Isolation、Permission Intersection、Failure Isolation
- Skill Dependency Resolver、Capability Provider、Lockfile、License/Certificate/Schema Compatibility
## 4. Package 与 Lifecycle

- Package Format、Runtime/Rules/Templates/Tests/Docs/SBOM/Provenance/Signatures
- Install、Self-Test、Activation、Upgrade Shadow/Canary、Rollback、Uninstall、Emergency Revocation
## 5. Interfaces 与 Registry

- CLI、REST、gRPC、10-language Clients、IDE、Web Console、Execution OS Integration
- Public/Private/Air-gapped Registry、Immutable Versions、Advisories、Revocations、Transparency
## 6. Marketplace 与商业化

- Listing、Search、Recommendation、Publisher、Reviews、Moderation
- Metering、Entitlements、License、Billing、Revenue Share、Enterprise Governance
- 商业与认证隔离、Anti-Gaming

## 认证体系：SC1–SC5 Skill Certification

SC1–SC5 Skill Certification 必须绑定精确 Scope、Artifact Hash、环境、版本、Assumptions、Evidence 与有效期。证书必须支持 Expiry、Downgrade、Suspension、Revocation 和 Independent Renewal。

## 主要输出

- Skill Manifest/Schema Specifications
- 10-language SDKs
- Skill/Plugin Runtime
- Package Manager and Lockfile
- Permission/Sandbox/Secret/Effect Runtime
- CLI/API/IDE/Web Console
- Public/Private/Air-gapped Registry
- Marketplace
- Metering/License/Billing
- SC1–SC5 Certificates
- Final Platform Evidence Root

## 硬性原则

- 一个 Prompt 不等于 Skill
- 自由文本接口不能承载高风险权限
- Plugin 不得继承宿主全部权限
- 签名只证明来源不证明安全
- Skill 证书不自动成为项目证书
- 商业激励不得影响认证结论

## Definition of Done

```yaml
skill_manifest_schema: pass
input_output_schemas: pass
multi_language_sdks: pass
skill_runtime: pass
plugin_isolation: pass
dependency_resolver: pass
package_signatures_sbom: pass
permission_sandbox_secret_effect_governance: pass
install_upgrade_rollback_uninstall: pass
cli_api_ide_web: pass
registry_marketplace: pass
metering_license_billing: pass
revoked_skills_executable: 0
sc1_to_sc5: pass
final_platform_evidence_root: sealed
```
