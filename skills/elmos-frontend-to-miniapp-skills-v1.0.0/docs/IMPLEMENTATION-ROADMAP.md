# 实施路线图

本路线图按“可验证闭环”排序，不使用人工人日作为完成度指标。Elmos 在实现后应根据真实任务历史报告机器墙钟 ETA、置信区间和关键路径；在缺少历史样本时显示 `insufficient-data`，不得虚构时间。

## M0 — 契约与仓库骨架

### 进入条件

- Elmos 已有可创建、暂停、恢复、取消和归档的任务执行框架。
- 已确定转换引擎所在 monorepo 路径。

### 实施

- 建立 `conversion-contracts`、`semantic-ir`、`registry` 和 `runs/` 工作区契约。
- 引入本包 14 个 JSON Schema。
- 落地 artifact index、内容哈希、task ID 和 gate result 模型。
- 建立安全仓库扫描 sandbox。
- 把 22 个 Skills 安装到 `.agents/skills` 和 `.claude/skills`。

### 退出条件

- MAPP-001～004 完成。
- 最小 conversion-request 可创建任务并产生 inventory。
- 任务中断后可从 inventory checkpoint 恢复。
- Schema、安装和包验证全部通过。

## M1 — 最小 IR 闭环

### 实施

- Vue 3 todo fixture 作为第一个 golden project。
- Vue SFC、router、Pinia/局部状态进入 source facts。
- Semantic IR v1 可确定性序列化。
- 组件、状态、事件和样式最小规则可工作。
- 先生成一个不含高风险能力的微信目标工程。

### 退出条件

- MAPP-005～020 中适用于最小样例的任务完成。
- 源→IR→目标 trace 覆盖率 100%。
- 重复运行输出哈希一致。
- 微信目标原生构建与关键流程通过。
- 不支持项为 0 或有明确分类。

## M2 — React 与依赖迁移

### 实施

- React TSX、Hooks、Router、Redux/Zustand 支持。
- CSS Modules/CSS-in-JS 的受控子集。
- 依赖使用面分析、替代图和许可证/供应链检查。
- 共享业务核心与平台端口接口。

### 退出条件

- React commerce fixture 可生成至少两个目标平台。
- Hook cleanup、异步请求和路由状态差分通过。
- 所有直接依赖有保留/替代/重写/后端迁移/阻断结论。

## M3 — Flutter 语义重建

### 实施

- Dart analyzer CLI。
- Widget Tree、Navigator、StatefulWidget、Provider/Riverpod/Bloc 基础支持。
- 常见布局、表单、手势、主题和动画转换。
- Platform Channel 与插件报告。
- 局部 Canvas 策略与全页 Canvas 禁止门禁。

### 退出条件

- Flutter dashboard fixture 的页面、导航和状态流程通过。
- 所有插件和 Platform Channel 100% 有结论。
- 未发生整页截图化或 Canvas 化。
- 视觉差异达到样例阈值。

## M4 — 四平台代码生成

### 实施

- 微信、支付宝、抖音、小红书独立 platform profile。
- 四套原生工程 generator。
- app/page/component/style/config、路由、分包、资源和平台 API adapter。
- 官方构建工具的受控适配器。
- 预览/上传/审核/发布动作分级。

### 退出条件

- MAPP-023～026 完成。
- 同一 IR 可同时生成四个平台。
- 四个平台的生成代码不互相导入平台 SDK。
- 每个平台至少一个 golden project 官方构建通过，或有工具链无法自动化的可验证阻断记录。

## M5 — 商业能力、隐私与安全

### 实施

- 登录、身份绑定、分享、商品、订单、支付、退款和会员 contract。
- 服务端密钥与客户端能力分离。
- 数据流、权限、第三方 SDK、secret 和审核披露扫描。
- 回调验签、幂等、重放防护和补偿。

### 退出条件

- MAPP-027～030 完成。
- 客户端高危 secret 为 0。
- 敏感数据流 100% 可追踪。
- sandbox/mock 订单和回调流程通过。
- 真实支付、退款或发布动作仍受人工审批保护。

## M6 — 差分、视觉与自动修复

### 实施

- 源/目标行为 trace harness。
- 视觉基线、设备矩阵和 mask 审计。
- finding → repair candidate → patch → targeted tests → affected gates。
- 规则上游优先修复和最多三次默认循环。

### 退出条件

- MAPP-031～036 完成。
- 关键流程通过率 100%。
- 确定性页面达到请求中的视觉阈值。
- 同类缺陷可通过规则修复复用于第二个 fixture。
- 无限循环、重复补丁和降低门禁行为被测试阻断。

## M7 — CI、证据与生产运行

### 实施

- 可重现构建镜像与工具版本锁定。
- 多租户 workspace、缓存、凭证和日志隔离。
- preview/upload/review/release 分级流水线。
- evidence graph、兼容报告、成本和系统运行时。
- 失败恢复、灰度、回滚和平台工具链漂移检测。

### 退出条件

- MAPP-037～040 完成。
- 所有“ready”结论都有当前证据和哈希。
- 安装、验证、构建、测试、修复和报告可在 CI 重放。
- 至少完成一次四平台非生产 dry-run。
- 正式发布仍必须由授权主体批准。

## 实施优先级

1. 契约、IR、trace 和证据。
2. Vue 3 → 微信最小闭环。
3. React 与第二个平台。
4. Flutter analyzer。
5. 四平台完整 generator。
6. 商业能力和隐私安全。
7. 差分、视觉和自动修复。
8. 发布和规模化。

不要先大量堆积语法规则而缺少可运行闭环；每个阶段都必须有 fixture、官方构建或明确阻断证据。
