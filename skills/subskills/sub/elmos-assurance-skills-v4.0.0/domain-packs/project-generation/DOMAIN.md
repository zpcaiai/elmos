# 多语言项目生成 Domain Pack

## 保证目标
Approved requirements → contract/state/effect conformance

## 首个商业纵向切片
批准的订单需求 → 一个真实后端语言+真实数据库+接口回归；再加入第二语言差分

## 核心语义
先Domain/State/Interface/Acceptance，后实现。测试从approved normative spec生成，不从候选代码抽取expected。
多语言版本可以互相差分，但还必须分别满足同一规范，不能互相作唯一Oracle。关键内部能力无需变成公开API，可用受控test probe/组件接口。
需求模糊产生SpecQuestion/显式设计假设；关键规则未经责任人审批禁止发布。

## 必需验收场景
- **GEN-001** — 正常创建订单：请求/响应schema、DB行与业务字段一致，事件恰按声明语义产生。
- **GEN-002** — 跨tenant读取/修改：拒绝且DB/MQ无未授权副作用。
- **GEN-003** — 相同幂等键重复/并发创建：同一业务结果，无重复扣款/库存效果。
- **GEN-004** — 事务第二步故障：要求的原子状态不部分提交。
- **GEN-005** — 需求删实现但接口仍返回200：独立需求测试必须失败。
- **GEN-006** — UI重试/取消流程：UI/HTTP/最终数据状态一致。

## 形式化义务候选
金额/库存状态不变量；去重状态机的限定模型；纯领域规则保持。

## 不支持/阻塞
未批准业务假设；没有可执行规范且没有可观测结果的功能。

## 成熟度
本包仅SPECIFIED，原生适配与客户认证NOT_RUN。每种确切source/target/feature/environment组合独立晋级；不能用一个语言/DB测试结果覆盖整个矩阵。
