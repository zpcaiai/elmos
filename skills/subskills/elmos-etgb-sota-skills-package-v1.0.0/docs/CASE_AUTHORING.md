# Case authoring guide

## 必填

每个 case 必须说明 source、target、requirement、execution adapter、Oracle、coverage cell、禁止差异、claim policy 和 provenance。

## ID

ID 是稳定标识，不随标题改变。修改语义时创建 case version；不要复用 ID 掩盖历史。

## Good case

- 只验证一项主要能力，但包含足够上下文；
- 能自动 provision/cleanup；
- 期望行为来自业务契约或独立运行，而非生成模型；
- 失败能定位第一处差异；
- 含至少一个 edge/adversarial 变体；
- P0 含负向/故障测试。

## 禁止

- 仅断言文件存在；
- 仅断言编译；
- 只看代码相似度；
- 大量 ignore fields；
- 测试读取目标实现内部细节而无法跨技术栈；
- 在测试里嵌入生产 secret；
- 让生成 Agent 修改期望值。

## 添加能力

1. 编辑对应 `matrices/*.yaml`；
2. 更新 coverage model；
3. `etgb materialize`；
4. `etgb validate && etgb coverage`；
5. 添加可执行 fixture/adapter；
6. 添加 mutant，证明 Oracle 能杀死常见错误；
7. 评审 priority 与 release gate。
