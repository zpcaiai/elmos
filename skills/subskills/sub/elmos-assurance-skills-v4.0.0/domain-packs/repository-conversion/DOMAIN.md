# 仓库级跨语言转换 Domain Pack

## 保证目标
Module refinement + boundary observations + repo-level workflows

## 首个商业纵向切片
Java→C#等一个明确语言对，先纯领域模块和HTTP/DB边界，再扩展并发/反射

## 核心语义
采用Semantic IR中的类型/数值/NULL/异常/ownership/effect/concurrency能力块，而非一次写全世界统一语言。
每个language pair单独声明支持特性和runtime/stdlib/serialization版本；泛型、反射、FFI、native库、动态加载必须显式适配或unsupported。
小模块证明不能自动组合成全库证明；需要依赖假设、模块边界契约、组合义务与实际lowering/codegen绑定。
跨语言通信比较规范化协议值，语言内部的raw memory/运行时异常文本不可作为默认业务oracle。
关键纯函数可用Lean证明IR变换，真实runtime语义仍需native golden tests。

## 必需验收场景
- **REP-001** — 整数min/max/overflow与除法：按照源目标精确语义判定，必要时引入compat shim。
- **REP-002** — Unicode代理对/组合字符：按声明length/encoding语义比较，不能默认所有string等价。
- **REP-003** — 异常/资源释放/取消：观察异常类型映射、finally/dispose和残余effect。
- **REP-004** — equals/hash集合与序列化：不因排序normalizer掩盖业务依赖顺序。
- **REP-005** — 并发更新/锁/异步重试：有限调度和原生stress共同发现状态/幂等错误。
- **REP-006** — 模块正确但repo装配错误：原生build、contract、端到端workflow失败必须阻断。

## 形式化义务候选
纯子语言的语义保持；rule preconditions与组合义务；类型/数值compat shim性质。

## 不支持/阻塞
未验证的反射/FFI/动态加载；未知第三方库语义；未固定并发和平台假设。

## 成熟度
本包仅SPECIFIED，原生适配与客户认证NOT_RUN。每种确切source/target/feature/environment组合独立晋级；不能用一个语言/DB测试结果覆盖整个矩阵。
