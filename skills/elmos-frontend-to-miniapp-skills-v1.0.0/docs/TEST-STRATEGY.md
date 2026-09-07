# 测试策略

## 1. 测试金字塔

```text
Schema / pure rules / AST fixtures
        ↓
Source adapter contract tests
        ↓
IR and generator golden tests
        ↓
Platform component and API contract tests
        ↓
Official native builds
        ↓
Semantic differential tests
        ↓
Visual / performance / privacy / security
        ↓
Preview / sandbox / controlled real-device validation
```

编译通过只是中间门禁，不是功能等价证明。

## 2. Fixture 体系

每个源框架至少维护：

- minimal app；
- router/navigation；
- local/global state；
- form；
- async network；
- lifecycle cleanup；
- error/empty/loading；
- style/theme/responsive；
- third-party component；
- unsupported behavior；
- permission denial；
- recovery/idempotency。

推荐 golden projects：

| Fixture | 目的 |
|---|---|
| vue3-todo | 最小闭环、Pinia、表单、路由 |
| react-commerce | Hooks、Router、状态、订单和分享 |
| flutter-dashboard | Widget、Navigator、Provider、图表和动画 |
| mixed-monorepo | 多 package、多框架和共享库 |
| native-miniapp-port | 平台间既有小程序迁移 |
| adversarial-repo | 不可信脚本、密钥、巨型文件和路径攻击 |

## 3. Source Analyzer Tests

### AST 精度

- 节点类型；
- 类型信息；
- 源位置；
- import/export；
- 动态表达式；
- 错误恢复。

### 覆盖率

```text
parsed_source_files / eligible_source_files
```

必须为 100%，或每个失败文件都有结构化错误。不得把未解析文件从分母删除。

### 确定性

相同输入、规则和工具版本重复运行：

- 节点 ID 一致；
- 排序一致；
- JSON 规范化哈希一致；
- trace 一致。

## 4. IR Tests

- Schema validation；
- 引用完整性；
- 无悬空 route/component/state；
- 生命周期顺序；
- 状态读写类型；
- capability reference；
- source trace 覆盖；
- v1→vNext 迁移；
- round-trip；
- unknown field policy；
- large graph 性能。

## 5. Generator Tests

### Golden snapshot

对规范化输出做 snapshot，但不得只靠 snapshot。还需：

- parse generated project；
- route/config cross-check；
- import resolution；
- static type/lint；
- platform API allowlist；
- no-secret scan；
- deterministic regeneration；
- trace completeness。

### Mutation tests

对生成规则注入：

- 删除事件；
- 交换生命周期；
- 忽略 cleanup；
- 错误单位；
- 错误路由参数；
- 固定支付成功；
- 泄露 secret。

测试必须能捕获这些 mutation，否则门禁不足。

## 6. 官方构建测试

每个平台 build adapter 输出：

```json
{
  "platform": "wechat",
  "tool": "...",
  "tool_version": "...",
  "command_fingerprint": "...",
  "exit_code": 0,
  "artifact_sha256": "...",
  "started_at": "...",
  "finished_at": "...",
  "log_artifact": "..."
}
```

构建环境应固定镜像、系统依赖和工具版本。无法自动化的官方 IDE 步骤必须输出可操作的人工验证清单和 `blocked`，不能写 `passed`。

## 7. 语义差分测试

### 场景定义

每个场景包含：

- 初始状态；
- 用户动作；
- 模拟时间；
- mock 网络和返回；
- 预期路由；
- 预期状态；
- 预期请求；
- 预期存储；
- 预期错误；
- 清理与结束状态。

### Trace 示例

```json
[
  {"t": 0, "type": "route.enter", "value": "/cart"},
  {"t": 1, "type": "event.tap", "target": "checkout"},
  {"t": 2, "type": "request.start", "operation": "createOrder"},
  {"t": 3, "type": "state.write", "path": "order.status", "value": "created"}
]
```

比较维度：

- 值；
- 次数；
- 顺序；
- 延迟预算；
- 错误类型；
- 副作用；
- 清理。

平台随机 ID、时间戳或非业务字段只能通过明确 normalizer 归一化。

## 8. 视觉测试

### 固定条件

- 数据；
- 时间；
- locale；
- theme；
- 字体；
- viewport；
- pixel ratio；
- animation state；
- network；
- safe area。

### 指标

- pixel similarity；
- structural boxes；
- text wrapping；
- overflow；
- clipped controls；
- spacing/token；
- key-region weighted score。

默认阈值 0.95，关键支付、表单、导航区域应设置更高或零严重差异门禁。

### Mask 治理

每个 mask 记录：

- 页面；
- 矩形；
- 原因；
- owner；
- expiry；
- 批准；
- 是否影响关键区域。

过期 mask 自动失败。

## 9. 性能测试

不要硬编码跨项目统一毫秒数。conversion-request 定义：

- 源基线；
- 目标预算；
- 设备/模拟器；
- 样本数；
- warmup；
- percentile；
- 允许回归比例。

至少测：

- 冷启动；
- 首屏；
- 页面切换；
- 长列表滚动；
- 内存；
- 包体积；
- 网络并发；
- WebSocket/媒体稳定性。

环境不可比时输出 `unknown`。

## 10. 隐私与安全测试

- secret regex + entropy；
- AST data-flow；
- 权限调用位置；
- consent flow；
- third-party SDK inventory；
- callback signature；
- replay；
- order idempotency；
- URL/domain allowlist；
- path traversal；
- unsafe eval；
- command injection；
- source repository script isolation；
- log redaction；
- artifact access control。

## 11. 自动修复测试

每次修复：

1. 重现原 finding；
2. 应用最小 patch；
3. 运行最小失败测试；
4. 运行受影响的完整门禁；
5. 检查新 finding；
6. 保存 rollback；
7. 检查 patch 指纹。

测试自动修复本身：

- 达到最大三次停止；
- 重复补丁停止；
- 不降低阈值；
- 不扩大权限；
- 不把真实调用替换为固定成功；
- 中断后可恢复；
- rollback 可用。

## 12. 发布前测试矩阵

| 层级 | 微信 | 支付宝 | 抖音 | 小红书 |
|---|---:|---:|---:|---:|
| Schema/静态 | 必须 | 必须 | 必须 | 必须 |
| 官方构建 | 必须 | 必须 | 必须 | 必须或可验证阻断 |
| 关键流程 | 必须 | 必须 | 必须 | 必须 |
| 视觉 | 必须 | 必须 | 必须 | 必须 |
| 权限拒绝 | 必须 | 必须 | 必须 | 必须 |
| 弱网/超时 | 必须 | 必须 | 必须 | 必须 |
| sandbox 商业流程 | 适用时 | 适用时 | 适用时 | 适用时 |
| 真机/预览 | 发布前 | 发布前 | 发布前 | 发布前 |
| 审核材料 | 上传前 | 上传前 | 上传前 | 上传前 |

## 13. 测试结果状态

- `passed`：已执行且满足阈值；
- `failed`：已执行且不满足；
- `blocked`：外部条件阻止；
- `unknown`：证据不足或环境不可比；
- `skipped`：不适用且有理由。

只有 `passed` 才能满足门禁。
