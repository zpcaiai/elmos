#!/usr/bin/env python3
"""Scaffold a complete Batch 46 runnable-smoke pack for one project.

    python3 scripts/batch46/scaffold_smoke_pack.py <project-root> --write

Runs the four stages in order — detect, derive, synthesize, emit — and writes a
`smoke/pack.json` index plus a short `smoke/README.md` aimed at the person who
just received the generated project and wants to see it run.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import derive_minimal_data
import detect_project_profile
import emit_one_click_runner
import synthesize_seed_data
from smoke_common import (
    DEFAULT_FREE_QUOTA_SECONDS,
    SCHEMA_PREFIX,
    canonical_digest,
    read_json,
    smoke_dir,
    utc_now,
    write_json,
)

README = """# 一键冒烟运行 / One-click smoke run

这个目录由 ELMOS Batch 46 生成。它给本项目补齐了“能跑起来”所需的最小临时数据，
并提供一条命令的启动入口。

```bash
./run-smoke.sh              # 启动 + 灌入种子数据 + 探活 + 冒烟断言
./run-smoke.sh --entry compose
./run-smoke.sh --no-hold    # 断言完立刻回收，不占用租约时间
make -f Makefile.smoke smoke
```

**免费运行额度 {quota_minutes} 分钟。** 到期后本次启动的所有服务会被停止、容器与卷会被删除、
临时数据会被清空。额度不会自动续期；如需延长必须显式执行：

```bash
python3 smoke/tools/smoke_lease.py extend --project . --seconds 300 \\
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
"""


def scaffold(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    root = Path(root).resolve()
    profile = detect_project_profile.detect(root)
    if args.write:
        write_json(smoke_dir(root) / "profile.json", profile)

    requirements = derive_minimal_data.derive(root, profile)
    if args.write:
        write_json(smoke_dir(root) / "minimal-data-requirements.json", requirements)

    seed_manifest = synthesize_seed_data.synthesize(root, args)
    runner_manifest = emit_one_click_runner.emit(
        root, args.write, Path(args.tools_source or Path(__file__).resolve().parent)
    )

    pack = {
        "schema": f"{SCHEMA_PREFIX}.smoke-pack/1",
        "generated_at": utc_now(),
        "generator": "elmos/scripts/batch46/scaffold_smoke_pack.py",
        "project_name": root.name,
        "polyglot": profile.get("polyglot", False),
        "languages": sorted({s["language"] for s in profile.get("stacks", [])}),
        "frameworks": sorted({s["framework"] for s in profile.get("stacks", []) if s.get("framework")}),
        "datastores": sorted({d["engine"] for d in profile.get("datastores", [])}),
        "digests": {
            "profile": profile.get("profile_digest"),
            "requirements": requirements.get("requirements_digest"),
            "seed_manifest": seed_manifest.get("seed_manifest_digest"),
            "runner_manifest": runner_manifest.get("runner_manifest_digest"),
        },
        "entries": {name: entry.get("status") for name, entry in runner_manifest.get("entries", {}).items()},
        "default_entry": runner_manifest.get("default_entry"),
        "free_quota_seconds": DEFAULT_FREE_QUOTA_SECONDS,
        "execution_status": "NOT_RUN",
        "unknown": runner_manifest.get("unknown", []),
        "unsupported": requirements.get("unsupported", []),
    }
    pack["pack_digest"] = canonical_digest({k: v for k, v in pack.items()
                                            if k not in ("generated_at", "pack_digest")})
    if args.write:
        write_json(smoke_dir(root) / "pack.json", pack)
        (smoke_dir(root) / "README.md").write_text(
            README.format(quota_minutes=DEFAULT_FREE_QUOTA_SECONDS // 60), encoding="utf-8"
        )
    return pack


def main() -> int:
    parser = argparse.ArgumentParser(description="Scaffold a Batch 46 runnable-smoke pack")
    parser.add_argument("project_root")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--seed")
    parser.add_argument("--sample")
    parser.add_argument("--sample-authorization")
    parser.add_argument("--accept-scan-findings", action="store_true")
    parser.add_argument("--corpus")
    parser.add_argument("--corpus-max-files", type=int, default=20)
    parser.add_argument("--tools-source")
    args = parser.parse_args()
    root = Path(args.project_root)
    if not root.is_dir():
        print(f"error: not a directory: {root}")
        return 2
    pack = scaffold(root, args)
    entries = ", ".join(f"{k}={v}" for k, v in pack["entries"].items())
    print(f"smoke pack for {pack['project_name']}: languages={pack['languages'] or ['?']} entries[{entries}]")
    if pack["unknown"]:
        print(f"unknown items that must be resolved before certification: {len(pack['unknown'])}")
    if not args.write:
        print("(dry run; pass --write to materialise the pack)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
