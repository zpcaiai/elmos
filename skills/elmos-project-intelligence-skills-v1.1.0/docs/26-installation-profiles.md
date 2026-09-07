# Installation Profiles

| Profile | Skill count | Intended use |
|---|---:|---|
| `bootstrap` | 14 | 先建设底座、作业编排、缓存、观测、评测、ETA 与认证。 |
| `reader` | 16 | 在线代码阅读、导航、讲解、学习路径与项目问答。 |
| `architecture` | 26 | 架构、功能、流程、数据、API/事件、图表、影响与治理分析。 |
| `artifacts` | 15 | 图表、文档、PPT、报告包、版本/锁定与 Git 交付。 |
| `conversion` | 33 | 与 Elmos 整项目生成、语言转换和老系统翻新闭环。 |
| `enterprise` | 24 | 企业治理、连接器、大仓、部署、认证和商业交付。 |
| `full` | 44 | 完整 44 技能生产实施包。 |

## 选择原则

- 新项目优先 `bootstrap`，再按阶段追加。
- 已有基础设施且只做代码理解可直接使用 `reader`。
- Profile 是安装集合，不代表可以跳过技能的真实依赖；执行时仍以 `depends_on` 和 batch 门禁为准。
