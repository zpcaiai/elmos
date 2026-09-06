# Elmos Live Workbench — Skills Package 1.0.0

**源码可读、解释有证据、调试是真的、预览在 READY 后持续600秒。**

这是 Elmos 的增量实现技能包，不是已上线的在线 IDE，也不改写 Elmos 的全局版本。
它向既有 Proof-Driven Agentic Harness / Repository Semantic Compiler 架构接入
源码教学、调试与临时运行能力；不替代原有生成、转换、项目图谱或独立认证模块。

## 从哪里开始

1. 读 `DESIGN.zh-CN.md`：完整功能、边界、架构与实现取舍。
2. 读 `INTEGRATION.md`、`IMPLEMENTATION_PLAN.md`：基线盘点、复用、批次及真实验收。
3. 由根 `SKILL.md` 路由到 `SKILL_INDEX.md` 中28个内部工作流；不要一次性把它们全部塞入模型上下文。
4. 读 `VALIDATION_REPORT.md`：明确实际执行了什么，以及没有执行什么。

## 包里有什么

- 1个外部路由、28个内部技能工作流，每个含 `SKILL.md`、机器契约及3条验收案例。
- 12个 JSON Schema、10个数据形状样例、12个候选运行时配置。
- Python参考内核：固定600秒窗口、源码坐标、调试命令去重/围栏、证据绑定。
- 原创 Python/JavaScript 实际进程样例、边界变异测试、真实 Python DAP 调试实验。
- 非覆盖安装器、安装/撤回测试、包校验器、发布门禁及逐批落地说明。
- 不含已实现的多租户API、Monaco工作台、云沙箱provider、四语言生产级适配器或生产证书。

## 本地验证

参考代码要求 Python 3.10+；原生双语言样例另外需要 Node.js。`debugpy`实验只执行随包原创受信样例。

```bash
cd elmos-live-workbench
python3 -m pip install -r requirements-dev.txt
python3 scripts/validate_package.py
PYTHONPATH=reference python3 -m unittest discover -s reference/tests -v
python3 scripts/run_native_fixtures.py
python3 scripts/run_debugpy_lab.py
```

依赖范围用于开发；真正发布的runtime profile必须固定版本、摘要、平台和许可证检查结果。
上述脚本不会建立公共预览服务，也没有把本机当作不可信仓库的安全沙箱。
不要将 `run_native_fixtures.py` 改成接受任意仓库路径后直接上线。

## 安装到现有仓库

```bash
# 默认只显示计划，不改文件。
python3 scripts/install.py --repo /absolute/path/to/elmos
# 看完冲突/目录计划后执行；不覆盖任何已存在目标。
python3 scripts/install.py --repo /absolute/path/to/elmos --apply
```

安装后仅 `.agents/skills/elmos-live-workbench/SKILL.md` 作为额外入口。
全部实现材料放在 `.elmos/skillpacks/elmos-live-workbench/`，不复制或覆盖现有内核。
现有 Elmos router 是否应调用这个入口，由 B0 的兼容性盘点决定，安装脚本不会擅自改它。

```bash
python3 scripts/install.py --repo /absolute/path/to/elmos --uninstall
python3 scripts/install.py --repo /absolute/path/to/elmos --uninstall --apply
```

卸载仅删除与安装收据哈希一致的包文件；用户修改过的文件、额外文件与原仓库内容保留。
本地安装器适用于受信仓库的维护操作，不是抵抗恶意并发文件系统修改的权限隔离系统。

## 最关键的诚实边界

“schema通过”“参考内核通过”“原生fixture通过”“真实DAP通过”“浏览器工作台通过”
“隔离provider通过”“真实600秒通过”“多租户安全与清理通过”是不同状态。
本包报告分别列出；不允许把前四项外推成后四项已经完成。
`examples/` 中时间、签名引用和清理收据只是数据形状，不是生产运行证明。

参阅 `provenance/SOURCES.md` 了解官方技术依据与已检索的既有 Elmos 设计资料。

## 完整性与报告

`FILES.sha256`覆盖静态交付内容；`reports/`和`VALIDATION_REPORT.*`为可再生成报告，不纳入该静态索引。
完整ZIP另有外部SHA-256文件。重跑样例会更新本地报告，不能把更新后的时间与原始验收混为一谈。
`validate_package.py`检查schema、依赖DAG、批次关系、状态与静态哈希；它不验证部署签名真实性。
