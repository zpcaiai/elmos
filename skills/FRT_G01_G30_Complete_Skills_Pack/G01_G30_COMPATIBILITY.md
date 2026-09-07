# G01–G30 Compatibility and Certificate Graph

```text
G01
  ↓
G02
  ↓
G03
  ↓
G04
  ↓
G05
  ↓
G06
  ↓
G07
  ↓
G08
  ↓
G09
  ↓
G10
  ↓
G11
  ↓
G12
  ↓
G13
  ↓
G14
  ↓
G15
  ↓
G16
  ↓
G17
  ↓
G18
  ↓
G19
  ↓
G20
  ↓
G21
  ↓
G22
  ↓
G23
  ↓
G24
  ↓
G25
  ↓
G26
  ↓
G27
  ↓
G28
  ↓
G29
  ↓
G30
```

## Certificate invalidation

- 上游Schema、Policy、Pack、Toolchain、环境或证书Digest变化时，下游证书必须变为`STALE`或`RETEST_REQUIRED`。
- G13–G17合计形成30条有向路径，任一路径的Route Pack撤销必须传播到G18–G30。
- G30只能聚合有效的G21–G29闭环证书和仍在Scope内的G01–G20基础证书。

## Required dependency modes

- `hard`: 缺失即停止。
- `compatibility`: 版本范围不匹配时执行显式迁移。
- `evidence`: 必须读取Fresh Evidence。
- `runtime`: 生产执行需要。
- `certification`: 签发更高等级证书需要。