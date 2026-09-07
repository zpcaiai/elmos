# 威胁模型与安全边界

## 1. 仓库内容不可信

源仓库可能包含：

- prompt injection 文本；
- 恶意 build plugin；
- shell script；
- annotation processor；
- test 中的外部调用；
- dependency confusion；
- secrets；
- 巨型/压缩炸弹文件；
- symlink/path traversal；
- 生成源码执行。

扫描阶段应尽量静态；构建/测试只能在无秘密、限制网络和资源的 sandbox 中运行。

## 2. 参数绑定扩大

Struts/Servlet 到 Spring 后，自动 binding 可能暴露更多 nested property。生成器必须基于 Binding IR 生成 allowlist，并对未知字段、敏感字段、集合索引和 object graph depth 设限。

## 3. OGNL/表达式

Struts2 OGNL 和 JSP EL 的动态访问可能带来安全和语义风险。迁移应：

- 恢复实际读取/写入路径；
- 转换为显式 DTO/model；
- 对无法消除的表达式使用受限 evaluator；
- 不复制危险的广泛 method/property access。

## 4. 自动修复风险

Repair Agent 不得：

- 绕过安全测试以让差分“通过”；
- 扩大权限；
- 删除失败测试；
- 将异常吞掉；
- 将事务/写入改成 no-op；
- 通过 normalizer 忽略业务字段；
- 修改 source baseline；
- 在无证据时改关键业务逻辑。

这些行为由 repair policy 和 diff-of-tests gate 检测。

## 5. 生产副作用

真实数据库、消息、邮件、支付、文件和外部 API 默认禁止双写。使用：

- transaction rollback；
- snapshot/clone；
- proxy capture；
- sandbox double；
- dry-run；
- idempotency key；
- allowlisted test tenant。

生产 canary 需显式 approval 和 scoped authority。

## 6. Secret 处理

- 只保存 secret reference；
- 日志/trace/body 脱敏；
- artifact 设置租户隔离与保留期；
- source map 不复制秘密；
- 模型上下文不加载不必要秘密；
- 下载证据包时按权限过滤。

## 7. 供应链

目标输出需生成 SBOM，检查：

- 旧 Struts/Commons/OGNL 依赖是否完全移除；
- javax/jakarta 混用；
- 可疑 Maven repository/plugin；
- shaded vulnerable classes；
- container-provided version；
- test-only 依赖泄漏到生产；
- 锁定的镜像 digest。

## 8. 权限模型

最低角色：

```text
Viewer
MigrationOperator
CodeApprover
SecurityApprover
DataApprover
ProductionCutoverApprover
Administrator
```

生产认证和切流应支持职责分离。
