# ELMOS Batch 66–80 略严苛测试用例集 Skills

## Inventory

- Source Package：Batch 66–80 Complete，PG223–PG417
- Source Skills：195
- Test Skills：35（15个Batch Suite＋20个Cross-cutting Suite）
- Machine-readable Cases：450
  - Source-specific：390（每个Source Skill一项正向＋一项负向）
  - Cross-cutting：60
- Priority：P0 312、P1 120、P2 18
- Zero-tolerance Cases：103
- Initial Gate：`NOT_RUN`

## Install

```bash
./install.sh ~/.codex/skills
```

只安装某个Batch测试Skill：

```bash
./install.sh ~/.codex/skills --batch 78
```

## Static Validation

```bash
./validate.sh
```

## Execute Gate

在填入真实Case结果和Evidence后：

```bash
python3 scripts/test-suite-b66-80/run_slightly_strict_gate.py test-suites/batch66-80-slightly-strict
```

默认450项均为`not-run`，Gate会返回`NOT_RUN/BLOCKED`语义；静态包验证通过不代表Node、Go、Xcode、Android、数据库、容器、Kubernetes、Terraform或托管CI已真实认证。
