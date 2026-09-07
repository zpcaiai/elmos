# Corpus governance

本目录只分发仓库元数据和固定 commit，不再分发第三方源代码。执行 `scripts/fetch_corpora.py` 前必须：

1. 完成许可证、专利、商标、数据与出口控制审查；
2. 将 `license_review` 从 `required` 改为 `approved`；
3. 在无生产凭据、无宿主 Docker socket、默认断网的隔离环境中构建；
4. 对下载内容做 SHA/commit 校验、恶意脚本扫描和依赖锁定；
5. 发布报告中记录语料版本、时间切分和任何排除项。

`release` profile 会把未批准语料视为阻断项；本包的离线 `smoke` 不需要下载任何仓库。
