# 平台能力矩阵与注册表规则

本文件是能力注册表的**种子设计**，不是永久事实表。平台 API、账户权限、类目、地区、主体资质、审核和工具链会变化；生产执行必须读取版本化 `platform-profile` 与 `capability-registry`，并记录 `verified_at` 和官方资料。

## 1. A–E 兼容等级

| 等级 | 含义 | 可自动生成 | 是否需要审批 |
|---|---|---:|---:|
| A | 目标平台存在原生等价能力，语义与测试可证明 | 是 | 普通代码审批 |
| B | 通过受控 adapter 或组合组件可等价实现 | 是 | 高风险能力可能需要 |
| C | 需要重新设计页面、交互、数据模型或服务端 | 先生成计划 | 是 |
| D | 取决于业务选择、资质、账户权限或平台当前状态 | 否 | 是 |
| E | 目标平台当前无法实现或被政策禁止 | 否 | 必须决定移除/替代/放弃目标 |

`permission-dependent`、`backend-required`、`review-sensitive` 是附加标签，不替代 A–E。

## 2. 源框架覆盖

| 源类型 | 解析策略 | 主要高风险点 |
|---|---|---|
| Vue 2/3 | SFC + TypeScript AST + template/style AST | 动态组件、Teleport、DOM 指令、运行时模板 |
| React | TS/JS AST + JSX/TSX + Hook/状态图 | Portal、DOM、CSS-in-JS、SSR、动态 Hook |
| Flutter | Dart analyzer + Widget/State/Nav 重建 | 原生插件、Platform Channel、Shader、CustomPainter |
| H5/TS/JS | HTML/CSS/JS AST + browser API inventory | DOM、Service Worker、浏览器扩展、复杂 Web API |
| Taro/uni-app | 识别其抽象层并恢复语义 | 条件编译、插件、目标平台分支 |
| 既有小程序 | 平台 AST + API/配置分析 | 平台专属能力、隐式全局状态、历史兼容代码 |

## 3. 能力类别种子矩阵

下表中的结论是规划起点，真正的 `classification` 必须结合实际调用、账户和当前官方资料解析。

| 能力类别 | 微信 | 支付宝 | 抖音 | 小红书 | 默认处理 |
|---|---|---|---|---|---|
| 页面/组件/路由 | A/B | A/B | A/B | A/B | Semantic IR → 平台页面和组件 |
| 本地状态/存储 | A/B | A/B | A/B | A/B | StoragePort；配额从 profile 读取 |
| 网络/上传下载 | A/B | A/B | A/B | A/B | 域名、TLS、超时和权限检查 |
| 登录/用户身份 | B + 权限 | B + 权限 | B + 权限 | B/D + 权限 | IdentityPort + 服务端换票 |
| 获取手机号/敏感身份 | D + 审核 | D + 审核 | D + 审核 | D + 审核 | 最小权限、用途说明、人工确认 |
| 支付/退款 | D + 服务端 | D + 服务端 | D + 服务端 | D + 服务端 | CommercePort；逐平台模式验证 |
| 分享/场景入口 | B | B | B | B/D | SharePort；场景参数专项测试 |
| 商品/订单/电商 | B/D | B/D | B/D | B/D | 领域模型 + 平台 adapter |
| 内容/视频/直播 | C/D | C/D | B/D | B/D | 依赖类目、资质和内容政策 |
| 地图/定位 | B/D | B/D | B/D | D | 能力/权限/地图 SDK 动态解析 |
| 相机/相册/媒体 | B/D | B/D | B/D | B/D | 用户触发、权限降级、媒体测试 |
| 蓝牙/NFC/设备 | D | D | D | D/E | 读取 profile；无能力时不得 stub |
| WebSocket/实时 | B | B | B | B/D | 生命周期、重连与后台策略 |
| 文件系统 | B/C | B/C | B/C | B/C | 沙箱路径和配额适配 |
| WebView | D | D | D | D | 默认禁止；仅明确批准 |
| DOM/Portal/Shadow DOM | C/E | C/E | C/E | C/E | 原生组件重构 |
| Service Worker/PWA | E/C | E/C | E/C | E/C | 服务端或平台后台能力重构 |
| Flutter CustomPainter | B/C | B/C | B/C | B/C | 优先原生/局部 Canvas |
| Flutter Platform Channel | C/D/E | C/D/E | C/D/E | C/D/E | 插件能力逐项解析 |
| 推送/订阅消息 | D | D | D | D | 权限、模板、用户授权和服务端 |
| 分析/埋点/崩溃 | B/D | B/D | B/D | B/D | 第三方 SDK 与隐私披露检查 |

## 4. Registry Entry

使用 `schemas/capability-registry-entry.schema.json`。最低字段：

```yaml
id: commerce.payment.request
category: commerce
source_patterns:
  - framework: vue
    symbol: paymentService.pay
targets:
  wechat:
    support: decision
    runtime: hybrid
    permission:
      - merchant-account
      - platform-capability
    review_risk: high
    adapter: wechat-commerce
    required_tests:
      - order-idempotency
      - callback-signature
  xiaohongshu:
    support: decision
    runtime: hybrid
    permission:
      - professional-account
      - platform-capability
    review_risk: high
    adapter: xhs-commerce
fallback:
  strategy: backend-order-plus-approved-checkout
verified_at: "2026-08-19"
source_refs:
  - "official-doc-reference-id"
```

## 5. 组件映射规则

映射键不能只用组件名，应组合：

```text
semantic_role
+ interaction_contract
+ state_model
+ props/events/slots
+ layout_constraints
+ accessibility
+ target_platform
+ platform_profile_version
```

示例：

```yaml
source:
  framework: react
  symbol: Select
semantic_role: single-select
requirements:
  searchable: true
  async_options: true
  clearable: true
targets:
  wechat:
    classification: B
    strategy: generated-composite
    tests:
      - keyboard-or-focus-alternative
      - async-options
      - clear-selection
```

## 6. 漂移管理

能力注册表更新流程：

1. 发现官方文档、CLI、审核或账户行为变化。
2. 创建新的 registry/profile revision。
3. 保存资料、验证日期和变更说明。
4. 运行所有受影响 capability fixtures。
5. 对活跃转换任务标记 `profile-stale`。
6. 只对新 attempt 使用新 revision；旧证据保持不可变。
7. 高风险能力变更需要审批。

禁止直接覆盖历史 registry 后仍声称旧任务使用的是当前规则。
