# Elmos Knowledge–Skill–Model Foundry v3.0.0

## 定位

本包是 **Elmos Proof-Driven Agentic Harness / Repository Semantic Compiler v3** 的商业生产级能力规格与工程脚手架，将知识、Skill、Experience、Dataset、Model/Adapter、Evidence 与全部业务线统一到可发现、可执行、可验证、可回滚的体系中。

## 规模

- **41** 个 Meta-Skill / Capability Pack；
- **1310** 个原子 Proof-Carrying Skill；
- 相比 v2.0.0 新增 **24 个业务线包、852 个原子 Skill**；
- 优先级：P0=916，P1=368，P2=26，P3=0；
- 覆盖仓库执行 OS、Spring、跨语言、SQL/数据库、项目生成、前端/移动/小程序、重构、API/事件、大数据、云原生、QA、安全、性能、架构工作台、AI Agent/RAG、主机遗留、工业边缘、技术栈适配、客户交付和商业化。

## 关键原则

1. **Knowledge、Skill、Experience、Dataset、Model、Evidence 分离治理**。
2. **客户数据默认仅用于本租户执行与检索，禁止进入全局训练**。
3. **确定性验证优先于模型判断，模型不得覆盖编译、测试、安全和策略硬门**。
4. **权限归属具体 Environment、Attachment、Workspace 与 Tool Request，而非 Thread 全局状态**。
5. **发布单元不可变，回滚模型、Adapter、Skill、知识、工具链、策略和评测基线的完整组合**。
6. **所有大型任务记录机器 Wall-clock ETA、进度、恢复点、Token/GPU/工具/存储成本**。
7. **`specification-ready` 不等于 Runtime 已实现或可直接上线**。

## 目录

```text
skills/meta/                     启动时暴露的 41 个 Meta-Skill
skills/atomic/                   1310 个原子 Skill
registry/                        Skill、业务线、依赖和技术支持矩阵
schemas/                         强类型契约与证据 Schema
policies/                        权限、训练、发布、隔离和 Golden Route 策略
pipelines/                       业务线端到端执行流水线
coverage/                        覆盖审计、能力矩阵与 v2→v3 增量
certification/                   E0–E5 与生产上线硬门
database/                        PostgreSQL 元数据和执行持久化模型
tools/                           生成、校验、覆盖审计和 Package Diff 工具
```

## 校验

```bash
python tools/validate_package.py
python tools/coverage_audit.py
```

校验只证明包结构、Schema、引用、覆盖和内容完整性；不会替代真实编译器、数据库、集群、模型、客户仓库、长稳、影子和外部认证测试。

## 首要实施顺序

`Repository Execution OS → Semantic IR/Adapter → QA & Evidence → Spring/SQL Golden Route → Cross-language/Project Generation → Frontend/Data/Cloud/AI → Customer Delivery & Commercialization`。
## 统一评测与依赖完整性

- 1,310 项原子 Skill 均具备 `8 positive + 8 negative + 4 ambiguous + 4 adversarial` 的最低激活/路由/安全用例，共 **31,440** 条；
- 每项 Skill 均具备执行策略、回滚契约和 Conformance Manifest；
- Skill 依赖图必须无自依赖、无环、无悬空引用；
- CI 同时执行 JSON Schema、依赖 DAG、评测数量、占位符、空文件、覆盖矩阵与 Python 编译检查。

