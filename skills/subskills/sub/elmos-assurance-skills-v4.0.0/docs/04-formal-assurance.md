# Lean / SMT / 状态模型的适用边界

## 1. 必须证明的是正确的命题

流程：已批准业务claim → 可信challenge statement → 形式语义/假设 → 待证rule/程序义务 → 不可信proof候选 → 隔离编译 → 内核/外部checker → statement一致性 → precondition实例检查 → source/IR/target/artifact绑定 → 证据。

Lean kernel接受proof term不意味着需求正确、SQL引擎符合模型、代码生成器无bug或目标可上线。所有这些都需单列义务。将trusted computing base、外部公理、FFI/native-evaluation、编译器、库、checker版本列入证据。

## 2. 技术选择

Lean：小型可组合变换规则、精确算术、数据不变量、DSL解释器与规范保持。
SMT：有界路径、约束/反例、类型/数值前置条件。SAT表示有模型，UNSAT只有在编码/逻辑/证明验证约束正确时支持所声明结论；UNKNOWN绝不是PASS。
TLC/状态模型：租约fencing、预算/幂等/取消、事件协议的有限模型。通过的是所声明的finite bound，不是无限部署的证明。
原生差分：处理真实运行时、框架、DB dialect与环境；不能用形式模型替代全部原生证据。

## 3. Lean严格模式

锁定工具链版本与下载/镜像摘要。示例候选为截至2026-09-09官方release页可见的 v4.33.1；**本交付环境没有Lean/Lake，示例未编译**，生产仍需完整工具链批准。
可信工作区保存challenge与imports允许清单；proof候选构建在无网络、限额沙箱。禁止导入候选仓库自带的“证明通过器”来审核自己。

对目标theorem做传递公理审计（不是只grep源码）；禁止 sorryAx、自定义未批准公理和扩大信任边界的途径。对native evaluation的处理按精确版本核实，不能沿用旧版本名称当充分检查。
标准公理也需profile允许。`#print axioms`只是检查的一部分；恶意metaprogram/build/olean仍需sandbox、可信statement comparator与独立核验。
严格profile使用官方验证文档描述的comparator+支持该精确语言版本的外部checker。没有兼容外部checker时保留INCONCLUSIVE或申请较低、准确命名的assurance profile，不伪称双核通过。

## 4. 规则证明与实例验证

VerifiedRule带 source/target DSL版本、preconditions、semantics model版本、theorem hash、known counterexamples、evaluator/encoder/lowering版本、runtime regression与批准身份。
“证明一次复用”只适用于相同rule/semantics/toolchain与precondition有效的实例。LLM声称满足前置条件不够，必须有静态可判定验证、证明或真实运行证据。规则撤销按依赖图撤销所有受影响结果。

## 5. SQL例子：不要遗漏外层NULL

将 `x NOT IN (SELECT y FROM T)` 改成相关 `NOT EXISTS(... WHERE y=x)`，只要求T.y非NULL仍不充分：当x为NULL且T非空时两者WHERE选择可能不同。
常用的**充分前提**需覆盖外层x与内层y都非NULL，并保证比较、类型转换/排序规则与相关条件一致；空集边界单列测试。更复杂谓词必须重新建模。
本包 `formal/lean/ElmosProofs.lean` 只给出Bool条件/列表bag子语言中的明确小定理；不是通用SQL等价证明。`examples/sql_null_counterexample.py` 可运行并复现NULL陷阱。

## 6. 项目级形式化覆盖

分母是已批准的critical formal obligations，不是函数行数或theorem数量。证明100个琐碎定理不能覆盖1个未证明的资金不变量。
存在未声明假设、模型不适用、前置条件未知、源码绑定缺失，formal_claim不能PASS。formal N/A也需scope说明，E5证书明确哪些不是formal assurance。

## 7. 反例与现实接口

保持源码span/IR node/rule instance/observation字段可追踪；将SMT或fuzz counterexample最小化成native regression；证明失败可以生成有价值测试，但不能自动删掉原claim。
