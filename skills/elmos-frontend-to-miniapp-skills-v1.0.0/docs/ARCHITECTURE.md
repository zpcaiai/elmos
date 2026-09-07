# Elmos 前端转小程序生产架构

## 1. 目标与非目标

### 目标

Elmos 应把 Vue、React、Flutter、H5、Taro、uni-app 或既有小程序转换为微信、支付宝、抖音和小红书的原生小程序项目，并提供：

- 仓库级静态分析；
- 统一 Semantic IR；
- 平台能力与权限解析；
- 原生代码生成；
- 官方工具链构建；
- 功能、视觉、性能、隐私和安全验证；
- 有界自动修复；
- 中断恢复、成本记录和证据归档；
- 分级上传、审核与发布。

### 非目标

- 不承诺未经资质、权限或审核即可使用平台能力。
- 不把 WebView、截图或全页面 Canvas 包装称为原生转换。
- 不保证所有浏览器、Flutter 原生插件或平台专属能力存在严格等价实现。
- 不把“代码已生成”视为“迁移已完成”。
- 不自动替代需要业务、法律、隐私、支付或发布授权的人工决策。

## 2. 总体流水线

```text
Conversion Request
        │
        ▼
┌─────────────────────────────┐
│ 1. Discovery & Inventory    │
│ repo snapshot / framework   │
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│ 2. Source Semantic Analysis │
│ Vue / React / Flutter / ... │
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│ 3. Versioned Semantic IR    │
│ UI/state/event/style/trace  │
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│ 4. Conversion Planning      │
│ capability/component/style  │
│ lifecycle/dependency        │
└──────┬────────┬────────┬────┘
       ▼        ▼        ▼
 WeChat     Alipay    Douyin    Xiaohongshu
 Adapter    Adapter   Adapter   Adapter
       └────────┴────────┴───────────┘
                       ▼
┌─────────────────────────────┐
│ 5. Native Code Generation   │
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│ 6. Build & Validation       │
│ semantic / visual / privacy │
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│ 7. Bounded Auto Repair      │
│ upstream-first / rollback   │
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│ 8. Evidence & Approval      │
│ build / test / cost / risk  │
└──────────────┬──────────────┘
               ▼
        Preview / Upload /
        Review / Release
```

## 3. 关键架构原则

### 3.1 源框架与目标平台解耦

源适配器只负责恢复语义，目标适配器只负责消费 IR。不得形成 `Vue → WeChat`、`React → Alipay` 这类成对硬编码转换器，否则规则数量会随输入×输出矩阵爆炸。

### 3.2 IR 是行为模型，不是通用 AST

IR 应表达：

- 页面、组件、属性、插槽和组合关系；
- 状态读写、派生值、订阅与持久化；
- 事件顺序、冒泡、默认行为和异步副作用；
- app/page/component 生命周期；
- 路由、参数、页面栈和入口场景；
- 设计 token、布局约束、样式和动画；
- 平台能力、权限、隐私数据流和后端依赖；
- 源位置、规则版本、目标文件和测试观察点。

IR 不应保留大量仅对某一源框架有意义的语法，也不应提前写入某一目标平台的文件格式。

### 3.3 版本化能力注册表

平台能力不是布尔值。每个能力至少包含：

```yaml
support: native | adapter | redesign | decision | unsupported
permission: none | account | category | user-consent | qualification
runtime: client | server | hybrid
review_risk: low | medium | high
fallback: <named strategy>
verified_at: 2026-08-19
source_refs: [...]
```

存在 API 不等于当前开发账户有权限；文档中存在能力也不等于所有地区、类目或主体均可使用。

### 3.4 原生优先，降级受控

默认策略：

1. 目标平台原生组件/API；
2. 生成受测组合组件；
3. 共享业务核心 + 平台适配器；
4. 局部 Canvas、后端渲染或其他替代；
5. 经明确批准的 WebView；
6. 不支持并阻断。

第 4–5 级必须由 capability finding 和审批记录支撑。禁止自动把复杂页面整页 Canvas 化。

### 3.5 上游优先修复

修复顺序：

1. 源分析规则；
2. IR 模型或迁移；
3. 能力/组件/样式映射规则；
4. 平台适配器；
5. 代码生成模板；
6. 最后才是目标生成文件的局部补丁。

任何直接修改生成文件的有效修复都应回写到规则或模板，否则下一次生成会丢失。

### 3.6 每个结论必须有证据

“已支持”“已编译”“已等价”“可发布”分别需要不同证据：

- 已支持：能力解析和实现路径；
- 已编译：官方工具链命令、版本、退出码和产物哈希；
- 已等价：关键流程差分与视觉结果；
- 可发布：隐私、安全、资质、审核材料和审批；
- 已发布：平台回执、版本、时间和回滚点。

## 4. 运行时服务边界

建议 Elmos 将转换能力拆成以下服务/worker：

| 服务 | 职责 | 推荐运行时 |
|---|---|---|
| conversion-orchestrator | 状态机、检查点、成本、恢复、审批 | Elmos 现有任务编排层 |
| repository-inventory | 仓库扫描、依赖和入口清单 | TypeScript/Rust |
| vue-analyzer | Vue AST/SFC 分析 | TypeScript |
| react-analyzer | TSX/Hook/Router 分析 | TypeScript |
| flutter-analyzer | Dart analyzer、Widget/State 图 | Dart CLI |
| ir-core | Schema、IR 版本、确定性序列化 | TypeScript；性能路径可 Rust |
| rule-engine | mapping/capability/style/lifecycle 规则 | TypeScript/Rust |
| target-generators | 四个平台代码生成 | TypeScript |
| build-workers | 平台工具链隔离执行 | 独立容器/VM |
| validation-workers | 差分、视觉、性能和安全 | TypeScript/Python |
| evidence-service | 证据、哈希、报告和签署 | Java/TypeScript |
| credential-broker | 短期凭证、审批和审计 | Elmos 安全控制面 |

Flutter analyzer 应作为独立 Dart 工具输出 JSON，而不是要求 TypeScript 直接完整理解 Dart 类型系统。

## 5. 运行目录与不可变产物

```text
runs/<run-id>/
├── request/
│   ├── conversion-request.json
│   └── source-revision.json
├── discovery/
├── analysis/
│   ├── vue/
│   ├── react/
│   └── flutter/
├── ir/
│   ├── semantic-ir.json
│   └── trace-index.json
├── plans/
│   ├── capability-resolution.json
│   ├── component-mapping-plan.json
│   ├── state-lifecycle-plan.json
│   ├── style-plan.json
│   └── dependency-migration-plan.json
├── platforms/
│   ├── wechat/
│   ├── alipay/
│   ├── douyin/
│   └── xiaohongshu/
├── tests/
├── repairs/
├── evidence/
├── logs/
└── state.json
```

阶段产物在通过后视为不可变。后续修复创建新 attempt 或新 revision，不原地改写旧证据。

## 6. 状态机与恢复

建议状态：

```text
RECEIVED
→ INVENTORIED
→ SOURCE_ANALYZED
→ IR_VALIDATED
→ PLANNED
→ GENERATED
→ BUILT
→ SEMANTIC_TESTED
→ VISUAL_TESTED
→ PRIVACY_SECURITY_TESTED
→ REPAIRED (optional loop)
→ EVIDENCE_READY
→ APPROVED
→ UPLOADED
→ UNDER_REVIEW
→ RELEASED
```

终止状态：

- `BLOCKED`
- `FAILED`
- `CANCELLED`
- `SUPERSEDED`

每个状态转换记录：

- 输入 artifact 哈希；
- 输出 artifact 哈希；
- skill/task ID；
- toolchain 和规则版本；
- tenant/run/attempt；
- 系统墙钟开始与结束时间；
- token、模型、平台构建和基础设施成本；
- 是否可重试、下一恢复点和副作用回执。

## 7. 幂等与缓存

### 幂等键

```text
sha256(
  skill_name +
  skill_version +
  normalized_input_hashes +
  conversion_policy_hash +
  capability_registry_version +
  platform_profile_version +
  toolchain_version
)
```

### 缓存层

- 文件内容 CAS；
- AST 与依赖图缓存；
- IR 子图缓存；
- mapping 规则结果缓存；
- 平台生成文件缓存；
- 官方构建缓存；
- 测试基线与截图缓存。

缓存命中必须验证产物哈希。规则、Schema、平台 profile、工具链或请求策略变化都应使相关层失效。

## 8. 多租户隔离

每个租户和任务使用独立 workspace、缓存命名空间、凭证 scope 和构建沙箱。禁止：

- 跨租户复用未脱敏源代码；
- 把一个租户的 preview/upload 凭证用于另一个租户；
- 在共享缓存中存储明文 secret；
- 把任务日志暴露给其他租户；
- 让平台回调缺失 tenant/app 绑定。

可共享的只有公开规则、平台 profile、无客户代码的代码生成模板和经过内容寻址且授权允许的公共依赖缓存。

## 9. 代码共享策略

生成项目可采用：

```text
generated-project/
├── shared/
│   ├── domain/
│   ├── application/
│   ├── schemas/
│   └── services/
└── platforms/
    ├── wechat/
    ├── alipay/
    ├── douyin/
    └── xiaohongshu/
```

共享层不得导入平台全局对象。所有平台调用通过端口：

```ts
interface MiniAppPlatform {
  identity: IdentityPort;
  storage: StoragePort;
  network: NetworkPort;
  navigation: NavigationPort;
  share: SharePort;
  commerce?: CommercePort;
  media?: MediaPort;
}
```

当平台原生体验比共享率更重要时，可生成平台专属页面，但仍应共享领域模型和服务 contract。

## 10. 可扩展性

新增源框架需要实现：

- detector signals；
- parser/analyzer；
- source facts schema；
- IR lowering；
- fixture 与差分基线。

新增目标平台需要实现：

- platform profile；
- capability entries；
- component/style/lifecycle mappings；
- generator；
- official build adapter；
- test harness；
- privacy/review checklist。

不得修改现有源分析器来硬编码新目标平台。

## 11. 生产就绪判定

只有全部适用门禁通过并有当前证据时，结论才可为 `ready`。以下情况必须为 `not-ready` 或 `blocked`：

- 任何关键流程未执行；
- 官方构建未通过；
- C/D/E 项未披露或未批准；
- 真实密钥出现在客户端；
- 权限、隐私或支付风险未关闭；
- 视觉修复导致语义回归；
- 证据哈希不一致；
- 平台资质、账户权限或审核条件未知。
