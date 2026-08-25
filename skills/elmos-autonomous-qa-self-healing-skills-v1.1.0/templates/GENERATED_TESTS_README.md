# Generated Test Assets

## 产出信息

- Project ID: `<project-id>`
- Revision ID: `<revision-id>`
- Run ID: `<run-id>`
- Source Snapshot: `<snapshot-id>`
- Manifest: `manifests/test-artifact-set.json`

## 环境与依赖

列出固定运行时版本、包管理器、锁文件、服务依赖、浏览器/设备和测试数据要求。

## 运行入口

```bash
# 测试发现/列举
<discover-command>

# 最小冒烟
<smoke-command>

# 全部 Required 测试
<all-command>

# 指定测试类型
<type-command>

# 重放失败测试
<replay-command>
```

## 目录与需求映射

说明各测试目录、测试类型、关联需求和验证状态；详细文件级映射见 Manifest。

## 基线更新

视觉或性能基线不得自动无解释覆盖。记录更新原因、审批人、旧/新哈希和回归结果。

## 已知阻塞项

列出无法执行或未认证的测试及原因。不得把 BLOCKED 写成 PASSED。
