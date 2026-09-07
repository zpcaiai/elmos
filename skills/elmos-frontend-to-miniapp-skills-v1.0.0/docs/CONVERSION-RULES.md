# 转换规则规范

## 1. 规则优先级

```text
security/privacy hard policy
> explicit conversion-request policy
> target platform profile
> capability registry
> project-specific approved override
> generic mapping rule
> heuristic
```

低优先级规则不得覆盖高优先级安全与隐私策略。

## 2. 规则 DSL

建议规则采用声明式 YAML，经 Schema 验证后编译为确定性决策图。

```yaml
id: react.effect.to-page-lifecycle.v1
version: 1.0.0
match:
  source_framework: react
  ir_kind: effect
  predicates:
    - has_cleanup: true
    - scope: page
target:
  platform: "*"
action:
  strategy: lifecycle-binding
  on_mount: page.show
  on_cleanup: page.hide-or-unload
constraints:
  - preserve_dependency_set
  - cancel_pending_async
classification: B
tests:
  - effect-runs-once-per-dependency-change
  - cleanup-before-destroy
```

每条规则至少包含：

- 唯一 ID 和语义版本；
- 适用源/目标/IR 节点；
- predicate；
- action；
- 分类；
- 风险与限制；
- required tests；
- 来源和更新时间；
- 冲突优先级。

## 3. 冲突解析

同一节点命中多条规则时：

1. 先按 hard policy；
2. 再按 specificity；
3. 再按显式优先级；
4. 仍冲突则输出 D，不任意选择；
5. 冲突必须进入 mapping decisions。

不得依赖文件遍历顺序决定结果。

## 4. Vue 规则

必须覆盖：

- `v-if/v-else` 条件结构；
- `v-for` key 稳定性；
- `v-model` 的 prop/event 契约；
- props、emits、slot、provide/inject；
- computed 的依赖与缓存语义；
- watch 的 deep/immediate/flush 语义；
- app/page/component 生命周期；
- Router 参数、守卫、懒加载；
- Vuex/Pinia 模块、action 和持久化；
- scoped style 和动态 class/style；
- Teleport、DOM directive 和动态组件风险。

## 5. React 规则

必须覆盖：

- 函数组件、类组件和组合模式；
- state/reducer/context；
- Hook 调用顺序；
- effect 依赖和 cleanup；
- memo/callback 的语义边界；
- Router 与页面栈；
- Redux/Zustand/MobX；
- controlled/uncontrolled form；
- Portal、DOM、browser event；
- CSS Modules、CSS-in-JS 与 utility class；
- Suspense/SSR 专属行为的重构。

## 6. Flutter 规则

必须覆盖：

- Widget constructor 与 child/children；
- StatelessWidget/StatefulWidget；
- build dependency；
- initState/didChangeDependencies/dispose；
- Navigator/Router；
- Provider/Riverpod/Bloc/GetX；
- constraints、Flex、Stack、ListView、GridView；
- Theme、MediaQuery、安全区和本地化；
- GestureDetector、Form、Focus；
- AnimationController/Tween；
- CustomPainter；
- Platform Channel 和插件。

禁止规则：

```text
Flutter page → screenshot
Flutter application → full-page Canvas
unknown plugin → ignored
```

## 7. 样式规则

- 先解析级联和作用域，再转换。
- 设计 token 必须独立提取。
- 单位转换只能执行一次。
- 不支持选择器必须进入报告。
- 响应式规则按设备矩阵验证。
- 字体缺失不得无提示回退导致布局变化。
- 修复不得用全局 `!important` 掩盖问题。

## 8. 平台能力规则

平台调用必须经过端口或 adapter，禁止业务代码直接散落：

```ts
platform.identity.login()
platform.navigation.open(route)
platform.commerce.createOrder(input)
platform.share.shareCard(card)
```

adapter 返回统一领域错误，而不是把平台错误码直接扩散到业务层。原始平台错误应保留在 evidence/debug metadata 中。

## 9. 不支持项规则

每个不支持项必须包含：

```json
{
  "source_location": "...",
  "feature": "...",
  "classification": "C|D|E",
  "impact": "...",
  "alternatives": [],
  "decision_owner": "...",
  "blocking": true
}
```

禁止：

- 删除源文件或路由后不报告；
- 生成空函数；
- 固定返回成功；
- 用 TODO 注释标记为已实现；
- 跳过测试后把状态写为 passed。

## 10. 规则测试

每条规则至少有：

- positive fixture；
- negative fixture；
- ambiguity/conflict fixture；
- deterministic snapshot；
- trace assertion；
- required test generation assertion。

高风险规则还需：

- security/privacy case；
- permission denied case；
- timeout/retry case；
- rollback case。
