# 官方资料与更新入口

资料检查日期：`2026-08-19`。这些 URL 用于初始化 platform profile 和能力注册表。生产执行前必须再次确认当前内容、工具版本和账户权限。

## Agent Skills

- OpenAI — Build skills  
  https://developers.openai.com/codex/build-skills
- OpenAI — Codex customization  
  https://developers.openai.com/codex/customization/overview
- Anthropic — Extend Claude with skills  
  https://docs.anthropic.com/en/docs/claude-code/skills

当前安装约定：

- Codex 仓库技能：`.agents/skills/<name>/SKILL.md`
- Claude Code 仓库技能：`.claude/skills/<name>/SKILL.md`

## 微信小程序

- 微信小程序 CI 文档入口  
  https://developers.weixin.qq.com/miniprogram/dev/devtools/ci.html
- `miniprogram-ci` 包  
  https://www.npmjs.com/package/miniprogram-ci
- 微信小程序开发文档根目录  
  https://developers.weixin.qq.com/miniprogram/dev/framework/

自动化环境可能无法抓取微信文档站；实现时仍应由开发/运维环境访问官方页面，固定实际工具版本，并验证 preview/upload 所需密钥和权限。

## 支付宝小程序

- 小程序 CLI 产品介绍  
  https://opendocs.alipay.com/mini/02qh1f
- CLI upload  
  https://opendocs.alipay.com/mini/02q3an
- 支付宝小程序文档  
  https://opendocs.alipay.com/mini

官方资料显示小程序 CLI 面向轻量研发和 CI/CD，并提供 build、preview、upload 等命令入口。具体命令、认证和支持范围应从当前页面生成 platform profile。

## 抖音小程序

- 开发文档入口  
  https://developer.open-douyin.com/docs/resource/zh-CN/mini-app/develop/
- 框架/应用/配置入口  
  https://developer.open-douyin.com/docs/resource/zh-CN/mini-app/develop/framework/basic-reference/general-configuration
- 开放平台  
  https://developer.open-douyin.com/

注册表应分别建模框架、组件、JS API、服务端 OpenAPI、行业插件、开发工具和场景值，不能把服务端 secret 下沉到客户端。

## 小红书小程序

- 小红书小程序开放平台  
  https://miniapp.xiaohongshu.com/
- 小程序开发文档入口  
  https://miniapp.xiaohongshu.com/doc/DC626355
- 第三方授权 token  
  https://miniapp.xiaohongshu.com/third/api-3rd/post-api-rmp-tp-auth-token
- 小程序下单/支付资料  
  https://miniapp.xiaohongshu.com/third/api-3rd-doc/rmpDeal

小红书部分旧页面会提示迁移到新版文档站，或在自动抓取时超时。能力注册表必须记录页面版本和验证日期；支付、授权、专业号、类目和服务商模式都应按实际账户重新验证。

## 安全研究（补充，不替代官方规则）

- AppSecret 泄露研究  
  https://arxiv.org/abs/2306.08151
- 小程序代码与隐私政策一致性研究  
  https://arxiv.org/abs/2302.13860
- Super App 隐藏 API 研究  
  https://arxiv.org/abs/2306.08134

这些研究支持本包的默认安全策略：AppSecret 仅在后端、数据流与隐私声明一致、只使用公开且获授权的平台能力。

## Registry 更新要求

每个引用在 registry 中保存：

```yaml
url: https://...
title: ...
publisher: ...
retrieved_at: "2026-08-19T00:00:00+08:00"
content_hash: "<optional>"
platform_profile_version: "..."
verification:
  docs_reviewed: true
  account_tested: false
  build_tested: false
notes: ...
```

`docs_reviewed` 不得被当作 `account_tested` 或 `build_tested`。
