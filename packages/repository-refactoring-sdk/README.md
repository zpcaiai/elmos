# @elmos/repository-refactoring-sdk

`elmos-repository-refactoring` 确定性内核的 **TypeScript 外壳**：类型、传输、错误分类。
零运行时依赖，`tsc --strict` +
`noUncheckedIndexedAccess` + `exactOptionalPropertyTypes` 全绿。

## 这个包做什么、不做什么

```
   TypeScript 宿主
        │  client.run(skill, payload, trustedContext)
        ▼
  ┌───────────────────────┐   一个 JSON 文档进   ┌──────────────────────┐
  │ RepositoryRefactoring │ ─────────────────►  │ Python 确定性内核     │
  │ Client（本包）         │ ◄─────────────────  │ 所有判定都在这一侧    │
  └───────────────────────┘   一个 JSON 文档出   └──────────────────────┘
```

**做**：编译期的 Skill 名、风险等级、门禁三态类型；子进程传输（无 shell、
环境变量白名单、超时、输出上限）；把「没成功」和「跑不起来」分成两类错误。

**不做**：重试、缓存、改写 payload、把 `blocked` 解释成别的东西。重试策略需要看
`failure_class`，那是 Orchestrator 的判断，不是传输层的。

## 三条被类型强制的诚实性规则

1. **`Status` 没有默认值、没有 `unknown` 成员。** 调用方必须显式处理 `blocked` 和
   `rejected`；不存在一种写法让未决的运行读起来像成功。
2. **可能未决的布尔一律是 `boolean | null`。** `null` = 未判定。`gateResults()` 把
   缺失的 `passed` 映射成 `null` 而不是 `false`，`undecidedBlockingGates()` 把它们
   单独列出来——阻断门未决即失败。
3. **退出码和信封状态互校。** 两者不一致时抛 `RuntimeUnavailable`，而不是挑一个
   看起来更顺眼的用。

## 用法

```ts
import {
  RepositoryRefactoringClient,
  undecidedBlockingGates,
  topologicalOrder,
} from "@elmos/repository-refactoring-sdk";

const client = new RepositoryRefactoringClient({
  packageRoot: "../repository-refactoring/src",   // 或让解释器自己装好
  trustedContext: {
    workspace_root: "/abs/approved/root",         // 宿主授权，payload 给不了
    policy: { /* 缺省 = enterprise-default：拒网络、无自治 */ },
  },
});

const envelope = await client.run("test-and-verification", { workspace, request });

if (envelope.status !== "succeeded") {
  // reasons 才是有用的部分，不要吞掉
  console.error(envelope.reasons.join("\n"));
  console.error(undecidedBlockingGates(envelope));  // 「没跑」不等于「过了」
}
```

`SKILL_NAMES` 是目录声明顺序（00–22 编号），**不是**依赖顺序——09 数据 Schema 依赖
17 人工审批门。需要调度顺序时用 `topologicalOrder()`。

## 目录同步

`src/catalog.ts` 由 `scripts/generate-catalog.ts` 从内核提交的
`config/skill-catalog.json` 生成。`test/catalog.test.ts` 在测试时重新读取同一份
JSON，因此 Python 侧新增一个 Skill 而这里忘了重新生成，是**构建失败**，不是悄悄
少一个类型。

```bash
pnpm run build && node dist/scripts/generate-catalog.js
```

## 验证

```bash
pnpm run build      # tsc -p tsconfig.json
pnpm test           # node --test dist/test/*.test.js
```

集成测试真的会拉起 Python 解释器。找不到 Python ≥ 3.11 时它们**跳过**而不是通过——
一次什么都没跑却全绿的运行，正是这个包要防的那种谎。
