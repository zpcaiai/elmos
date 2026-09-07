# 生成线整条不能出活（已修，一行）

2026-08-26。触发：Mac 端跑 `verify-on-mac.sh` 第 3 步，project-synthesis-engine
40 条失败，其中 35 条同一个错：

```
ValueError: PROJECT_STRUCTURE_UNCLASSIFIED_ROOT:scripts
  src/elmos_project_synthesis/project_graphs.py:145
  <- workspace.render_workspace:663 -> render_project_structure
```

## 这不是测试问题，是生成线本身停摆

`render_workspace` 在**每一条路径**上都调 `render_project_structure`。所以
`generate_workspace` 对**任何**请求都抛异常——八门语言、任何 profile，一个工作区也产不出来。

用 08-21 的同一把仪器（`measure_generation_surface.py`）对照：

```
entity_scaling（1 个实体的生成文件数）
                08-21      修复前(今天)                              修复后
  java            57   ERROR:PROJECT_STRUCTURE_UNCLASSIFIED_ROOT:scripts   63
  python          53   ERROR:...                                            59
  csharp          56   ERROR:...                                            62
  typescript      51   ERROR:...                                            57
  go              49   ERROR:...                                            55
  kotlin          52   ERROR:...                                            58
  php             49   ERROR:...                                            55
  rust            53   ERROR:...                                            59
```

**08-21 还能出活，08-25 的基线快照里已经坏了。** 落在这两天之间。

## 根因：两份清单必须一致，但不一致

`workspace.render_workspace` 每次都发射 `scripts/projectctl.py`（one-command
controller；`cli.py` 甚至把它列进"归档必须包含的四个文件"），dotnet 目标另加
`scripts/local_runtime.py`。而 `project_graphs._SHARED_ROOT_KINDS` 里**没有
`scripts` 这一项**：

```python
_SHARED_ROOT_KINDS = {
    ".github": "continuous-integration",
    "database": "database",
    "deploy": "deployment",
    "docs": "documentation",
    "observability": "observability",
    "operations": "operations",
    "requirements": "requirements",
    "security": "security",          # <- 没有 "scripts"
}
```

于是分类器对自家发射器产出的目录报"未分类根目录"并失败关闭。
**失败关闭是对的——它拒绝描述一个它分不清的工作区。缺陷是那条缺失的条目。**

与 08-25 那个关系闸门缺陷同型：**一个改动要在所有闸门上找一遍**。
`scripts/projectctl.py` 加进发射面时，分类表没跟着改。

## 修法

```python
    "requirements": "requirements",
    # `scripts/projectctl.py` is emitted for every request and is one of the
    # four files `cli.py` requires an archive to contain; `scripts/` was simply
    # never classified, which failed every `render_workspace` closed.
    "scripts": "operations",
    "security": "security",
```

**kind 取既有的 `operations` 而不是新造一个**：controller 就是运维入口
（`operations/` 已经放着性能预算），而 `_STRUCTURE_KINDS` 是从这些 value 推导的，
新造 kind 会拓宽别的消费者读的词表。

## 零回归（同一棵树前后对比）

```
修复前 52 条 FAILED/ERROR
修复后 18 条
被这一行修好 34 条，新增 0 条
```

## 归属

**不是本会话造成的。** `project_graphs.py` 最后一次提交是 2026-08-10
(`dd32fcbfe`)，`deployment_guidance.py` 是 2026-08-09 (`8f5738086`)，
都早于 08-25/08-26 的改动；08-25 的基线快照里已经复现同样 35 条。

但有一条要说清楚：**08-25 我报过"project-synthesis 43 条既有失败，前后完全一致"。**
那句话本身没错——我确实没让它更坏——但我**没有去看那 43 条是什么**。
如果当时看一眼，这个停摆能早一天发现。
零回归对比只证明"我没弄坏"，不证明"它是好的"。

## 剩下的 18 条（未动，不是本次范围）

- `test_acceptance_runner.py` 4 条 ERROR（收集期）
- `test_production_matrix.py` 5 条
- `test_synthesis.py` 5 条：verification 的超时环境变量没生效
  (`assert 300.0 == 600`)、超范围超时没有在执行前拒绝、
  依赖同步的瞬时失败重试没发生、probe 的两条状态判定
- `test_project_graphs.py` 2 条 schema 严格性
- 另 2 条

这些看起来是另一个会话正在做的功能（测试先于实现），**没有认领就不动**。
