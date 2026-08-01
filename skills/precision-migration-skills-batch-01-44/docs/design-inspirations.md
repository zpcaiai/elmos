# Design Inspirations and Capability Mapping

本技能包只吸收公开、通用的软件工程思想，不包含第三方专有实现。

| Public design pattern | Absorbed into |
|---|---|
| 分阶段应用现代化评估、阻断项、目标路径与代表切片试点 | Batch 02-04 |
| Transformation Skill：自然语言、参考知识、样例、规则、PoC、多轮执行与组织私有包 | Batch 11、13、43、44 |
| 语义树、类型归因、可组合Recipe、扫描后重写、最小补丁与回滚 | Batch 05、11、12 |
| 新旧系统双运行、生产事件回放、行为与性能比较 | Batch 30、42 |
| 持续技术债发现、自动修复与执行反馈学习 | Batch 43 |
| 厂商中立数据库IR、Schema/Data/Procedure/App联合迁移 | Batch 19-27 |
| Leanstral辅助证明、Lean Kernel可信裁决 | Batch 33-35 |

## Product boundary

- 云厂商和编码Agent可以作为候选生成器或数据源。
- 本系统的独立价值位于：语义恢复、方向专用验证、反例闭环、证据认证、私有化与最终上线责任。
- 对第三方工具输出采用同一套客观门禁，不因生成来源而降低标准。
