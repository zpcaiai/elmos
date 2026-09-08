---
name: elmos-live-workbench
description: 为 Elmos 多语言生成和仓库级跨语言转换产物实现源码阅读、逐行/模块/架构教学、真实调试和600秒运行预览。用于实现、集成、验证或扩展 Live Workbench；先复用已有 Kernel、图谱和安全边界，再按阶段交付真实垂直切片。
metadata:
  version: "1.0.0"
---

# Elmos Live Workbench 实现入口

先读 `README.md`、`INTEGRATION.md`、`IMPLEMENTATION_PLAN.md`。技术细节见 `DESIGN.zh-CN.md`。
本包是实施技能、机器契约和有限参考代码，不是已经部署的多语言IDE。

## 工作顺序
1. 读取目标仓库已有指令、构建说明和相关模块，生成可复用/缺失/冲突清单；不得先新建重复微服务。
2. 保持现有8 Kernel、四业务线和E0–E5含义；将本包命名空间 `lw.v1` 映射到现有owner。
3. 依 `workflows/implementation-batches.json` 选择最小未完成垂直切片。只按需加载 `skills/` 内相关 SKILL.md，不把28个子工作流全放进上下文。
4. 按 `contracts/` 冻结输入输出，按 `policies/` 落实租约、权限、revision、证据与清理不变量。
5. 真实跑通一个受信fixture后，继续实现故障/越权/恢复路径和其他P0 runtime。Mock仅可用于单测，不可作完成凭据。
6. 完成 `evals/qualification-plan.json` 中对应验收；每项分列pass/fail/not_run/unsupported。
7. 更新实施报告与恢复checkpoint，报告实际wall-clock、资源/token用量、证据摘要及未支持表面。

## 绝对边界
准备/编译不能侵占成功就绪后的600秒；刷新/断点/重连不能续租；没有合格隔离provider不执行公网不可信源码。
日志回看不是通用反向调试，跨语言不按行号强行对齐，预览成功不等于语义等价或E5。
不得自动安装项目提供的Skill，不得读取/泄露主凭据，不得连接生产数据库。

## 本地检查
`python scripts/validate_package.py`
`PYTHONPATH=reference python -m unittest discover -s reference/tests -v`
可选真实本地样例：`python scripts/run_native_fixtures.py` 与 `python scripts/run_debugpy_lab.py`。
这些只运行随包原创可信样例，不能作为任意上传项目的安全执行器。
