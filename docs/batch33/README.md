# Batch 33 Codex Skills：Cloud、IaC 与 DevOps 迁移

本包提供 **Skills 1223–1242**，用于让 Codex 在现有迁移平台代码仓库中实施、验证和认证 Cloud、IaC 与 DevOps 现代化能力。

它不是一组抽象架构说明，而是一个可安装工程覆盖包，包含：

- 20 个仓库级 Codex Skills；
- Runtime Architecture Contract；
- Provider-neutral IaC IR；
- Cloud Pack、Support Matrix、Target Profile 和 Validation Profile；
- 脚手架、验证器、候选评分和保守认证 Gate；
- JSON Schema、模板、负向测试和回归测试；
- Batch 20–32 代码仓库的可合并安装结构。

## 1. Skills 1223–1242

| Skill | 调用名 | 主要用途 |
|---:|---|---|
| 1223 | `$b33-cloud-iac-devops-factory` | 建立并认证一条精确、有方向的 Cloud/IaC/DevOps 迁移 Pack |
| 1224 | `$b33-runtime-architecture-contract` | 提取运行架构、身份、网络、数据流、可用性、恢复和运维 Contract |
| 1225 | `$b33-provider-neutral-iac-ir` | 建立类型化、Provider-neutral IaC IR 与资源所有权模型 |
| 1226 | `$b33-cloud-service-capability-map` | 把源云能力映射到目标服务、模块、Adapter、共存或 Block 策略 |
| 1227 | `$b33-container-build-migration` | 迁移 Dockerfile、镜像构建、SBOM、签名、Provenance 和运行 Contract |
| 1228 | `$b33-kubernetes-manifest-migration` | 迁移 Kubernetes 工作负载、策略、存储、健康、扩缩容和发布行为 |
| 1229 | `$b33-helm-chart-migration` | 迁移 Helm Chart、Values、Hook、依赖、升级、回滚和 Chart Test |
| 1230 | `$b33-terraform-module-migration` | 迁移 Terraform Module、Provider、State、Import、Move、Plan、Drift 和 Destroy |
| 1231 | `$b33-cloud-native-iac-migration` | 迁移 CloudFormation、Bicep、ARM 等云原生 IaC |
| 1232 | `$b33-cicd-pipeline-migration` | 迁移 Jenkins、GitHub Actions、GitLab CI、Azure DevOps 等流水线 |
| 1233 | `$b33-secret-config-environment` | 迁移 Secret、Config、Environment、证书和 Promotion 语义 |
| 1234 | `$b33-identity-network-dns-mesh` | 迁移 Identity、Network、DNS、Private Connectivity 和 Service Mesh |
| 1235 | `$b33-serverless-event-runtime` | 迁移 Serverless Function、Trigger、Retry、DLQ、并发和超时 |
| 1236 | `$b33-managed-service-mapping` | 映射数据库、Cache、Queue、Stream、Object Store、Search 等托管服务 |
| 1237 | `$b33-api-gateway-ingress-traffic` | 迁移 API Gateway、Ingress、域名、证书、限流、Canary 和流量策略 |
| 1238 | `$b33-observability-alert-dashboard` | 迁移 Metrics、Logs、Traces、Alert、Dashboard、SLO 和 Retention |
| 1239 | `$b33-cloud-security-guardrails` | 迁移 IAM、Network、Encryption、Admission、Compliance 和 Guardrail |
| 1240 | `$b33-cloud-cost-capacity-optimizer` | 验证并优化容量、Quota、性能、可用性和成本 |
| 1241 | `$b33-infrastructure-drift-validator` | 对齐定义、State、Managed Fields、Live Resource、Policy、Cost 与 Runtime Contract |
| 1242 | `$b33-cloud-certification-gate` | 执行保守认证 Gate，输出 certified、limited、experimental 或 blocked |

## 2. 安装

```bash
./install.sh /path/to/migration-platform
cd /path/to/migration-platform
make batch33-check
```

安装内容包括：

```text
.agents/skills/b33-*/SKILL.md
docs/batch33/
schemas/batch33/
templates/batch33/
scripts/batch33/
tests/batch33/
Makefile.batch33
```

若目标仓库已有 `AGENTS.md` 和 `Makefile`，安装器会追加 Batch 33 入口，不覆盖现有内容。

## 3. 创建 Cloud Pack

例如创建 AWS CloudFormation/EKS 到 Azure Terraform/AKS 的研究 Pack：

```bash
python3 scripts/batch33/scaffold_cloud_pack.py \
  --source-platform aws \
  --target-platform azure \
  --source-provider aws \
  --target-provider azurerm \
  --source-region us-east-1 \
  --target-region eastus \
  --source-iac-tool cloudformation \
  --source-iac-version 2010-09-09 \
  --target-iac-tool terraform \
  --target-iac-version 1.12.2 \
  --source-runtime eks \
  --source-runtime-version 1.32 \
  --target-runtime aks \
  --target-runtime-version 1.33 \
  --source-ci jenkins \
  --source-ci-version 2.516 \
  --target-ci github-actions \
  --target-ci-version 2026
```

生成目录：

```text
cloud-packs/<pack-key>/
├── pack.json
├── support-matrix.json
├── route-matrix.json
├── source-fingerprint/
│   └── fingerprint.json
├── runtime-architecture/
│   └── contract.json
├── iac-ir/
│   └── model.json
├── target-profile/
│   └── profile.json
├── validation/
│   └── validation-profile.json
├── transformations/
├── adapters/
├── policies/
├── state/
├── rollout/
├── cost/
├── drift/
├── corpus/
│   ├── development/
│   ├── negative/
│   ├── holdout/
│   └── representative-workloads/
└── certification/
    ├── evidence.json
    ├── certification.json
    ├── gap-inventory.md
    ├── gate-result.json
    └── gate-report.md
```

## 4. 验证 Pack

```bash
python3 scripts/batch33/validate_cloud_pack.py \
  cloud-packs/<pack-key>

python3 scripts/batch33/validate_runtime_contract.py \
  cloud-packs/<pack-key>/runtime-architecture/contract.json

python3 scripts/batch33/validate_iac_ir.py \
  cloud-packs/<pack-key>/iac-ir/model.json

python3 scripts/batch33/run_cloud_gate.py \
  cloud-packs/<pack-key>
```

研究状态 Pack 可以通过结构验证，但只有真实 Evidence 满足认证阈值时才允许 `certified`。

## 5. 认证 Gate

认证状态不能通过编辑 JSON 绕过。`certified` 至少要求：

```text
Source Fingerprint Coverage               >= 95%
Runtime Contract Source-map Coverage      >= 95%
IaC IR Source-map Coverage                >= 95%
Source Plan Pass Rate                     = 100%
Target Plan Pass Rate                     = 100%
Target Apply/Emulator Pass Rate           = 100%
P0 Deployment Contract Pass Rate          = 100%
Container Build Pass Rate                 = 100%
Kubernetes Validation Pass Rate           = 100%
CI/CD Pipeline Pass Rate                  = 100%
Identity/Network Contract Pass Rate       = 100%
Secret/Config Pass Rate                   = 100%
Observability Pass Rate                   = 100%
Security Guardrail Pass Rate              = 100%
Drift Validation Pass Rate                = 100%
Cost Budget Pass Rate                     = 100%
Rollback/Destroy Pass Rate                = 100%
Representative Workload Pass Rate         = 100%
Source-map Coverage                       >= 95%
```

以下值必须为零：

```text
Critical Unknowns
Silent Resource Drops
Critical Security Regressions
Critical Network Exposures
Secret Leaks
Privilege Expansions
Data Residency Violations
Unauthorized Public Egress
Unapproved Provider Changes
Unknown Drift Resources
Orphaned Resources
Cost Budget Violations
Destroy Failures
Test Integrity Violations
Unapproved Baseline Changes
```

还必须具备：

- 独立 Holdout Corpus；
- Representative Workload Corpus；
- Runtime Architecture 和 IaC IR 中的真实节点及 Source Map；
- P0 Workload；
- 真实 Plan、Apply/Emulator、Runtime、Security、Drift、Cost、Rollback 和 Cleanup Evidence；
- 精确 Source/Target Tuple、版本、Region、Account Model、Provider、Runtime 和 State Backend；
- 可验证 Evidence 引用。

## 6. Codex 调用示例

### 建立完整 Cloud Pack

```text
$b33-cloud-iac-devops-factory

检查当前仓库并实施一条 AWS CloudFormation/EKS 到
Azure Terraform/AKS 的生产形态迁移 Pack。

要求：
1. 锁定云平台、Provider、IaC Tool、Runtime、Region、Account Model、State Backend 和 CI/CD 精确版本；
2. 同时执行静态定义和真实运行时发现；
3. 生成 Runtime Architecture Contract 与 Provider-neutral IaC IR；
4. 覆盖 Container、Kubernetes、Terraform、CI/CD、Identity、Network、Secret、Observability 和 Security；
5. 使用隔离账号或批准模拟环境执行真实 Plan，以及适用的 Apply/Runtime 验证；
6. 验证 Drift、Cost、Rollback、Destroy 和孤儿资源清理；
7. 建立 Negative、Holdout 和 Representative Workload Corpus；
8. 禁止为了通过测试扩大 IAM、开放公网、关闭策略或写入明文 Secret；
9. 最终状态只能由 Batch 33 Gate 决定。
```

### Terraform Module 和 State 迁移

```text
$b33-terraform-module-migration

迁移当前Terraform Module与State。

必须：
- 锁定CLI和Provider版本；
- 解析Module、Provider Schema、Backend、Workspace、State Address、Import、Moved Block和Lifecycle；
- 生成类型化IaC IR；
- 使用保存的Plan并审查机器可读Plan JSON；
- 在隔离Backend验证Import、Move、Lock、Apply、Drift、Upgrade、Recovery和Destroy；
- 不得出现未批准Replace、Secret输出、孤儿资源或State冲突。
```

### Kubernetes Workload 迁移

```text
$b33-kubernetes-manifest-migration

迁移一个P0 Kubernetes工作负载。

必须保持：
- Namespace、ServiceAccount和Workload Identity；
- NetworkPolicy、Ingress/Egress和Private Exposure；
- Config/Secret Reference；
- Volume、StorageClass和Data Policy；
- Probe、Resource、Autoscaling、PDB和Rollout；
- Field Ownership和Managed Fields；
- Server-side Validation、Canary、Rollback和Cleanup。

禁止使用force-conflicts或关闭Schema验证来获得成功。
```

### 最终认证

```text
$b33-cloud-certification-gate

对cloud-packs/<pack-key>执行完整Batch 33认证。

核对精确Tuple、Runtime Fingerprint、Runtime Architecture Contract、IaC IR、Target Profile、真实Plan、Apply或Emulator、P0 Runtime、Security、Drift、Cost、Rollback、Destroy、Holdout、Representative Workload和Evidence。

证据不足时必须维持research、experimental、limited或blocked，不能输出certified。
```

## 7. 设计约束

- 每个 Pack 都是精确、方向性、版本化并独立认证的；反向路线或另一 Region/Provider 是不同 Pack。
- 静态 IaC 不等于生产事实；必须结合 State、Managed Fields、Live Resources、Runtime Telemetry、Policy 和 Cost。
- 复杂迁移必须通过类型化 Contract 和 IR，不允许以 Regex 或原始文本替换作为语义核心。
- 客户已有资源和 State 必须有 Import、Move、Ownership、Replace、Coexistence 和 Destroy 策略。
- 所有 Apply、Runtime 和 Destroy 测试必须在批准的隔离环境中执行，并记录 TTL、Owner、Budget 和 Cleanup Evidence。
- Model 生成的 IaC、Pipeline 或 Policy 仅是候选，也必须通过同一认证 Gate。

## 8. 范围说明

本包实现的是：

```text
Codex实施工作流
+ Cloud Pack协议
+ Runtime Architecture Contract
+ IaC IR
+ Schema和模板
+ 脚手架
+ 验证器
+ 保守认证Gate
+ 自动化测试
```

它不代表 AWS、Azure、GCP、Kubernetes、Helm、Terraform、CloudFormation、Bicep、Jenkins、GitHub Actions 等实际迁移引擎或路线已经获得认证。真实路线仍须在具有相应CLI、云账号、集群、State Backend、CI/CD和隔离测试环境的工程仓库中完成并提供真实Evidence。
