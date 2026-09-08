# 运行与恢复

校验：`python3 scripts/validate_package.py`；测试：`python3 scripts/run_checks.py --output-dir /tmp/elmos-aiopt-tests`。
安装计划：`python3 scripts/install.py --repo /absolute/path/to/elmos`；核对后加`--apply`。
卸载计划同命令加`--uninstall`；确认执行再加`--apply`。本地修改/新增文件保留，原AGENTS不动。

缺validation依赖：在包外venv按requirements-validation.txt安装；不要污染宿主依赖锁。
缺LangGraph/真实后端：native gate保持not_run，不用本包状态机冒充。
摘要不匹配：停止并审查；不要跳过校验或把sha当签名。修改后必须重新测试才reseal。
存在同名Skill：拒绝覆盖，按owner审查显式合并或直接路径调用；不自动升级。
权限/快照未知：fail closed，不能缓存兜底；搜索故障且授权可验证才lexical降级。
UNKNOWN_RESULT：隔离冲突workspace，先独立receipt/状态对账，不重发。
图升级：按版本路由旧线程或明确迁移，不把新图直接套旧checkpoint。
指标退化：关闭flag回旧安全路径，保留证据；不删除失败样本重新宣布提高。
所有新输出、venv、临时DB置于包外，reports是交付历史记录，不是实时任务库。

若安装目录已有本地修改，请从保留的原始未修改包执行卸载；从已修改安装目录自卸载会先因完整性检查而停止。
