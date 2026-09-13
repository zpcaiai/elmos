# 一键冒烟运行 / One-click smoke run

这个目录由 ELMOS Batch 46 生成。它给本项目补齐了“能跑起来”所需的最小临时数据，
并提供一条命令的启动入口。

```bash
./run-smoke.sh              # 启动 + 灌入种子数据 + 探活 + 冒烟断言
./run-smoke.sh --entry compose
./run-smoke.sh --no-hold    # 断言完立刻回收，不占用租约时间
make -f Makefile.smoke smoke
```

**免费运行额度 10 分钟。** 到期后本次启动的所有服务会被停止、容器与卷会被删除、
临时数据会被清空。额度不会自动续期；如需延长必须显式执行：

```bash
python3 smoke/tools/smoke_lease.py extend --project . --seconds 300 \
    --reason "手工排查登录流程" --actor "<你的名字>"
python3 smoke/tools/smoke_lease.py status --project .
python3 smoke/tools/smoke_lease.py stop --project . --reason manual
```

## 这里的数据是什么

`smoke/seed/` 下的全部内容都是一次性的合成数据，类别为 `ephemeral-disposable`，
仅由本项目自身的 DDL、OpenAPI 与环境模板推导而来。所有取值都带 `SMOKE-` / `smoke-`
前缀，便于一眼识别。**不要把它导入任何共享或生产数据库。**

## 这不是什么

冒烟结果只证明“能起来、能响应一次请求、能干净退出”。它不构成路线等价性、方言、
性能、安全、可访问性或任何迁移包认证的证据 —— 那些仍由各自的 Batch 门禁决定。

## 文件

| 文件 | 作用 |
| --- | --- |
| `smoke/profile.json` | 探测到的技术栈、数据存储、端口与未知项 |
| `smoke/minimal-data-requirements.json` | 跑起来所需的最小环境变量、数据集与桩上游 |
| `smoke/seed/` | 生成的一次性种子数据与环境文件 |
| `smoke/seed-manifest.json` | 每个数据产物的来源类别与摘要 |
| `smoke/assertions.json` | 本项目的冒烟断言定义 |
| `smoke/runner-manifest.json` | 各入口可用性与租约策略 |
| `smoke/runtime/` | 运行时产物：租约、日志、结果（可随时删除） |
