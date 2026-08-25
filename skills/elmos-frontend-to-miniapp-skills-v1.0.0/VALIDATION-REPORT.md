# Elmos Frontend → MiniApp Skills Package 验证报告

- 包版本：`1.0.0`
- 验证日期：`2026-08-19`
- 验证范围：Skills 包结构、契约、Schema、fixture、依赖关系、安装卸载、安全扫描、校验和与归档可用性
- 当前结论：`PASSED`

## 1. 验证摘要

| 项目 | 结果 |
|---|---:|
| Skills | 22 / 22 通过 |
| 独立任务 ID | 40 / 40，唯一且连续 |
| JSON Schema | 14 / 14，Draft 2020-12 自验证通过 |
| 有效 fixtures | 14 / 14，通过对应 Schema |
| Python 单元测试 | 28 / 28 通过 |
| Codex 安装 smoke test | 22 / 22 安装、状态检查与卸载通过 |
| Claude Code 安装 smoke test | 22 / 22 安装、状态检查与卸载通过 |
| 依赖图 | 无未知依赖、无自依赖、无环 |
| 必需文档、模板和示例 | 通过 |
| Secret/私钥模式扫描 | 0 项发现 |
| 包内文件 SHA-256 | 全部通过 |
| ZIP 解压后复验 | 通过 |
| TAR.GZ 解压后复验 | 通过 |

## 2. 实际执行的验证

```bash
python3 scripts/validate_skills.py --json
python3 scripts/validate_schemas.py --json
python3 scripts/check_no_secrets.py --json
python3 -m unittest discover -s tests -p 'test_*.py' -v
./verify.sh --json
```

`verify.sh` 还会在临时目录中，把 22 个 Skills 分别安装到 `.agents/skills/` 与 `.claude/skills/`，检查安装标记和技能集合，再执行安全卸载；因此不是只检查静态文件是否存在。

## 3. 关键契约验证

已验证以下不变量：

- `.agents/skills/<skill>/SKILL.md` 中的名称、描述、版本、任务 ID 与 manifest 一致；
- 22 个技能均带 `references/contract.md`、`assets/output-contract.yaml` 和调用示例；
- `MAPP-001` 至 `MAPP-040` 无缺号、无重复；
- 四个平台生成器依赖组件、状态事件生命周期、样式和依赖迁移计划；
- WebView、整页 Canvas、截图和静默删除默认被禁止；
- Flutter 必须通过 Dart AST/Widget 语义重建；
- C/D/E 兼容项必须披露；
- 客户端不得保存真实 AppSecret、私钥或 refresh token；
- 上传、审核和发布不是默认自动副作用，必须经过权限与审批。

## 4. 验证边界

本报告证明的是**Skills Package 本身可安装、可解析、可验证并具备完整实施契约**。本包不是已编译完成的 Elmos 转换器二进制，因此本报告不声称已经对真实业务仓库完成四个平台编译、真机测试或上架审核。

这些运行期结论必须在后续实现转换引擎后，由本包定义的官方工具链构建、差分测试、视觉回归、隐私安全和迁移证据门禁逐项目产生；账户权限、平台资质或工具链不可用时，状态必须保持 `blocked` 或 `unknown`。
