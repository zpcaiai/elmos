# FRT G01–G30 Complete Skills Pack

本包整合FRT大型前端仓库转换平台 **Generation Batch G01–G30**，覆盖六类前端技术、30条有向转换路径、形式验证、产品化、功能/业务/数据/管理/可用性/回归/性能/韧性/安全和Production Closure。

## Inventory

- 30 Batch级`SKILL.md`
- 472 个独立可安装子Skill
- G01–G30兼容链与Certificate family
- Codex实施Prompt、检查清单、安装和验证脚本
- Schema、示例、包清单与SHA-256

## Install

```bash
./install.sh ~/.codex/skills
```

默认不覆盖同名Skill。需要覆盖时：

```bash
./install.sh ~/.codex/skills --overwrite
```

## Validate

```bash
./validate.sh
```

## Recommended implementation order

```text
G01 → G12：核心语义与平台能力
G13 → G17：30条方向路径
G18：Pack组合
G19：形式验证与反例修复
G20：产品化
G21 → G30：Production Closure
```

## Trust model

模型只生成候选；编译器、类型系统、测试、Proof Kernel、设备和运行Evidence决定是否通过。任何R4/R5缺口均不可由平均分补偿。

详见`PROVENANCE.md`和`VALIDATION_REPORT.md`。
