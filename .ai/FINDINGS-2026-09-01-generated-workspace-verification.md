# 生成线缺的那一半：生成出来的项目到底能不能跑

2026-09-01。仪器：`.ai/measurement-2026-08-26/verify_generated_workspaces.py`。
证据：`cloud-generation-evidence.json`（3 实体）、`cloud-generation-evidence-1entity.json`（1 实体）。
**本轮只在云端跑，构建/启动/CRUD/RLS 仍是 `NOT_RUN`——那部分只有 Mac 能出。**

## 为什么要做这个

整个测量从「生成中小型项目的准确度、完整度究竟能达到多少」开始。
现有的 `generation-surface` 证据回答了**生成器接受什么**：24/48 组合、8 语言、
最多 20 实体、每格文件数。但它自己在最要紧的那个字段里写着：

```json
"verification_status": {"status": "NOT_RUN",
 "reason": "verification.verify_workspace needs the pinned macOS toolchains;
            build/startup/CRUD/RLS results are not produced by this run."}
```

**没有人验过生成出来的项目能不能构建、能不能起来、CRUD 通不通。**
`pytest` 165 通过也不是这个答案——它测的是生成器，不是产物。

## 仪器的三条硬规矩

1. **接受集是推导出来的，不是写死的。** 格子来自问 `approve_request` 拿它的拒绝码。
   写死一个 24，引擎哪天改了，仪器会安静地测错矩阵。
2. **`NOT_RUN` 永远不算通过也不算失败。** 表头是三个数，不是一个百分比。
3. **逐格落盘。** 每格结果在下一格开始前写入，`--resume` 跳过已记录的——
   Mac 上全量要几小时，断了必须能接着跑。

## 云端结果：实体数一变，接受矩阵就塌一半

```
                        1 实体            3 实体
REFUSED_BY_INTAKE         24               24     ← in-memory+jwt/oidc、postgresql+none
生成成功                  24               12
GENERATION_ERROR           0               12     ← <LANG>_PRODUCTION_PROFILE_SINGLE_ENTITY_ONLY
```

12 个报错整整齐齐是 **6 种语言 × 2 种 auth**，只在 `postgresql` 下：

```
csharp / typescript / go / kotlin / php / rust
  postgresql|jwt|*    DOTNET_/TYPESCRIPT_/GO_/KOTLIN_/PHP_/RUST_PRODUCTION_PROFILE_SINGLE_ENTITY_ONLY
  postgresql|oidc|*   同上
```

**`in-memory` 下 8 种语言在 3 实体全部生成成功**，所以这条限制专属于 production/postgresql 侧。

### 这不是新发现，是把已知的那条量化了

`FINDINGS-2026-08-25-remaining-items.md` §6 第一行就写着
「6/8 语言多实体 | 特性 | 按 §3.1 的顺序逐目标改」。**已知。**
本轮补的是它**值多少**：

> **现有证据里「accepted: 24」这个数，只在 1 实体下成立。**
> 实体数 ≥2 时，production（postgresql）profile 只剩 **java + python 两种语言**，
> 接受组合 **24 → 12**。

一个只能装一个实体的「中小型项目」不是中小型项目。**任何引用「8 语言 / 24 组合」的
说法，都必须同时写上「1 实体」这个限定**，否则它描述的是一个不存在的能力。

各格文件数（1 实体）：in-memory 47–54，postgresql 55–63。3 实体时 java 62→71、python 50→59。

## 一个被我降级的 FAILED

kotlin 三格在云端报 `FAILED`，查下去是
`could not resolve plugin artifact 'org.jetbrains.kotlin.jvm:...:2.2.20'`
——**这个容器到不了 Gradle 插件仓库**（Maven Central 同样不通）。
构建够不到依赖仓库，对生成的项目本身什么都没说。

引擎的自动重试是**刻意窄的**：只对 `uv sync --locked`，因为 `--locked` 意味着
「要么精确解出锁文件要么失败」，这才使重试安全——这个设计是对的，不该动。
所以**降级放在测量这一侧**：仪器识别到不可达依赖的标记就把该格记为
`NOT_RUN_UNREACHABLE_DEPENDENCIES`，同时**保留引擎原话** `engine_status: FAILED`
和触发降级的标记。

```
in-memory|none|kotlin   -> NOT_RUN_UNREACHABLE_DEPENDENCIES
                           engine said: FAILED | marker: could not resolve plugin artifact
```

**在一个网络受限的 CI 里，这三格会被当成产品缺陷报出去。** 它们不是。

## 负控制（三条，全过）

| 用例 | 期望 | 实得 |
|---|---|---|
| 已知不支持的组合 `in-memory\|jwt` | 拒绝 | `REFUSED_BY_INTAKE:PROFILE_COMBINATION_UNSUPPORTED:in-memory:jwt` |
| 云端无钉死工具链 | 报「没测」 | `PARTIAL`，`toolchain:{NOT_RUN}`；python 的 `build-analysis` 6 项 PASSED |
| **篡改一个生成的源文件** | 必须拒绝 | `VERIFICATION_ERROR: GENERATION_MANIFEST_FILE_DIGEST_INVALID` |

第三条值得单说：**第一次我随手改的是 `python/.venv/bin/activate_this.py`，验证器毫无反应**
——那是验证过程自己造的 venv 产物，不在生成清单里。换成 `python/tests/test_api.py` 才立刻炸。
**一个改了没反应的变异测试等于没做变异测试**，必须确认改的是被摘要绑定的文件。

## 另一件差点出错的事

我云端那份 project-synthesis 副本比仓库**落后 13 个文件**（2 个新模块 + 11 个改动）。
拿它测就是在测一个不存在的引擎。本轮是把仓库当前源码打包 stage 过来跑的。
**本地副本的新鲜度必须每次核对，不能假设。**

## 云端到此为止，剩下的只有 Mac 能出

`build-analysis` 这一档**只有 python 真跑起来了**（6 项 PASSED）；
java/csharp/typescript/go/php/rust 都停在 `toolchain: NOT_RUN`——工具链检查没过就不会往下走。
**构建、启动、CRUD、RLS 四档在云端一次都没执行过。**

Mac 上的跑法（先一格证明回路，再放全量，`--resume` 可断可续）：

```
uv --directory engines/project-synthesis-engine run --locked python \
  "$(pwd)/.ai/measurement-2026-08-26/verify_generated_workspaces.py" \
  --languages python --persistence postgresql --auth-modes jwt \
  --out /tmp/elmos-ws --json /tmp/elmos-gen-evidence.json
```

**在那份证据出来之前，这条线的「准确度、完整度」仍然只有生成侧的数，没有执行侧的数。**
本报告没有改变这一点，它只是把生成侧的数说准了：**24 是 1 实体下的数，多实体是 12。**
