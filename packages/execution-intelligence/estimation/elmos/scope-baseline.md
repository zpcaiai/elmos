# SCOPE_BASELINE

- 根：`/sessions/rcw-01selignehxwntgsnfurjwmx/mnt/elmos`
- 文件 45,790，字符 366,736,507，一次性读取估算 95,021,753 tokens（`cjk-aware-heuristic`）
- Skill 文件 9,212，目录常驻 556,211 tokens
- 语言身份 17 种，构建体系：cargo, go, gradle, make, maven, npm, pub, python, swiftpm
- Git：有

## 语言分布（按文件数）

| 语言 | 文件数 |
|---|---|
| python | 2,875 |
| java | 1,294 |
| typescript | 885 |
| csharp | 378 |
| javascript | 300 |
| go | 259 |
| rust | 254 |
| cpp | 178 |
| swift | 145 |
| objc | 127 |
| react | 66 |
| flutter | 54 |
| php | 37 |
| arkts | 10 |
| kotlin | 9 |

## 体量最大的目录

| 目录 | 文件数 | 估算 tokens |
|---|---|---|
| verification-packs | 6,283 | 26,560,165 |
| client-packs | 4,793 | 20,276,057 |
| routes | 4,638 | 8,734,313 |
| agent-skills | 8,374 | 7,345,257 |
| skills | 7,739 | 6,144,810 |
| test-suites | 1,991 | 4,248,621 |
| docs | 528 | 3,477,424 |
| engines | 1,051 | 3,382,441 |
| .agents | 2,595 | 2,360,720 |
| apps | 1,801 | 2,265,097 |

## 路由矩阵

- 权威源：`routes/inventory.json`
- 声明路线数：**156**（列表长度 156）
- 语言：13 门
- 磁盘上的路由目录：176
- PENDING_ANALYZER：flutter, kotlin, react

## 风险与缺口

高 3 · 中 1 · 低 3

| ID | 级别 | 类型 | 说明 | 需人工决策 |
|---|---|---|---|---|
| route-directory-count-differs | low | informational | 176 route directories on disk vs declared route_count=156; surplus reconciled: 20 retained pack(s) = deprecated_route_keys of 'eleven-language-complete-110' | 否 |
| pending-analyzer-flutter | high | missing-capability | language 'flutter' is declared in the matrix but its analyzer is PENDING_ANALYZER | 否 |
| pending-analyzer-kotlin | high | missing-capability | language 'kotlin' is declared in the matrix but its analyzer is PENDING_ANALYZER | 否 |
| pending-analyzer-react | high | missing-capability | language 'react' is declared in the matrix but its analyzer is PENDING_ANALYZER | 否 |
| historical-denominators-in-prose | low | informational | 9 non-authoritative document(s) quote an older denominator. That is usually correct as history; it is listed so nobody quotes one by accident. | 否 |
| oversized-skills | medium | context-pressure | 40 SKILL.md bodies exceed the activation-cost threshold | 否 |
| unscanned-files | low | coverage | 13 files were skipped (too large or not UTF-8) and are not in any total | 否 |

> A gap with needs_human_input=true blocks a production-grade forecast; the auditor will not invent the answer.
