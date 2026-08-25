---
name: elmos-onboarding-learning-path
description: 根据角色生成项目概览、术语表、阅读顺序、核心流程和上手任务。用于新人入职、项目交接和跨团队理解。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: experience
  title_zh: 项目介绍与新人学习路径
  batch: BATCH-03-code-reader-and-explanation
  owner: elmos-project-intelligence
---

# 项目介绍与新人学习路径

## 目标

把庞大代码库转换为角色化、可进度跟踪、可回源的学习路径。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- Project Intelligence Graph
- 项目文档
- 目标角色与经验
- 可用时间/目标

## 必须输出

- 项目一页纸
- 术语表
- 分阶段阅读路径
- 练习与检查题
- 学习进度

## 执行流程

1. 识别项目使命、边界、核心业务能力和技术栈。
2. 为开发、测试、运维、产品、架构、安全设计不同路径。
3. 选择最具代表性的文件、调用链、流程和数据模型。
4. 生成 30 分钟、半天、3 天、2 周不同学习计划。
5. 为每阶段提供可验证任务和相关代码深链。
6. 根据用户反馈和项目变更更新路径。

## 实施要求

- 路径应从系统上下文逐步深入，不从随机核心类开始。
- 标记必须理解、可选、危险修改区域。
- 术语映射业务名词、代码名、表名和 API。
- 学习材料绑定 revision。
- 可导出 Markdown、DOCX、PPT 大纲。

## 安全与可信度约束

- 不得假设新人拥有未声明权限或环境。
- 不得推荐查看含敏感数据的生产配置。
- 过期路径必须提示重新生成。

## 依赖技能

- `elmos-code-explanation`
- `elmos-project-intelligence-graph`

## 预期交付物

- `onboarding-guide.md`
- `learning-path.json`

## 完成定义

- [ ] 用户能沿路径定位并运行最小开发闭环。
- [ ] 每个学习节点有目标、材料、练习和完成条件。
- [ ] 路径中的文件和链接全部存在。
- [ ] 项目变化后受影响节点被标记 stale。
- [ ] 角色间内容明显差异化。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
