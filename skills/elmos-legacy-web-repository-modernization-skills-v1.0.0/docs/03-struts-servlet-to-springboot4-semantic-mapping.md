# Struts 1 / Struts 2 / Servlet → Spring Boot 4 深层语义映射

## 1. Struts 1

### 1.1 请求流水线

`RequestProcessor.process()` 的关键顺序应恢复为：

```text
multipart wrap
→ path selection
→ locale
→ content type / no-cache
→ custom preprocess
→ one-time cached messages
→ action mapping
→ role check
→ ActionForm acquire/store
→ reset + populate
→ validate
→ mapping forward/include short-circuit
→ Action instance acquire
→ Action.execute
→ exception mapping
→ ActionForward resolution
```

任何自定义 `RequestProcessor` override 都可能改变上述阶段、短路或副作用。

### 1.2 Action 生命周期

Struts1 可能缓存并复用 Action 实例。目标 Spring Controller 默认也是 singleton，但这不意味着可机械映射：

- legacy Action 共享 mutable field 可能已存在竞态；
- Spring 注入新依赖后可能改变线程安全；
- ActionServlet reference、static cache、synchronized 区域需要审计；
- 目标可选择 stateless singleton、request-scope adapter 或显式状态外移。

### 1.3 ActionForm

必须精确保持：

- request/session scope；
- `reset()` 在参数 populate 前；
- session-scoped checkbox 未提交时的 false/reset；
- 类型转换和 population error；
- `validate()` 在 Action 执行前；
- validation failure 的 input forward、messages、request/session 状态；
- multipart handler finish/rollback 生命周期。

建议目标构造：

```text
DTO / @ModelAttribute
+ LegacyFormLifecycleBinder
+ Converter/Formatter
+ Validator
+ BindingResult adapter
```

而不是单纯 DTO。

### 1.4 RequestProcessor hook 映射

| Struts1 语义 | Spring 候选 | 选择条件 |
|---|---|---|
| 低层 request/encoding | Filter/OncePerRequestFilter | 在 DispatcherServlet 前 |
| route 解析后的前置检查 | HandlerInterceptor | 需要 handler metadata |
| 参数/对象构造 | HandlerMethodArgumentResolver | 特殊 binding lifecycle |
| 类型转换 | Converter/Formatter/WebDataBinder | 字段级规则 |
| validation | Validator | 保持时机和消息 |
| 异常映射 | ControllerAdvice/HandlerExceptionResolver | 全局/局部优先级 |
| forward/result | ModelAndView/forward:/redirect:/resolver | 精确导航代数 |
| 一次性 messages | Flash/session compatibility bridge | 保持消费时机 |

## 2. Struts 2

### 2.1 Around-Invocation Interceptor Stack

Struts2 interceptor 不是普通的“前置列表”。典型结构：

```text
I1.before
  I2.before
    Action
  I2.after
I1.after
PreResultListeners
Result.execute
```

同时 interceptor 可以：

- 不调用 `invocation.invoke()` 而短路；
- 改变 Action/ValueStack；
- 返回不同 result code；
- 捕获异常；
- 在 Action 后修改结果；
- 使用 per-action 参数；
- 条件执行。

Target IR 必须保留：

```yaml
order:
before:
afterUnwind:
shortCircuit:
condition:
resultMutation:
exceptionBehavior:
```

### 2.2 ValueStack 与 OGNL

迁移不能把 ValueStack 简化成普通 DTO。需要恢复：

- stack 中对象顺序；
- property resolution；
- model-driven/preparable；
- parameter population；
- conversion errors；
- request/session/application maps；
- result 参数表达式；
- taglib 读取；
- OGNL 安全面。

目标应尽量变成显式 model/request/session contract；暂时无法消除时使用最小 compatibility adapter，并限制 property allowlist。

### 2.3 Result Types

至少区分：

- dispatcher/view；
- redirect；
- redirectAction；
- stream；
- json/xml；
- chain；
- freemarker/velocity；
- custom Result；
- `NONE`。

`ActionChainResult` 涉及新的 ActionInvocation 与最终 result 查找，不能直接改为 controller method call。

### 2.4 Interceptor 映射策略

| Interceptor 语义 | Spring 候选 |
|---|---|
| 参数绑定/转换 | ArgumentResolver + Binder + Converter |
| validation/workflow | Validator + ControllerAdvice/compatibility layer |
| auth/roles | SecurityFilterChain/Method Security |
| token/double submit | CSRF/idempotency service |
| prepare/model driven | ArgumentResolver/service orchestration |
| file upload | MultipartResolver + validation |
| exception | HandlerExceptionResolver |
| custom around | HandlerInterceptor/AOP/explicit pipeline adapter |
| scope | request/session model adapter |

映射按语义选扩展点，禁止“一律 HandlerInterceptor”。

## 3. Servlet

### 3.1 Effective Descriptor

必须合并：

- `web.xml`；
- `web-fragment.xml`；
- `metadata-complete`；
- `@WebServlet/@WebFilter/@WebListener`；
- `ServletContainerInitializer`；
- programmatic registration；
- container-specific descriptor。

输出 effective route/filter/listener/resource/security model，并保留冲突/部署失败语义。

### 3.2 Dispatcher Types

Filter mapping 需区分：

```text
REQUEST
FORWARD
INCLUDE
ERROR
ASYNC
```

目标 Filter order 和 dispatcher types 变化会导致认证、编码、日志、事务或错误页行为变化。

### 3.3 RequestDispatcher

`forward()`、`include()` 和 error dispatch 影响：

- request attributes；
- response buffer/commit；
- URL/path 视图；
- filter dispatch；
- error attributes；
- JSP 可见数据。

生成器必须使用 NavigationDispatchIR，不得将它们统一成返回 view name。

### 3.4 何时保留 Servlet

以下场景不应强制改 Controller：

- 二进制/大文件 streaming；
- async/nonblocking I/O；
- 特殊协议或低层 response 操作；
- 容器 callback/initializer；
- 第三方 servlet；
- 复杂 include/forward 行为。

可以把 Servlet 迁移到 `jakarta.servlet` 并由 Spring Boot registration 管理，同时逐步现代化外围。

## 4. JSP / TLD / Tiles

默认 Phase A 保留视图，理由：

- 避免将 Web 框架差异和 UI 差异混在同一验证波次；
- JSP/TLD 可能依赖 request/session attribute；
- custom tag 可能包含业务甚至副作用；
- Tiles definition 继承与动态 include 需要独立恢复。

保留 JSP 时由 packaging planner 决定 WAR/外置容器；移除 JSP 后再评估 executable JAR。

## 5. Spring Boot 4 目标约束

目标基线：

```text
Java 17+
Spring Framework 7.x
Jakarta EE 11
Servlet 6.1
Spring Boot 4.x focused modules/starters
```

迁移必须单独处理：

- `javax.*`→`jakarta.*`；
- 老依赖/容器不兼容；
- Boot 4 starter/module 变化；
- test starter 变化；
- charset/logging/Jackson 等依赖升级差异；
- JSP/容器打包；
- Undertow 等不满足目标 Servlet 基线的选择。

## 6. 最危险的等价性断点

| 断点 | 典型后果 |
|---|---|
| ActionForm reset 丢失 | checkbox/session wizard 状态错误 |
| interceptor order 改变 | validation/auth/prepare 顺序错误 |
| forward→redirect | request attributes 丢失、URL/status 变化 |
| filter dispatcher type 丢失 | 错误页/forward 未执行安全或编码逻辑 |
| ValueStack 展平 | JSP/OGNL 属性解析不同 |
| Action/Servlet shared field | 并发数据串扰 |
| exception precedence 改变 | 状态码/页面/事务回滚不同 |
| parameter binding 变宽 | mass assignment 安全风险 |
| transaction boundary 外移 | 部分提交或重复副作用 |
| session serialization 变化 | 集群/重启 session 失效 |
| JSP tag 副作用遗漏 | 页面显示相同但业务写入丢失 |
| response commit/streaming 变化 | 下载损坏或错误处理失效 |
