# 从 Struts/Servlet 迁移提炼出的仓库级通用能力

这条 Golden Route 的价值不只在 Java Web。它暴露了任何大型仓库转换都会遇到的本质问题，因此应抽象成 Elmos 的通用底座。

## 1. Repository Semantic Compiler

传统转换器的输入是源码，输出是源码；仓库级转换的输入应是：

```text
Source + Build + Config + Runtime + State + Effects + Deployment + Tests
```

输出也不只是目标代码，而是：

```text
Target Repository + Semantic Source Map + Verification Evidence + Certification
```

这要求 Elmos 建立“前端适配器—中间语义—后端生成器”的编译器式架构，而不是让每个迁移 Agent 直接读旧代码后自由生成。

## 2. Effective Configuration Recovery

大型仓库中真正生效的配置通常来自多层叠加：

```text
framework defaults
< packaged XML/properties
< build profile/resource filtering
< container descriptor
< JNDI
< environment/system properties
< runtime programmatic registration
```

Elmos 必须计算每个环境的 effective configuration，而不是只读取仓库中的一个 `web.xml` 或 `application.properties`。

通用化后，这一能力可以服务：

- Spring/Java EE 版本迁移；
- Kubernetes/Helm/Terraform 转换；
- 云厂商迁移；
- 多环境配置收敛；
- 数据库和消息系统切换。

## 3. Lifecycle Calculus

Struts1 RequestProcessor、Struts2 interceptor stack、Servlet Filter chain 都表明：框架行为由**有序阶段**组成。

统一表示：

```yaml
pipeline:
  - id: authentication
    phase: before
    order: 100
    condition: ...
    shortCircuit: FORBIDDEN
    effects: [...]
  - id: validation
    phase: before
    order: 300
    shortCircuit: INPUT_VIEW
  - id: handler
    phase: invoke
  - id: audit
    phase: after
    unwindOrder: reverse
```

这套 Lifecycle IR 可推广到：

- middleware/filter/interceptor；
- compiler pass；
- CI/CD pipeline；
- data processing pipeline；
- message consumer chain；
- workflow/agent tool chain。

## 4. Navigation Algebra

遗留 Web 框架中的返回值不是普通字符串，而是导航操作：

```text
Render(view)
Forward(uri)
Include(uri)
Redirect(uri, status)
Chain(action)
ErrorDispatch(code/exception)
Stream(content)
NoResult
```

这些操作影响 request attribute、response commit、URL、Cookie、状态码和后续过滤器。Elmos 应把它们定义为通用代数，而不是字符串映射。

## 5. State-Scope-Temporal Semantics

仓库行为不仅取决于函数输入，还取决于：

```text
page → request → action → session → application
thread → static → cache → database → external service
```

并且很多行为只有在请求序列中可见：

```text
GET form → POST invalid → POST valid → redirect → GET confirmation
```

因此 Elmos 需要：

- State Object IR；
- Scope/lifetime/serialization；
- Request Sequence State Machine；
- temporal assertions；
- 并发 tab/session 竞争模型。

此能力可推广到桌面应用、移动端状态迁移、工作流、微服务和事件系统。

## 6. Side-Effect Topology

“返回结果一样”不能证明行为等价。必须恢复：

- DB 行写入和事务；
- 消息 topic/queue；
- 文件；
- 邮件；
- 外部 HTTP；
- cache；
- audit/log；
- idempotency key；
- retry/compensation。

Elmos 应将所有副作用纳入一张图，并记录 order、count、commit/rollback、at-most/at-least/exactly-once 语义。

## 7. Evidence-Centered Reasoning

每条语义事实都要回答：

- 来自哪个文件/符号/配置？
- 在哪个环境有效？
- 是静态声明、运行观察还是推断？
- 置信度多少？
- 与哪些证据冲突？
- 哪个 extractor/model/version 产生？

这形成 Repository Evidence Graph。生成器、验证器和修复器必须消费同一证据图，避免不同 Agent 各自“重新理解”仓库。

## 8. Unknown Semantics as First-Class Debt

大型仓库必然存在：

- 反射；
- 动态脚本；
- 容器私有扩展；
- 加密配置；
- 缺少生产环境；
- 无法重放的外部服务；
- native code；
- 冲突证据。

成熟系统不能假装这些已解决。Elmos 必须维护 unknown ledger，并让它直接影响风险、测试预算和 E0–E5 认证。

## 9. Mixed-Framework Route Ownership

真实仓库通常不是纯 Struts 或纯 Servlet，而是多个框架共享 URL 空间。Elmos 必须计算：

```text
URL + HTTP Method + DispatcherType + Environment → Effective Owner
```

这成为：

- 转换单元切分依据；
- route shadowing 检测；
- Strangler 路由表；
- canary/rollback 路由控制；
- 目标系统漏路由/扩路由检测。

## 10. Compatibility Shim Synthesis

目标框架不总有一对一等价物。Elmos 应能生成受控 compatibility shim，但必须满足：

- 只承载框架语义，不承载业务逻辑；
- 有明确输入/输出契约；
- 有差分测试；
- 有性能成本和安全审计；
- 有移除条件；
- 不能掩盖 critical unknown。

## 11. Deterministic + Constrained Generative Rewrite

转换引擎分为三层：

1. **确定性结构改写**：AST、符号、XML/descriptor、依赖、构建；
2. **模板/adapter 生成**：由 IR 驱动；
3. **受约束模型修复**：只处理无法由规则覆盖的局部语义，必须有 evidence、tests、diff oracle 和预算。

任何模型 patch 都不是事实来源；运行证据才是。

## 12. Semantic Source Map

普通 source map 映射文本位置；Elmos 需要映射：

```text
legacy evidence
→ semantic IR node
→ migration decision
→ target code/config
→ tests
→ runtime observation
→ certification gate
```

它支持解释、影响分析、回归选择、自动修复、审计和精确回滚。

## 13. Differential Oracle Factory

差分验证不是单一 body diff，而是一组可配置 Oracle：

- HTTP protocol oracle；
- DOM/view oracle；
- session oracle；
- database oracle；
- transaction oracle；
- message/file/email/HTTP effect oracle；
- security oracle；
- concurrency/performance oracle；
- observability trace oracle。

每个 Oracle 需要显式 normalizer；normalizer 本身必须版本化和审计。

## 14. Sequence-Aware Contract Mining

Elmos 应从：

- 现有测试；
- access log；
- APM trace；
- JSP/form；
- 控制流；
- 数据约束；
- 风险模型

生成可重放的请求序列。只做 endpoint-level smoke test 无法覆盖 session、wizard、token 和事务恢复。

## 15. Conversion Wave Compiler

大型仓库不能做一次 giant commit。应以图切分 transformation units：

```text
module DAG
+ route ownership
+ shared session
+ DB transaction boundary
+ view dependency
+ side-effect sinks
+ risk
```

每个 wave 必须：

- 可独立构建；
- 可独立验证；
- 有明确 source map；
- 可回滚；
- 可恢复；
- 不破坏未迁移区域。

## 16. Certifiability as a Product Feature

Elmos 的商业竞争力不只是生成速度，而是能回答：

- 转换了什么？
- 为什么这样转？
- 哪些行为已证明等价？
- 哪些只是推断？
- 哪些仍未知？
- 是否可以生产切流？
- 出问题如何回滚？

因此 E0–E5 认证、Evidence Bundle 和 Unknown Ledger 必须成为产品一等输出。

## 17. Large-Repository Scaling

通用扩展策略：

- 先建索引和证据图，再按 transformation unit 按需加载；
- IR 与 artifact 分块存储；
- 内容寻址缓存；
- 依赖感知失效；
- 静态分析与测试并行；
- 共享模块使用 fencing；
- 通过 risk budget 决定模型和验证资源；
- 定期全量验证，平时影响面回归。

## 18. Harness-Native Long Task Semantics

每个长任务都必须具备：

- 环境所有权与权限快照；
- executor lease/fencing；
- 检查点；
- 暂停/恢复/取消；
- 幂等副作用；
- artifact hash；
- 重试预算；
- wall-clock ETA；
- token/compute/storage ledger；
- 版本化模型、prompt、tool 和 policy。

这些能力可直接复用于 Elmos 的其他语言转换和大型项目生成任务。
