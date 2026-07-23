
# ELMOS Product Convergence & Reference Implementation Skills

这是一套独立的产品收敛实施覆盖层，不增加新的功能Batch。

## 包含

- CONV-001–CONV-032：32个Codex Skills
- 统一Capability Package、依赖图、项目生命周期、Workflow、Evidence、Policy和Skill Registry
- Java/Spring → C#/ASP.NET Reference Route
- Control Plane、Private Runner、Migration Engine和Validation Lab Reference Implementation
- 两家Design Partner、Customer Handoff、Verified Migrated Workload和最终收敛Gate
- 12个JSON Schema、模板、校验器和自动测试

## 安装

```bash
./install.sh /path/to/elmos
```

## 主要入口

```text
$conv-product-convergence-orchestrator
$conv-java-spring-csharp-reference-route
$conv-product-convergence-readiness-gate
```

## 验证

```bash
python3 scripts/product-convergence/validate_skill_bundle.py .
python3 scripts/product-convergence/validate_convergence_bundle.py product-convergence
python3 -m unittest tests/product-convergence/test_toolkit.py
```

默认Readiness Gate为`not-run`，不会因文件存在自动宣称产品成熟。
