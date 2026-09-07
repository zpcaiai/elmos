# ADR-002：原生小程序优先

- 状态：Accepted
- 日期：2026-08-19

## 决策

默认输出原生页面、组件和平台 API adapter。WebView、全页 Canvas、截图和固定视频不是默认转换策略。

## 理由

- 可审核和可维护；
- 平台能力与性能更可控；
- 便于测试、隐私扫描和差分；
- 避免把复杂性隐藏在不可编辑壳层。

## 例外

局部 Canvas、WebView 或其他降级只在：

- conversion-request 明确允许；
- capability finding 为 C/D；
- 有业务和安全审批；
- 有功能、性能、隐私和回滚测试。

例外必须进入 evidence。
