# 换 profile 到类方法能买到多少：实测 **21 个，全是空壳**

2026-08-26（call-lever 之后同日）。仪器：`.ai/measurement-2026-08-26/method_profile_headroom.py`。
证据：`method-profile.json`。语料与前三轮完全相同（20 个真实 PyPI 项目，583 文件 / 7.06 MB）。

## 为什么测这个

headroom 的结论是：`typed-pure-function-v1` 是**自由函数** profile，而
**4,128 个 subject（占全体 25.7%）是类方法**，在任何类型或函数体规则被查阅之前就以
`NESTED_SYMBOL` 被拒。这是 profile 之外最大的一整块，所以「把 profile 扩到方法」
是显而易见的下一个提案。

它也是**还没被验证过**的提案。本周每一个未验证的投影回来都比声称的小，六次全是。所以：验。

## 方法：提升（lift），让真分析器裁

一个方法，如果第一个参数是 `self`/`cls` 而函数体从不引用它，那它机械地就是一个自由函数；
`@staticmethod` 本来就是。把它挪到模块顶层（**保留模块其余部分**，这样它引用的全局名
仍然解析得到），当前分析器就能直接判。提升后 READY，就是方法 profile 会接纳的；
其他结果，就是方法 profile **还得再打败**的那堵墙。

**真的用到 `self` 的方法只统计、不提升。** `self` 是对象类型，而规范类型只有
`int/float/bool/str`。接纳它们不是放宽 profile，**是换一套类型系统**——把这句话说出来
正是这次测量的意义。接收者名字不是 `self`/`cls` 的（239 个），一律拒绝猜测。

## 结果

```
语料里的方法定义 4,160
  instance-method 2,402 / dunder 1,410 / property 209 / classmethod 79 / staticmethod 60

3,638 (87.4%) 无法提升
    3,399  真的用到 self/cls   ← 这不是 profile 问题，是类型系统问题
      239  接收者不叫 self/cls，拒绝猜测

  522 可提升 → 真分析器裁决
      501  BLOCKED_AFTER_LIFT
       21  READY_AFTER_LIFT     ← 全部收益
```

提升之后死在哪：

```
PYTHON_PARAMETER_TYPE_REQUIRED   347
PYTHON_RETURN_TYPE_REQUIRED      122   ← 合计 469/501 = 93.6% 死在类型墙
PYTHON_UNSUPPORTED_STATEMENT      11
PYTHON_UNSUPPORTED_EXPRESSION      9
PYTHON_UNANNOTATED_ASSIGNMENT      6
FUNCTION_BODY_IS_ONLY_DOCUMENTATION 3
ASYNC_FUNCTION                     2
UNDECLARED_NAME                    1
```

**第三次是同一堵墙。** 类型面自己 ≈0、拆掉调用墙 87% 落在类型墙、现在换 profile
93.6% 落在类型墙。三根杠杆各自独立地撞在同一个地方。

## 那 21 个是什么

按类别：**dunder 15、instance-method 6、staticmethod 0、classmethod 0、property 0。**

`@staticmethod` 这一栏最能说明问题：**60 个全部可提升——它们本来就是自由函数——
READY 是 0。** 「方法这个形状」根本不是障碍，障碍从来都是类型和函数体。

按函数体形状：**21 个里 20 个是「零参数 + 单条 `return <字面量>`」。**

```
UnprocessedParamType.__repr__   params=0   return 'UNPROCESSED'
StringParamType.__repr__        params=0   return 'STRING'
DateTime.__repr__               params=0   return 'DateTime'
IntParamType.__repr__           params=0   return 'INT'
FloatParamType.__repr__         params=0   return 'FLOAT'
BoolParamType.__repr__          params=0   return 'BOOL'
UUIDParameterType.__repr__      params=0   return 'UUID'
Expr.can_assign                 params=0   return False
NSRef.can_assign                params=0   return True
Undefined.__str__               params=0   return ''
Undefined.__len__               params=0   return 0
Undefined.__bool__              params=0   return False
Undefined.__repr__              params=0   return 'Undefined'
_MissingType.__repr__           params=0   return 'missing'
_MissingType.__reduce__         params=0   return 'missing'
InfinityType.__repr__           params=0   return 'Infinity'
NegativeInfinityType.__repr__   params=0   return '-Infinity'
Empty._generateDefaultName      params=0   return 'Empty'
_ErrorStop._generateDefaultName params=0   return '-'
MockRequest.is_unverifiable     params=0   return True
Environment.join_path           params=2   return template      ← 恒等穿透
```

**没有一个在计算任何东西。** 20 个返回字面量，第 21 个把自己的参数原样返回。
这和「只差一个注解」那 5 个是同一个故事：**子集恰好接纳的，正是什么都不做的那些函数。**

## 数字

准入从 **1/16,046 → 22/16,046（0.14%）**。用 25.7% 的语料换 0.13 个百分点。

## 对「dunder 15 个」这一栏的保留

我不把它算进任何乐观口径。`__repr__` / `__len__` / `__bool__` 是**语言协议调用的**，
不是按名字调用的；把 `__repr__` 提升成自由函数、再声称「这是一个可转换单元」，
和把 `@property` 当可调用单元一样可疑。**所以工具把 `ready_by_kind` 单独列出来，
不折进一个好看的总数里。** 真正站得住的「自由函数形状的实例方法」只有 **6 个**，
其中 3 个还是 `return <字面量>`。

## 负控制

9 个合成方法，覆盖全部分类，逐条落在预期：纯静态方法 → READY；静态方法体内是 `%`
→ BLOCKED 且带 `PYTHON_FLOORED_MODULO_OUTSIDE_CERTIFIED_SUBSET`；静态方法无注解
→ BLOCKED `PARAMETER_TYPE_REQUIRED`；用 `self` 的 → 不提升；不用 `self` 的实例方法
→ READY；不用 `cls` 的 classmethod → READY；`__eq__(self, other)` → BLOCKED（`other` 无注解）；
**接收者叫 `this` 的 → 拒绝猜测**。

## 结论

三根杠杆到此全部验完，全部实测：

| 提案 | 镜像/直觉说 | 真分析器说 |
|---|---|---|
| 扩规范类型（bytes / `T\|None` / `list[str]` / `-> None`） | 有收益 | **0** |
| 补类型注解（`TYPE:MISSING`） | 11 | **5，且全部多解** |
| 跨单元调用纯度证明（`CALL:user-function`） | +18 | **0（结构性）** |
| 换 profile 到类方法（25.7% 的语料） | 最大的一块 | **21，20 个是 `return <字面量>`** |

**没有一个单点改动能把这条线从 0.1% 量级抬起来。** 三次独立的测量都指向同一处：
**类型墙**（93.6% / 87% / 上界 12）。而类型墙背后是一个已经验证过的事实——
在分析器最有可能推断成功的 5 个点上，答案不唯一（[[ir-local-bindings]] 拒绝推断的
设计决定因此站得住）。

真正的选择不在「再放宽一条规则」这个层面上，而是：**要么接受这条线的定位是
「窄子集上的可证明转换」而不是「通用转换」，要么把 `self` 的对象类型接进类型系统——
后者不是放宽 profile，是另一个工程。** 这个判断现在有四组实测数据托着，不是意见。
