# ETGB v1.0 Coverage Model

## 1. 覆盖定义

覆盖率不是代码行覆盖率的同义词。ETGB 同时维护：

- capability-cell coverage；
- requirement coverage；
- source/target path coverage；
- Oracle coverage；
- technique coverage；
- boundary/fault/security coverage；
- repository scale coverage；
- code line/branch/mutation coverage。

`etgb coverage` 重新从矩阵生成期望 case ID，并与物化 suite 比较；任何缺失或额外漂移都会失败。

## 2. 当前物化规模

| 业务线 | 具体用例 |
|---|---:|
| Spring modernisation | 3,117 |
| Cross-language repository translation | 29,535 |
| Multilingual project generation | 1,451 |
| SQL dialect/routine conversion | 11,761 |
| Cross-cutting | 512 |
| **总计** | **46,376** |

其中 P0 7,020、P1 31,434、P2 7,922。

## 3. Spring 维度

`archetype × feature × variant`：8 个源原型、221 个能力定义，按 applicability 过滤，至少包含 nominal 与 edge-adversarial。

## 4. Cross-language 维度

`pair × feature × variant`：113 条路径、173 个能力定义。Backend 10 种语言为全部有向组合；另有前端、小程序和 Native 路径。

## 5. Project generation 维度

- 10 栈 × 55 模板 × 2 部署档；
- 10 栈 × 20 演化任务；
- 10 栈 × 15 对抗需求；
- 加 1 个离线 smoke。

## 6. SQL 维度

`pair × feature × variant`：30 条迁移路径、206 个能力定义；分析平台专有能力只应用于 analytics pair。

## 7. 横切维度

`business-line × scenario × fault-position`：4 × 64 × 2 = 512。

## 8. 关闭缺口的规则

一个 capability cell 只有在以下条件全部满足时才算“已覆盖”：

1. case definition 通过 Schema；
2. 具备输入、目标、可执行计划和 Oracle；
3. 至少存在一个正常变体和一个边界/逆向变体；
4. P0 具备隐藏测试或独立 Oracle；
5. 运行结果带完整 evidence；
6. 不可用环境被显式报告，而不是跳过后当通过；
7. 生产发布还需通过对应 release gate。
