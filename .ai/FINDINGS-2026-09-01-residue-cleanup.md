# 清理 18 个 elmos-* 残留目录：门禁救了一次，而它拦下的是**我判据写错**

2026-09-01。执行者 Ethan（Mac 终端），脚本 `cleanup-elmos-residue.sh`（仓库根）。

## 0. 结果

18 个目录全清，`AIProjects/` 下只剩 `elmos`；其余 12 个项目未受影响。
删除后 `git fsck --connectivity-only` **rc=0**。磁盘 8.7Gi → **30Gi**。
零提交丢失——两条未合并分支已 fetch 进 `refs/residue/`。

## 1. 盘出来的结构：这不是 18 份可删的快照，是一张咬合的图

**`elmos` 的对象库借在残留目录上**，两级 alternates 链：

```
elmos/.git/objects/info/alternates
  -> elmos-final-delivery-20260831/.git/objects
       -> elmos-recreated-20260831/.git/objects
```

**删掉这两个中任何一个，活仓库当场坏。** 这是 `cat` 出来的，不是推的。

另有 **7 个是 git worktree**，寄生在另外 3 个残留目录的 `.git` 里：

| 宿主 | 寄生的 worktree |
| --- | --- |
| `elmos-batch32-closeout-20260830` | deepmerge-override-final / dependabot-final / openhands-complete |
| `elmos-recovery-20260830-1820` | commercial-capability-expansion-v2 / frontend-skills-closeout / frontend-skills-final |
| `elmos-swift-java-arkui-recovery-20260830` | pi-harness-main-merge |

先删宿主，那几个就成孤儿。**删除有拓扑序。**

## 2. 我在同一个判据上错了两次

### 2.1 第一次：把「借得到」当成「已合并」

判据 `git -C elmos cat-file -e <sha>`。第一次跑，7 个残留 HEAD **全报「不在」**，
我差点据此写下「每个都有未合并工作，一个都不能删」。

真因是 **VM 里 `/Users/stephen/...` 这个 alternates 路径解析不了**，git 看不见借来的对象。
把 VM 路径塞进 `GIT_ALTERNATE_OBJECT_DIRECTORIES` 重跑，7 个全翻成「在」。

**判据错了，结论就是反的**，而且两次结论都很像真的。

### 2.2 第二次（更贵）：把「存在」当成「可达」

改对之后我下了结论「7 个 HEAD 都在 elmos 里，删了不丢东西」，脚本照此写了门禁。
`--apply` 跑到第 3 步 **FATAL**：repack 完之后 `fecfd1e3b` 不见了。

- `cat-file -e` 在有 alternates 时回答的是「**能不能借到**」；
- `repack -a` 只复制「**从本仓库 ref 可达**」的对象。

**存在 != 可达。** `fecfd1e3b` 是 final-delivery 自己分支上的提交，elmos 没有任何 ref 指向它，
所以借得到但 repack 不会带走它。

我的第一反应是「门禁太严了」。**去查才发现门禁是对的，错的是我给它的判据。**

### 2.3 顺带暴露的第三个口径错：只测 HEAD

改判据时我顺手把范围也放大，扫了 7 个 repo 的**全部 30 个分支**（而不是 7 个 HEAD）：

- 28 个已在 elmos；
- **2 个真缺**：
  - `elmos-final-delivery-20260831` / `codex/zip-skills-completion-20260831` = `fecfd1e3b`
    （`fix(polyglot): accept inherited private bundle groups`, 08-31 15:55）
  - `elmos-production-runtime-continuation` / `codex/formal-assurance-complete-followup-20260831` = `d73adafe7`
    （`fix(formal-assurance): close trust...`, 08-31 06:47）

**第二条是只测 HEAD 必然漏掉的**：那个 repo 的 HEAD（main `527d4e79e`）在 elmos 里，
按 HEAD 口径它是「安全可删」——但它另一条分支上挂着真实修复。
**门禁没拦住的话，今天就没了。**

## 3. 最终做法（v2）

1. 抢救三个独有文件到 `.ai-archive/residue-20260901/`
   （其中 `integrate_polyglot_semantic_assurance_skills.py` 与 `tooling/` 下同名文件
   **md5 不同**：`98327ab9` vs `177f2b8e`，是另一个版本不是副本）；
2. 扫全部 ref，缺的 `git fetch` 进 `refs/residue/<目录>/<分支>`；
3. **复验所有分支都在**（硬门禁）+ `fsck`；
4. `git worktree prune`（清掉 9 条指向已消失 `/private/tmp` 的注册）；
5. 按 worktree → 其余 → repo 的序删除。

`elmos` 的 alternates 已挪成 `.git/objects/info/alternates.disabled-20260901`（81 字节，可删）。

## 4. 方法论（三条，按贵重程度排）

1. **「验证不过」先查判据，别先怀疑门禁太严。** 今天门禁两次都是对的，两次错的都是我。
2. **存在 != 可达；HEAD != 全部分支。** 两条都是我推断的而不是测出来的，两条都错。
   借来的对象、未被任何 ref 指向的提交——这类东西在「看得见」和「留得下」之间有真实落差。
3. **可逆比正确便宜。** alternates 是**挪开**不是删掉，所以 v1 炸在第 3 步时代价是零；
   删除放在全部验证之后，所以判据错了两次也没损失任何东西。

## 5. 没做的

- 没有独立复算 `git fsck --full`（只跑了 `--connectivity-only`）；
- 那两条抢救进来的分支**没有合并**，只是保住了，是否要合入由你决定；
- 磁盘从 8.7Gi 到 30Gi 中，**只有约 7G 来自本次删除**——v1 的 `repack -a -d` 在删除前就
  释放了约 15G（旧 pack 与重复对象）。别把两者算成一笔。
