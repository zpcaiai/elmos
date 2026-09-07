#!/usr/bin/env python3
"""把商业化门禁 job 幂等地追加到 .github/workflows/ci.yml。

为什么是脚本而不是直接改文件：ci.yml 在本会话的环境里是受保护文件，
远程写不了。与其在文档里留一段"请手动粘贴这段 YAML"（粘错缩进就是一个
永远不会跑的 job，而 job 不跑和 job 通过在 Actions 页面上长得很像），
不如给一个能自己检查结果的脚本。

用法：
    python3 scripts/commercial/append_ci_gates.py            # 追加
    python3 scripts/commercial/append_ci_gates.py --check    # 只检查，不改动

退出码：0 已就绪 / 1 追加失败或校验不通过 / 2 --check 下发现缺失
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

WORKFLOW = Path(".github/workflows/ci.yml")
MARKER = "commercial-gates"

JOB = """
  commercial-gates:
    name: 商业化门禁（定价目录 / 单位经济 / 支付迁移）
    runs-on: ubuntu-latest
    # 这些门禁的作用是"没算清楚就不许发布"，因此必须与构建同权重，
    # 不能设 continue-on-error —— 那等于把门禁降级成一条提示。
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: 定价目录发布门禁
        run: python3 scripts/commercial/validate_pricing_catalog_publication.py

      - name: 单位经济学（成本输入未填时应判 NOT_RUN 而不是 0）
        run: python3 scripts/commercial/unit_economics.py --check

      - name: 生成能力支持矩阵
        run: python3 scripts/operations/validate_generation_support_matrix.py

  payment-database-gates:
    name: 支付回调数据库门禁（PostgreSQL 17.5）
    runs-on: ubuntu-latest
    services:
      postgres:
        # 仓库目标版本是 17.5。本地只验到 16.13，两者语义一致，
        # 但"语义一致"是推断，这个 job 是证据。
        image: postgres:17.5
        env:
          POSTGRES_PASSWORD: elmos
          POSTGRES_DB: elmos_ci
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 10
    env:
      DATABASE_URL: postgresql://postgres:elmos@localhost:5432/elmos_ci
    steps:
      - uses: actions/checkout@v4

      - name: 应用全部迁移
        run: |
          for file in $(ls modules/persistence/src/main/resources/db/migration/V*.sql | sort -V); do
            psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -f "$file"
          done

      - name: 回调台账与幂等
        run: bash tooling/payment-db-verify/verify_payment_callbacks.sh

      - name: 订阅激活存储函数
        run: bash tooling/payment-db-verify/verify_subscription_activation.sh

      - name: 订单目录与租户隔离
        run: bash tooling/payment-db-verify/verify_order_directory.sh
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="只检查是否已追加，不修改文件")
    arguments = parser.parse_args()

    if not WORKFLOW.exists():
        print(f"找不到 {WORKFLOW}。请在仓库根目录运行。")
        return 1

    content = WORKFLOW.read_text(encoding="utf-8")

    if f"\n  {MARKER}:" in content:
        print(f"{WORKFLOW} 已包含 {MARKER}，无需追加。")
        return 0

    if arguments.check:
        print(f"{WORKFLOW} 尚未包含 {MARKER}。运行不带 --check 的本脚本以追加。")
        return 2

    if "\njobs:\n" not in content and not content.startswith("jobs:\n"):
        print(f"{WORKFLOW} 里找不到顶层 jobs: 段，拒绝盲目追加。")
        return 1

    updated = content.rstrip("\n") + "\n" + JOB

    # 追加前先确认 YAML 仍然可解析。宁可不改，也不要把 CI 配置弄坏——
    # 一个语法错误的 workflow 是**整个 CI 不跑**，比少一个 job 严重得多。
    try:
        import yaml  # type: ignore
    except ImportError:
        print("提示：未安装 PyYAML，跳过语法校验。建议 pip install pyyaml 后重跑。")
    else:
        try:
            parsed = yaml.safe_load(updated)
        except yaml.YAMLError as error:
            print(f"追加后 YAML 无法解析，已放弃修改：{error}")
            return 1
        jobs = (parsed or {}).get("jobs") or {}
        for expected in (MARKER, "payment-database-gates"):
            if expected not in jobs:
                print(f"追加后仍找不到 job {expected}，已放弃修改。")
                return 1

    WORKFLOW.write_text(updated, encoding="utf-8")
    print(f"已向 {WORKFLOW} 追加 {MARKER} 与 payment-database-gates 两个 job。")
    print("请 review 后再提交：这两个 job 会让未通过的商业化门禁阻断合并。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
