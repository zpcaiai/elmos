# Elmos 精确 AI 优化改造 Skills Package v1.0.0

这是**实施规格、工作流、契约、参考代码与测试包**；不是已经改造或部署完成的Elmos。
目标是用最少新增设施优化源码检索、证据化教学、迁移/转换、生成、SQL转换和失败修复。
不要求把LangChain、LangGraph、Dify、Elasticsearch和独立向量数据库全部安装。

## 使用
1. 阅读SPEC.md、INTEGRATION.md和IMPLEMENTATION_PLAN.md，默认实施B0+B1。
2. 在包目录运行 `python3 scripts/validate_package.py` 与 `python3 scripts/run_checks.py`。
3. `python3 scripts/install.py --repo /absolute/path/to/elmos` 只显示计划；核对后加 `--apply` 执行新增安装。
4. 安装到 `.agents/skills/elmos-ai-optimization`；不编辑AGENTS或已有Skill，不修改生产代码。
5. 在Codex中使用CODEX_START_PROMPT.md；也可以不安装，直接要求Codex读取解压目录中的SKILL.md。

## 导航
- 主Skill五件套：SKILL.md / manifest.yaml / implementation.yaml / acceptance.yaml / runbook.md。
- SPEC.md：逻辑端口、数据、流程、安全、预算、业务消费者与灰度策略。
- tasks/tasks.yaml：30项任务；ACCEPTANCE.md：60条**待宿主执行**的验收定义。
- references/workflows：3个按需内部流程；不额外创建Codex或Elmos路由。
- contracts：14个Schema和14个示例，TypeScript宿主端口、API映射说明。
- reference：实际SQLite/FTS5参考、过滤、缓存、动作对账及指标数学，不是生产实现。
- adapters/catalog：候选适配与启用条件，不表示原生后端已连接。
- reports：本次实际验证记录与not_run资格表。

## 三个不同状态
PACKAGE_VALIDATED：本包结构和参考测试已通过。
HOST_FEATURE_VERIFIED：对应功能已在实际Elmos集成并验证。
PRODUCTION_APPROVED：宿主独立验收对指定范围批准发布。
三者不得互相替代。SHA256只证明内容一致，不证明来源可信或结论正确。

Python 3.10+，SQLite需FTS5；验证依赖见requirements-validation.txt。
虚拟环境、临时数据库和新测试输出放在包目录之外；密封校验会拒绝未列入清单的额外文件。不要为通过校验跳过摘要检查。
