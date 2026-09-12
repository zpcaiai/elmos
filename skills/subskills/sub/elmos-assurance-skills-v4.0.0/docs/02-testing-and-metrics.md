# 测试设计与可解释指标

## 1. 完整的测试不是输入笛卡尔积

将每项义务表达为 `interface × requirement × state/transition × input partition × role/tenant × failure mode × effect × platform` 的**已批准风险选择**。
关键权限/跨租户/资金/事务/幂等路径显式覆盖；普通组合可用pairwise/t-wise，但报告必须标记组合强度而非声称全部组合。

分别显示 planned、executable、executed、asserted、passed。HTTP请求被发出不等于响应语义、副作用或权限已被断言。分母为空显示 N/A/INCONCLUSIVE，不能100%。
覆盖计算基于冻结且有哈希的 ObligationSet，证据要求匹配该版本。独立接口发现以集合差异判断，不仅比较数量。

## 2. Oracle优先规则是职责，不是一个万能排序

- 正确性：客户/领域责任人批准的规范、不变量、安全政策。
- 兼容性：source runtime/golden traces，但要列明已批准的行为改变。
- 差分：source和target一致只能证明这次观测一致，可能共同犯错。
- 数学/性质：用独立reference implementation或经批准的代数/状态关系。
- 变形关系必须带前提；LLM生成的expected只是待审候选。

两种oracle冲突时新建finding；不得选择让测试通过的一方。规范生成与实现生成分支必须独立评审；同源规范本身错误仍可能使两者一起错。

## 3. 冒烟与全回归

冒烟按critical risk/dependency/历史故障选择低成本集合，必须包含真实业务canary，health=200不够。
若smoke不能覆盖所有规定关键义务，返回缺口而不是截断预算继续PASS。
Smoke通过才调度依赖其环境的全回归。全回归执行固定manifest中的全部必需case，不是把test runner恰好发现的集合当作“全部”。
最终发布全回归在同一候选artifact上运行。增量impact analysis只用于修复反馈；要复用证据须满足完整dependency closure、scope/policy批准、有效期与未变假设，不能复用旧artifact下的“全回归完成”。

## 4. 隔离、可复现、异步时序

每个scenario拥有独立DB schema/namespace、逻辑时钟和seed。真实secret由broker发短期token。
记录clock/timezone/locale/collation、随机seed、外部依赖版本。事件以correlationId和因果偏序比较，不用全局任意排序消除真实竞态；eventual consistency使用规范规定的deadline/稳定窗口。
UI单独记录DOM/无障碍树、网络、最终状态；视觉差异只在固定viewport/font/渲染版本下比较，不能仅凭截图判断功能。

## 5. 变异正确用法

标准化mutant状态：KILLED / SURVIVED / PROVEN_EQUIVALENT / INVALID / TIMEOUT / INFRA_ERROR / UNREACHED / UNKNOWN。
只允许有独立复核证据的equivalent/invalid从有效分母排除；TIMEOUT不默认算killed。
保守kill ratio：`KILLED / (KILLED + SURVIVED + UNREACHED + TIMEOUT + INFRA_ERROR + UNKNOWN)`；另报已确定有效分母上的ratio与未决数量。分母未收敛不能给critical PASS。

盲变异在克隆副本注入，不污染最终交付物；区分是在评估test suite、整个certifier还是Ethen。真实历史bug corpus与synthetic mutants分开报告。
禁止要求无依据的99.9% mutation目标。每个domain/profile先测baseline并经独立校准批准阈值；关键安全语义的指定must-kill集合必须全杀。

## 6. 两种“假通过率”不可混淆

`Defective-PASS rate = 缺陷样本中PASS数 / 经独立标注的缺陷样本数`，即P(PASS|defect)。
`Bad-certificate fraction = PASS样本中有缺陷数 / 经独立复核的PASS样本数`，即P(defect|PASS)。

还报 defect recall、false rejection、abstention、coverage debt、escaped critical defects、反例缩减率、每认证artifact的CPU/token/费用、P50/P95 wall-clock。

零失败不等于零风险。对独立同分布样本、固定判定规则、预先选定n，0/n事件的单侧95%二项上界为 `1 - 0.05**(1/n)`。例如 n=100约2.95%；n=3000约0.0998%。相关的同repo变异不能当3000个独立项目；按项目/缺陷族聚类并分层报告。该上界不自动适用于真实生产分布。

## 7. 测试质量红线

空suite、无assert、只assert status、过度mock关键effect、跳过critical、无限retry、泄露holdout、snapshot盲更新、放大浮点容差、把NULL变空串、bag去重、timestamp去时区、把未排序结果强行排序，均有专门负例。

## 8. 发布前完整测试组合

功能与契约 → 工作流/状态 → 权限/隔离 → DB/MQ/cache副作用 → 差分 → 性质/变形 → fuzz → 变异 → 安全/供应链 → 负载/故障/恢复 → 适用形式化 → Ethen challenge。
每层声明适用范围、原生工具、observation adapter和gate，不要求所有业务都使用所有工具。
