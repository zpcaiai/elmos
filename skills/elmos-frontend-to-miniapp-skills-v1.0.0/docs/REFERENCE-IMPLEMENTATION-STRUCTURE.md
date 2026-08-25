# 参考实现目录结构

建议把转换引擎作为 Elmos monorepo 中的独立能力域：

```text
apps/
├── conversion-api/
├── conversion-worker/
├── build-worker/
├── validation-worker/
└── miniapp-admin/

packages/
├── conversion-contracts/
├── repository-inventory/
├── source-vue/
├── source-react/
├── source-flutter-cli/
├── source-h5/
├── source-native-miniapp/
├── semantic-ir/
├── ir-migrations/
├── rule-engine/
├── capability-registry/
├── component-mappings/
├── style-lowering/
├── lifecycle-lowering/
├── dependency-migration/
├── target-wechat/
├── target-alipay/
├── target-douyin/
├── target-xiaohongshu/
├── platform-ports/
├── differential-harness/
├── visual-harness/
├── privacy-auditor/
├── auto-repair/
├── evidence-model/
└── toolchain-adapters/

infra/
├── containers/
│   ├── analyzer-node/
│   ├── analyzer-dart/
│   ├── build-wechat/
│   ├── build-alipay/
│   ├── build-douyin/
│   └── build-xiaohongshu/
├── policies/
├── workflows/
└── observability/

registry/
├── capabilities/
├── components/
├── platform-profiles/
├── dependency-replacements/
└── schema-migrations/

tests/
├── fixtures/
├── golden/
├── contract/
├── differential/
├── visual/
├── security/
└── e2e/
```

## 包职责

### conversion-contracts

- 任务请求、检查点、产物、门禁和审批 DTO；
- 由 OpenAPI/JSON Schema 生成多语言类型；
- 不含平台实现。

### repository-inventory

- 安全扫描文件树、包管理器和构建配置；
- 禁止执行仓库脚本；
- 输出 `project-inventory.json`。

### source-vue / source-react / source-flutter-cli

- 只生成 source facts 与 trace；
- 不直接生成平台文件；
- 解析失败也输出结构化错误与覆盖率。

### semantic-ir / ir-migrations

- 稳定 ID；
- Draft 2020-12 Schema；
- 确定性 JSON；
- 版本迁移和 compatibility tests。

### rule-engine

规则输入：

```ts
type RuleInput = {
  irNode: IRNode;
  platform: PlatformId;
  platformProfileVersion: string;
  capabilityRegistryVersion: string;
  policy: ConversionPolicy;
};
```

规则输出：

```ts
type RuleDecision = {
  classification: "A" | "B" | "C" | "D" | "E";
  targetPattern?: string;
  rationale: string;
  evidenceRefs: string[];
  requiredPermissions: string[];
  requiredTests: string[];
  risk: "low" | "medium" | "high" | "critical";
};
```

### target-*

目标 generator 只接受通过 Schema 的 IR 和计划。Generator 必须：

- 确定性；
- 可重入；
- 不调用真实平台副作用；
- 输出 trace；
- 不写 secret；
- 不手工拼接不可信路径。

### build-worker

每个平台独立镜像或受控 VM。构建输入是只读的生成快照；输出包括：

- 工具版本；
- 命令摘要；
- 退出码；
- 标准输出脱敏摘要；
- 产物哈希；
- 预览或上传回执。

### validation-worker

- mock/sandbox 外部依赖；
- 捕获行为 trace；
- 固定时间、随机数和动态数据；
- 对真机或官方 IDE 自动化不可用的部分输出明确阻断。

### evidence-model

所有结论以 claim/evidence 表示：

```ts
type EvidenceClaim = {
  id: string;
  claimType: "build" | "semantic-parity" | "visual-parity" | "privacy" | "security" | "release";
  subject: string;
  status: "passed" | "failed" | "blocked" | "unknown";
  evidence: ArtifactRef[];
  evaluatedAt: string;
  evaluatorVersion: string;
};
```

## 推荐技术选择

- TypeScript：Vue/React/H5 分析、IR、规则和代码生成；
- Dart：Flutter 静态分析；
- Rust：大仓库扫描、CAS、增量图和高性能规则执行（可逐步引入）；
- Python：报告、图像差分和离线分析；
- Java/TypeScript：Elmos 企业 API、任务与计费集成；
- PostgreSQL：任务、产物、规则版本、审批和成本；
- 对象存储：源快照、生成产物、截图和证据；
- Temporal 或 Elmos 已有可恢复工作流：长任务状态机；
- OpenTelemetry：trace、metrics 和日志。

技术版本应由仓库 lockfile 固定，不在 Skill 中硬编码会快速过期的版本号。
