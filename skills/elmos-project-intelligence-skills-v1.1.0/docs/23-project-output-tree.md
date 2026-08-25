# Elmos 分析一个项目后的标准输出树

```text
.elmos-insight/
├── manifest/
│   ├── project-manifest.json
│   ├── technology-fingerprint.json
│   └── analysis-plan.json
├── ir/
│   ├── code-ir/
│   ├── architecture-ir.json
│   ├── flow-ir.json
│   └── data-ir.json
├── graph/
│   ├── project-intelligence-graph.json
│   ├── graph-quality-report.json
│   └── revision-diff.json
├── evidence/
│   ├── claim-register.json
│   ├── evidence-bundle.json
│   └── stale-report.json
├── diagrams/
│   ├── specs/
│   ├── sources/
│   ├── svg/
│   ├── png/
│   └── manifest.json
├── docs/
│   ├── 00-project-overview.md
│   ├── 01-business-capabilities.md
│   ├── 02-system-architecture.md
│   ├── 03-module-catalog/
│   ├── 04-flows/
│   ├── 05-api-events.md
│   ├── 06-data-architecture.md
│   ├── 07-security.md
│   ├── 08-deployment.md
│   ├── 09-testing.md
│   ├── 10-runbook.md
│   └── 11-modernization-roadmap.md
├── presentations/
│   ├── project-overview.pptx
│   ├── architecture-review.pptx
│   └── slide-manifest.json
├── reports/
│   ├── risk-register.yaml
│   ├── technical-debt.yaml
│   ├── impact-report.json
│   ├── threat-model.md
│   └── certification-report.md
├── debug/
│   ├── runtime-profiles/
│   ├── adapter-capability-matrix.yaml
│   ├── sessions/
│   ├── replay-bundles/
│   ├── learning-missions/
│   ├── distributed-session-graphs/
│   └── debug-security-attestations/
├── runtime/
│   ├── runtime-graph.json
│   └── static-runtime-diff.md
├── conversion/
│   ├── source-target-mapping.json
│   ├── behavior-diff.json
│   └── modernization-report.md
└── delivery/
    ├── bundle-manifest.json
    └── evidence-package.zip
```

这是逻辑输出树。生产系统可把大文件放入对象存储，仓库只保留 manifest 和可审阅源文件。
