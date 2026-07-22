# ELMOS Batch 81–95 “略严苛”测试用例集 Skills

本包用于认证 `elmos-language-packs-batch81-95-complete`，覆盖 COBOL/Mainframe、SAP ABAP、数据库过程语言、PLC、MATLAB/Simulink、Modelica/FMI、VB、IBM i、R、SAS、Salesforce、Objective-C、Delphi、BEAM 与 Lua/OpenResty。

## 规模

- 源 Skills：180（PG223–PG402）
- Batch 专项测试 Skills：15（T081–T095）
- 跨平台 Release Gates：25（T096–T120）
- 测试 Skills 合计：40
- 核心测试用例：640
- 源 Skill 直接覆盖：180 / 180

## 结构

```text
agent-skills/runtime/   40个可安装测试Skills
CASE_CATALOG.json/csv  640个核心用例
COVERAGE_MATRIX.csv     PG223–PG402直接覆盖关系
schemas/                用例、结果与门禁Schema
scripts/                包验证和结果评估
subpackages/            三个Batch分组与跨平台门禁子包
```

## 执行原则

测试必须通过公开的 ELMOS 编排和证据契约执行；核心能力不能只做静态文件存在性检查。需要真实平台或兼容运行时的测试，不允许用 Mock 取代认证。

## 安装与验证

```bash
./install.sh ~/.codex/skills
./validate.sh
python3 scripts/evaluate_results.py results.json
```
