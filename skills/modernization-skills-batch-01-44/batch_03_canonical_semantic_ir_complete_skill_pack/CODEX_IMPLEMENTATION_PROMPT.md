# Codex Implementation Prompt — Batch 03

你正在实现 `batch-03`：**Batch 3：统一源码摄取、解析前端与 Canonical Semantic IR Foundation**。

## 必读文件

开始编码前，完整阅读：

```text
README.md
SKILL.md
SKILL_INDEX.md
BATCH02_COMPATIBILITY.md
IMPLEMENTATION_CHECKLIST.md
VALIDATION_REPORT.md
schemas/
policies/
examples/
tests/SCENARIOS.md
skills/*/SKILL.md
```

不得只读取根 `SKILL.md` 后跳过子 Skill。

## 总目标

将 Batch 2 锁定的多语言源码、配置、构建文件、SQL、API 契约、生成代码、二进制和运行元数据转换为 Native Lossless IR、Canonical Semantic IR、Analysis Graph IR、Domain IR 与 Formalizable Core，为后续转换、生成、验证和形式证明提供共同语义底座。

## 可信边界

- 原始字节、Native IR、Canonical IR、Analysis Graph 和 Formal Core 分层。
- Compiler-confirmed、Deterministic Analysis、Runtime Observed、Model Inferred 和 Unknown 分离。
- 所有 Lowering、Desugaring 和生成节点具有 Source Map 与 Provenance。
- 后续 Skill 必须声明最低 IR Level 与允许 Unknown。

## 强制工程原则

- Lossless Layer for Fidelity, Canonical Layer for Comparison
- Common Semantics in CSIR, Native Semantics in Extension Capsules
- Facts, Inferences and Unknowns Are Distinct
- Every Lowering Is Traceable
- Semantic Requirements Are Explicit
- Build Context Is Part of Meaning
- Content-addressed and Incremental
- Formal Boundary Is Explicit

## 禁止事项

- 不把所有语言压扁成万能 AST。
- 不在本 Batch 完成目标语言代码生成。
- 不把语法解析成功等同语义恢复成功。
- 不把模型推断类型冒充编译器类型。
- 不执行未经授权的构建脚本、宏处理器或反编译。
- 不删除无法规范化的语言专有语义。

## 建议仓库形态

```text
apps/
  api/
  console/
services/
packages/
  contracts/
  domain/
  adapters/
  policy/
  evidence/
  observability/
workers/
schemas/
policies/
tests/
  unit/
  contract/
  integration/
  security/
  certification/
```

可根据目标仓库技术栈调整目录，但不得破坏 Schema、证书、证据和兼容边界。

## 实现阶段

### Phase 1: Raw、Build Context 与 Frontend SDK

- 实现 Source Blob、Encoding、Path 和 Archive Security。
- 实现 Language/Region Detection、Build Context Graph。
- 实现 Frontend SDK、Registry、Sandbox 和 Capability Manifest。

### Phase 2: Native IR、Symbols 与 Types

- 实现 NLST、Round Trip 和 Native Diagnostics。
- 实现 Compiler-backed Attribution、Symbol/Scope 和 Canonical TypeRef。
- 实现 Extension Capsule Registry。

### Phase 3: CSIR 与分析图

- 实现 CSIR Schema 与 Lowering。
- 实现 Evaluation Order、CFG、SSA、Dataflow、Callgraph、Effect。
- 实现 BuildIR、ConfigIR、ApiIR、SqlIR 和 BinaryIR。

### Phase 4: Provenance、Formal、Incremental 与认证

- 实现 Source Map、Fingerprint 和 Generated/Macro Provenance。
- 实现 Formalizable Core 和 Proof Obligation。
- 实现 Chunk Store、Diff/Query API、IR0–IR6 Certificate。


## 每个阶段必须执行

1. 运行单元测试、契约测试和静态检查。
2. 更新实现清单，但不得篡改验证要求以制造通过。
3. 记录未实现范围、Unknown、风险与下一阶段依赖。
4. 对任何 Schema、策略或证书变化增加兼容性测试。
5. 对失败路径、暂停恢复、幂等、权限和失效规则编写测试。
6. 运行 `python tools/validate_package.py`，保持规格包本身有效。

## 输出要求

最终提交至少包含：

```text
可运行服务或库
数据库迁移脚本
OpenAPI 或等价 API 契约
事件和任务契约
测试与 Fixtures
本地启动说明
CI 配置
威胁模型与权限说明
观测指标
证书与证据样例
实现状态矩阵
```

## 完成标准

- 24 个 Skills 均有可运行实现或明确状态。
- 每个资产有 Raw、Native、Canonical 和分析层语义等级。
- Compiler Fact、Model Inference、Dynamic、Unknown 和 Opaque 分离。
- IR Bundle 内容寻址、可增量、可查询和可失效。
- IR0–IR6 Certificate 可按资产签发。

任何未达到的项目必须标为 `not-implemented`、`partial` 或 `experimental`；禁止用文档宣称替代实现和测试。
