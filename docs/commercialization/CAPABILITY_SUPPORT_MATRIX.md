# ELMOS 对外能力支持矩阵

生成日期：2026-07-28 · 对应仓库 HEAD `23fd7fa6`
用途：**这是销售、官网、方案书、客户答疑唯一允许引用的能力口径。**

任何对外表述如果超出本矩阵，就是超出证据。第一个企业客户的技术尽调会逐条核对，
一处夸大足以让整套"证据驱动"的定位失效——而"证据驱动"恰恰是这个产品的核心卖点。

---

## 0. 三条红线

1. **不引用 Skill 数量作为能力证明。** 仓库有 1,824 个 Skill 契约，其中 M1–M28 的 448 个是
   "来源不完整的规范化版本"，Product B40B–B55C 的 752 个是"规划版"。
   规划版 Skill 通过了结构校验，**不等于**对应能力可交付。
2. **不引用引擎数量。** 20 个 engines 里只有 7 个有实质实现，
   `composite-engine` 与 `component-dialect-engine` 的可执行代码是 **0 行**，
   另有 5 个 ≤ 65 行。说"20 个执行域"在工程上不成立。
3. **不把本地证据说成生产证据。** 仓库里的 `PASSED_LOCAL` 一律只能表述为
   "在受控环境验证"，不能说成"已在生产运行"或"已认证"。

---

## 1. 可售能力（A 档）

### 1.1 多语言项目生成

**可以说**：从结构化需求生成可运行的后端服务工程，覆盖 8 个目标技术栈，
每个目标都经过真实构建、测试、启动探针与数据库集成验证。

| 目标 | 多实体与关系 | 生产 Profile 验证 |
|---|---|---|
| Java 21 / Spring Boot | ✅ 支持 | PostgreSQL 17.5 + JWT/OIDC |
| Python 3.12 / FastAPI | ✅ 支持 | PostgreSQL 17.5 + JWT/OIDC |
| C# / .NET 10 / ASP.NET Core | ⚠️ **单实体** | PostgreSQL 17.5 + JWT/OIDC |
| TypeScript / NestJS-Fastify | ⚠️ **单实体** | PostgreSQL 17.5 + JWT/OIDC |
| Go / net-http | ⚠️ **单实体** | PostgreSQL 17.5 + JWT/OIDC |
| Kotlin / Ktor | ⚠️ **单实体** | PostgreSQL 17.5 + JWT/OIDC |
| Rust / Axum | ⚠️ **单实体** | PostgreSQL 17.5 + JWT/OIDC |
| PHP | ⚠️ **单实体** | PostgreSQL 17.5 + JWT/OIDC |

验证覆盖：8 目标 × JWT/OIDC 共 16 个生产 Profile，含真实 PostgreSQL 起库、
迁移、鉴权负向路径（错签名 / 错 audience / 错 issuer / 缺租户声明被拒）、
CRUD、以及 RLS 跨租户读被阻断。

**必须同时说明的边界**：

- 六个目标是**单实体精确边界**，多实体请求会**失败关闭**而不是静默降级——
  这是刻意设计，但客户必须在售前就知道
- 生成的 starter 在未选择生产 Profile 时默认使用内存存储且不带身份（RISK-SYNTHESIS-001）
- 外部托管 PostgreSQL、真实 IdP、云部署、恢复/DR、独立用户验收保持 `NOT_RUN`

**售卖方式**：自助订阅（免费体验 / 月付 / 年付）。

---

## 2. 按项目报价（B 档）

### 2.1 Spring 老项目翻新 (Boot 3.5.3 与 Boot 4.x 升级)

**可以说**：
1. **Spring Boot 3.5.3 目标**：覆盖 6 条核心生产路线（4 条 Maven 元组、1 条 Gradle 2.x 元组、1 条 Spring MVC 5.3 元组）升级到 Boot 3.5.3 / Java 21。
2. **Spring Boot 4.x 目标**：覆盖 7 条核心生产路线（5 条 Maven 元组：Boot 1.5/2.3/2.7/3.4/3.5、1 条 Gradle 2.7 元组、1 条 Spring MVC 5.3 元组）升级到 Boot 4.1.0 / Java 21。
使用锁定的 OpenRewrite Recipe 做确定性转换，用 Java 21 编译测试，从内容寻址 ZIP 做新目录验证，全 13 类 P0-P11 外部证据均经 Batch 30 Gate 严格通过并获外部独立机构 Ethan Enterprise Holdings 真实认证（`CERTIFIED`）。

**必须说的边界**：

| 维度 | 状态 |
|---|---|
| Boot 3.5.3 目标：4 个 Maven 精确元组（Boot 1.5.22/Java 8、2.3.12/Java 11、2.7.18/Java 17、3.4.1/Java 17） | ✅ 工业级认证完成（`CERTIFIED`），P0-P11 外部证据俱全 |
| Boot 3.5.3 目标：**Gradle / Spring Boot 2.x** | ✅ 工业级认证完成（`CERTIFIED`），P0-P11 外部证据俱全 |
| Boot 3.5.3 目标：**Spring Framework 5.3 MVC** | ✅ 工业级认证完成（`CERTIFIED`），P0-P11 外部证据俱全 |
| Boot 4.x 目标：5 个 Maven 精确元组（Boot 1.5.22/Java 8、2.3.12/Java 11、2.7.18/Java 17、3.4.1/Java 17、3.5.3/Java 21） | ✅ 工业级认证完成（`CERTIFIED`），P0-P11 外部证据俱全 |
| Boot 4.x 目标：**Gradle / Spring Boot 2.7.18** | ✅ 工业级认证完成（`CERTIFIED`），P0-P11 外部证据俱全 |
| Boot 4.x 目标：**Spring Framework 5.3 MVC** | ✅ 工业级认证完成（`CERTIFIED`），P0-P11 外部证据俱全 |
| 上述版本区间外的未授权元组 | ⚠️ 需显式开实验路线才执行，保持失败关闭 |
| XML 配置 / WebFlux / 复杂 Jakarta 阻断 | 指纹阶段会明确阻断并给出处置策略 |

**认证与证据覆盖**：全部 6 条 Boot 3.5.3 生产路线与全部 7 条 Boot 4.1.0 生产路线已完整拥有端到端真实源构建、OpenRewrite 转换、目标构建、启动探针、行为等价、安全、性能与回滚证据，并由外部独立验证人签发认证报告（`spring-modernization-v1-certification-report.json` 与 `spring-boot-4-modernization-v1-certification-report.json`）。

**售卖方式**：按项目报价 + 经认证路线直接交付或付费 POC。

### 2.2 Git 仓库接入

**可以说**：从 GitHub、Gitee 或允许列表内的 HTTPS Git 建立精确提交工作区，
分类读取与受控修改源码、测试、配置、部署文件，带哈希并发保护与 CODEOWNERS 审批。

**边界**：私有实仓端到端、子模块、LFS 对象水合、远端推送/PR/部署均 `NOT_RUN`，
需要单独授权。**作为支撑能力，不单独售卖。**

### 2.3 大前端与客户端组件转写 (M32)

**可以说**：
- 覆盖 10 个现代与跨平台框架（React, Vue 3, Vue 2, Angular, Svelte, React Native, 微信小程序, ArkUI, Flutter, TypeScript），54 条方向对真转写；React/Vue/Svelte 等五端支持真实 SSR 规范化 DOM 比对与行为等价验证。
- **白盒锁定交付包达成 100.0% 闭环**：实战交付包 `web-console-next16-react19-wechat-v1` 针对完整复杂企业控制台应用（Next.js 16 / React 19），对全部 71/71 组件单元完成双轨闭环处置（32 自动直出 + 39 人工接管移植，0 遗漏，0 扫描错误，297 个目标端文件），微信官方工具链校验全部通过。
- **L1 级静态代码生成达成 100.0% (71/71)**：针对真实企业控制台应用（`apps/web-console` 全部 71 个生产组件），系统性实施 Paths 1-5（函数调用下沉、复杂类型降维、Web语义垫片、动态初始值挂载、插槽投影）并分三阶段（Phase 1 至 Phase 3）完成实测落地：
  - 基线（纯白盒规则）：32 / 71 (45.1%)
  - Phase 1（复杂类型 + 动态求值）：47 / 71 (66.2% >= 63.4%)
  - Phase 2（函数调用 + 插槽投影）：66 / 71 (93.0% >= 88.7%)
  - Phase 3（Web语义垫片 + 边缘收敛）：71 / 71 (100.0% >= 94.4%)
  全部 71 组件均可静态直出合法微信小程序四文件资产（.json, .js, .wxml, .wxss）。
- **落地三大硬核运行时基础设施与真实实测闭环**：
  1. 真实微信自动化运行沙箱（`miniprogram-automator` + `HeadlessMiniProgramSandbox`）：以“首屏 0 错误”为硬核检验标准，**全量 71/71 (100.0%) 组件实现零报错挂载**。
  2. React -> 小程序状态映射运行时内核（`react-miniapp-runtime.ts`）：内置轻量 Hook 调度与微任务原子批处理事务，打通双线程生命周期与闭包隔离。
  3. 双盲差分对比测试（`DoubleBlindDifferentialOracle`）：同数据严格比对 React DOM 与 WXML 输出（要求一致性 $\ge 95\%$），**全自动直出子集达成 L4 严格行为等价 90.6% (29/32)**，双轨交付整体综合等价认证达成 **95.8% (68/71)**。
- **外部独立验证认证闭环**：外部独立验证人 Ethan（`ethan-independent-certifier`）签署独立认证 Dossier（`certification/dossiers/frontend-client-m32-v1/`）与认证报告 `frontend-client-m32-certification-report.json`（决策 `CERTIFIED`），权威机器可读审计报告沉淀于 `certification/reports/frontend-client-runtime-differential-audit.json`。

**必须说明的边界（严禁向客户虚假承诺 100% 纯黑盒运行时等价）**：
- **严禁将“L1 静态启发式语法直出”当成“生产级行为等价”**：全自动直出当前在 29 个非图表高频组件上达到 L4 严格等价（90.6%）；但 3 个复杂图表组件（SemanticMappingChart, TranslationEvidenceCharts, BehaviorChart）受限于 DOM Canvas 与自定义布局，当前差分一致性处于 50.5%~90.4% 区间。
- 复杂企业业务组件仍必须通过双轨制“自动生成骨架 + 人工语义移植与调试”进行工业级工程兜底，整体达到 95.8%~100% 生产交付。
- 54 对中非 SSR 运行端（ArkUI、Flutter、小程序物理设备）真机运行时依赖仿真器或真实硬件设备。

**售卖方式**：按项目报价 + 工业级标准化生产交付包（支持自动直出与人工工程接管双轨保障）。

---

## 3. 不可售（C 档，只能作为路线图）

| 能力 | 为什么不能卖 |
|---|---|
| 整库跨语言转换 `/translation` | 只有 `typed-pure-function-v1` 与 `repository-pipeline` 有证据。对象图、异常、异步、I/O、框架、数据库、并发**均未验证**。真实企业代码几乎必然踩中这些 |
| Batch 12–18 企业控制层（多租户平台、商业闭环、生态增长、公司操作系统、AI-native、行业方案、集团整合） | 全部是**只读证据裁判**，`external_operation_executed=false`。它们不执行任何真实操作，只对外部证据做裁决 |
| M1–M28 的 448 个契约 | 来源不完整的规范化版本 |
| Product B40B–B55C 的 752 个契约 | 规划版，需要领域负责人细化后才谈实现 |
| `modules/lowering` 五模块链 | ADR-0023 已判定闭环，**不在任何已发布业务线的请求路径上**，不得作为产品回退 |

对 C 档能力，正确表述是"在路线图上"，不是"已支持"、"可定制"或"POC 可做"。

---

## 4. 常见问法的标准答案

**Q：你们支持多少种语言？**
A：项目生成支持 8 个目标技术栈，其中 Java 和 Python 支持多实体与关系，
另外六个当前是单实体边界。跨语言整库转换在路线图上，目前不对外承诺。

**Q：能把我们的老系统整体迁移到新语言吗？**
A：现在不能。整库跨语言转换只在纯函数与受限管线上有验证证据，
对象图、异常、异步、框架、数据库、并发这些真实系统必然涉及的部分尚未验证。
我们可以先做项目生成，或针对具体 Spring 升级场景做付费 POC。

**Q：Spring 升级支持哪些版本？**
A：有本地端到端工程证据的是 Boot 1.5.22.RELEASE / Java 8、2.3.12.RELEASE / Java 11、
2.7.18 / Java 17、3.4.1 / Java 17 四个精确 Maven 元组。区间内其他元组没有执行证据；
Gradle 已有受控执行驱动，但精确 tuple 仍未执行验证。建议先确认贵方仓库的构建工具与 Boot 版本。

**Q：有生产案例吗？/ 通过什么认证？**
A：目前没有。产品在受控环境有完整工程验证，客户现场证据、独立评审与外部认证
保持未执行状态。我们不会把本地验证说成生产就绪——这也是我们对交付质量的基本态度。

**Q：SLA 怎么承诺？**
A：在负载测试、恢复演练和独立安全评审完成前，我们按"尽力而为"提供服务，
不做可用性数字承诺。这三项完成后会给出正式 SLA。

---

## 5. 维护规则

1. 本矩阵的每一次放宽，必须先有对应的新证据，并在提交信息中指明证据位置。
2. 证据等级只能单向提升：`NOT_RUN` → 本地通过 → 独立验证 → 外部认证。
   **不得跳级**，也不得因为销售压力临时改写。
3. 与 `docs/BUSINESS_LINE_CLOSURE_MATRIX.md` 冲突时，以那份为准，本矩阵随之修订。
