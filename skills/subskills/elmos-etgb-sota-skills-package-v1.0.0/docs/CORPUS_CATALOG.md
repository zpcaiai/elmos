# Corpus catalog and selection policy

## 分层

- Public benchmark：可比较、可复验；
- Real OSS：构建与依赖复杂度；
- Synthetic fixtures：精确隔离语义；
- Fault-injected repos：错误恢复和恶意输入；
- Private hidden：降低记忆/泄漏；
- Customer golden：商业验收。

## 当前锁定语料

`corpora/corpus-lock.yaml` 包含 17 个固定 commit，覆盖 Spring PetClinic、Struts Examples、Apache Roller、Broadleaf LegacyDemoSite、RealWorld、RepoTransBench、RustRepoTrans、TransRepo、ProjectEval、DevEval、HumanEvo、RepoExec、JHipster、Sakila、SQLancer、SQLGlot 和 AWS migration tester。

## 纳入标准

1. 可合法使用，许可证/商标/数据审查完成；
2. commit 可固定，构建可容器化；
3. 测试可执行或可构造独立 Oracle；
4. 不含真实秘密、恶意二进制或无法隔离的安装脚本；
5. 能填补明确 capability/scale 空白；
6. 记录来源、时间、过滤和已知缺陷。

## 污染控制

公开测试只作为一层；release/golden 必须含私有变体、时间切分 commit、隐藏测试和变形用例。Agent 不得通过工具读取 hidden test 仓库。
