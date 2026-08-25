# ADR-003：四个平台使用独立适配器

- 状态：Accepted
- 日期：2026-08-19

## 决策

微信、支付宝、抖音和小红书分别拥有 platform profile、capability mappings、generator、build adapter 和 test harness。

## 理由

平台在页面配置、组件、事件、生命周期、API、工具链、权限、资质、审核和商业能力上均可能不同。简单改扩展名或 API 前缀会产生隐蔽错误。

## 共享范围

可共享：

- 领域模型；
- 应用服务；
- Schema；
- 平台端口；
- 纯函数；
- 经过适配的资源和设计 token。

不可共享：

- 平台全局对象；
- 平台 secret；
- 未抽象的平台错误码；
- 假定相同的支付/授权流程。
