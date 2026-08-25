# 安全与隐私设计

## 1. 信任边界

不可信输入包括：

- 用户上传或连接的源仓库；
- package scripts、构建插件和代码生成器；
- 第三方依赖；
- 平台返回数据；
- 平台文档抓取或 registry 更新内容；
- 模型生成补丁；
- 用户提供的配置和路径。

可信控制面包括：

- 租户身份与权限；
- 工作流状态；
- secret broker；
- policy engine；
- artifact hash service；
- approval service；
- audit log。

## 2. 源仓库安全

Discovery 阶段：

- 不执行 `postinstall`、`prepare`、Gradle script、Dart build_runner 或任意仓库脚本；
- 不加载 `.env` 值；
- 限制文件大小、解压层级、压缩比和路径；
- 防止 zip-slip、symlink escape、path traversal；
- 二进制、超大文件和损坏文件进入清单；
- AST parser 在沙箱和资源限额内运行；
- 网络默认关闭。

需要运行源项目时：

- 创建一次性沙箱；
- 无生产凭证；
- 网络 allowlist；
- 只读源快照；
- 临时 writable overlay；
- CPU、内存、磁盘、进程和时间限额；
- 记录命令与输出并脱敏。

## 3. Secret 管理

允许：

```yaml
wechat_app_secret_ref: vault://tenant/123/wechat/app-secret
```

禁止：

```yaml
wechat_app_secret: "actual-secret"
```

secret broker 应：

- 按 tenant/run/task/platform/action 发放短期凭证；
- 区分 build、preview、upload、review、release；
- 只向执行该动作的隔离 worker 暴露；
- 不写磁盘或日志；
- 支持撤销与轮换；
- 记录使用审计但不记录值。

## 4. 平台权限

权限模型：

```text
developer identity
→ tenant membership
→ project role
→ platform app binding
→ capability entitlement
→ action approval
→ short-lived credential
```

仅有平台账号连接不代表允许上传或发布。每个动作检查：

- 租户；
- 项目；
- app id；
- 目标环境；
- capability；
- requested action；
- approval；
- credential scope。

## 5. 个人数据流

IR 中的数据节点至少标记：

- 数据类型；
- 是否个人/敏感；
- 来源；
- 用户触发；
- 使用目的；
- 传输域名；
- 本地/服务端存储；
- 保留期；
- 第三方共享；
- 删除路径；
- 权限和同意；
- 平台声明。

生成代码后重新做 AST/调用图扫描，验证事实与计划一致。

## 6. 支付和订单安全

- 客户端请求只发送最小订单输入；
- 服务端创建订单和支付参数；
- 每个 create/pay/refund 使用幂等键；
- 回调验签；
- 防重放；
- 金额、币种、商户、订单和用户在服务端校验；
- 不信任客户端 success；
- 状态机拒绝非法跳转；
- 超时、重复回调和部分失败有补偿；
- sandbox 与生产凭证隔离；
- 真实支付/退款必须审批。

## 7. 供应链

对依赖记录：

- 名称、版本、来源和哈希；
- 直接/传递；
- 使用面；
- 许可证；
- 漏洞；
- 维护状态；
- install/build scripts；
- 平台兼容；
- 替代决策。

代码生成模板和 registry 也属于供应链，必须版本化、签名或哈希并进入 evidence。

## 8. 日志和报告脱敏

禁止记录：

- secret；
- 私钥；
-完整 token；
- 身份证/手机号等完整敏感值；
- 支付参数；
- 用户原始内容（非必要）；
- 带凭证 URL。

使用：

- 字段级 allowlist；
- token 指纹；
- 用户 ID 哈希/别名；
- 错误堆栈路径清理；
- screenshot 敏感区域策略；
- 租户级日志访问控制；
- 保留期和删除。

## 9. 模型与自动修复安全

模型生成内容不是可信代码。每个 patch：

- 限定文件范围；
- AST/类型/静态检查；
- secret 和危险 API 扫描；
- 测试；
- diff size 和 blast radius；
- 禁止修改门禁配置、测试期望、mask 或安全策略，除非任务明确且审批；
- 禁止生成固定成功、绕过验签或关闭权限错误；
- 保存原始 finding 和 rollback。

## 10. 发布安全

动作分级：

| 动作 | 默认自动 | 审批 |
|---|---:|---|
| 静态检查 | 是 | 无 |
| 本地构建 | 是 | 无 |
| mock/sandbox 测试 | 是 | 无 |
| 生成预览 | 可配置 | 项目级 |
| 上传开发版本 | 否 | 平台 app 级 |
| 提交审核 | 否 | 业务+隐私 |
| 灰度发布 | 否 | 发布审批 |
| 全量发布 | 否 | 发布审批 |
| 回滚 | 可预授权 | 受控 |

## 11. 事件响应

检测到 secret 或跨租户暴露：

1. 立即停止相关 worker；
2. 封存但限制访问的证据；
3. 撤销/轮换凭证；
4. 标记受影响 artifact；
5. 通知租户与安全责任人；
6. 清理日志/缓存；
7. 根因与修复；
8. 重新验证；
9. 记录事件，不把事故报告放入普通用户可见日志。
