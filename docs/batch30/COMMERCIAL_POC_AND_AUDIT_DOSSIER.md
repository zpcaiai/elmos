# Spring 现代化企业级商用 PoC 实施与认证审查白皮书 (Batch 30 Audit Dossier)

**版本**: 1.0.0  
**发布时间**: 2026-09-09  
**维护组织**: ELMOS Java Modernization Team & Batch 30 Framework Pack Maintainers  
**适用范围**: Spring Boot 1.5–3.4 / Spring MVC / Java EE Servlet 2.5/JSP → Spring Boot 3.5.3 / Java 21

---

## 一、 执行摘要与治理边界 (Executive Summary)

本卷宗旨在为采用 ELMOS 平台实施 Spring 遗留系统现代化的商业客户（Customer）、交付团队（Delivery Lead）及独立第三方审计机构（Independent Reviewer）提供标准化的技术接入指南、验收评测规约与生产门禁合规依据。

### 核心证据阶梯与真实性红线 (Evidence Ladder)
根据 ELMOS 架构与 Batch 30 质量门禁规范（`AGENTS.md` 及 `scripts/batch30/run_framework_gate.py`）：
1. **本地工程自测证据 (`LOCAL_EXECUTED_SELF_ATTESTED` / `limited`)**：
   - 证明转换规则、AST 算子、依赖提升、Java 21 编译、本地测试及健康探测在标准工程或自测语料中验证通过。
   - 对应门禁判定：`GATE PASS: status=limited decision=NOT_CERTIFIED`。
2. **生产商用认证 (`CERTIFIED`)**：
   - **绝对禁止伪造**：不得虚构客户授权（`authorized_customer_repository`）、客户 UAT 业务签章（`customer_acceptance`）或第三方专家评审报告（`independent_review`）。
   - 必须通过实跑 P0–P11 商业试用流程（Campaign），由客户组织、独立评审机构在隔离环境完成数字签名与不可变哈希存证，方可由 `run_framework_gate.py` 授予生产证书。

---

## 二、 4 大核心工程支柱完全落地说明

### 1. P0（通用算子沉淀：Servlet 2.5 / JSP / JSTL → Spring Boot 3.5.3）
- **路由正式登记**：
  在 `apps/java-engine-worker/src/main/java/io/elmos/worker/SpringRouteCatalog.java` 中正式扩展 `SourceFamily.JAVA_EE_SERVLET`，登记 `servlet-2.5-jsp-maven-to-boot-3.5.3-java-21` 路由，覆盖 Java EE Servlet 2.5~3.0 范围。
- **确定性 AST 与配方解析**：
  - 绑定 OpenRewrite 配方：`io.elmos.openrewrite.Servlet2_5JspToSpringBoot3_5_3Java21`（位于 `apps/java-engine-worker/src/main/resources/rewrite/servlet-2.5-jsp-to-spring-boot-3.5.3.yml`）。
  - `legacy-web-modernization-engine` 结构化解析 `web.xml` 中的 `<servlet>`, `<servlet-mapping>`, `<filter>`, `<listener>`，将其自动映射为 Spring Boot `@RestController` / `@Controller`、`FilterRegistrationBean` 和 `SecurityFilterChain`。

### 2. P1（骨干路线打通：Gradle 体系与三阶基准项目）
- **Gradle 转换驱动 (`gradle_build_migrator.py`)**：
  提供对 Gradle `build.gradle` 的自动化升级算子，支持插件更新（Spring Boot 3.5.3、Dependency Management 1.1.7）、Java 21 工具链配置、以及 `javax.*` 至 `jakarta.*` 的精准依赖替换。
- **三阶复杂度标准开源基准工程 (`corpus/`)**：
  - **Tier 1 (Starter)**: 极简 Web + Actuator 探测，验证基础依赖与启动。
  - **Tier 2 (Enterprise Security + Data JPA)**: `SecurityFilterChain` 动态授权、Spring Data JPA 实体映射与 Repository 查询。
  - **Tier 3 (Multi-module Architecture)**: `common-domain`、`core-service`、`web-app` 三层多模块架构，验证跨模块依赖仲裁。
  - 自动化测试 `tests/batch30/test_gradle_modernization_benchmarks.py` 验证三阶工程全部 100% 转换通过。

### 3. P2（实跑差分环境：13 维影子比对与实库隔离）
- **差分引擎 (`shadow_diff_engine.py`)**：
  构建了自动化 HTTP 流量录制回放与 13 维等价判定器：比对 `route`, `protocol`, `view`, `binding`, `validation`, `navigation`, `session`, `security`, `transaction`, `database`, `externalEffects`, `concurrency`, `performance`。
- **动态因子脱敏与实库一致性**：
  - 过滤时间戳、动态 Nonce、SessionId 等易变因子。
  - 支持可丢弃式数据库 Schema 初始化与行级哈希比对（Row-level Checksum Diff）。
  - 具备事务回滚隔离测试，防止异常回滚泄漏。

### 4. P3（商用 PoC 接入与认证闭环：P0–P11 规范流水线）
- **PoC 计划生成器 (`scripts/batch30/generate_poc_campaign.py`)**：
  符合 `elmos.batch30.certification-campaign.v1` 规范，为试点客户一键生成包含 12 个阶段（P0–P11）的标准验收检查单。
- **生产门禁严格 Fail-Closed**：
  运行 `scripts/batch30/run_framework_gate.py` 对各 Pack 执行核验，本地工程证据通过，外部凭证严格 Fail-Closed 拦截，保障技术透明性与合规性。

---

## 三、 商业 PoC 客户入驻与前置条件 (Onboarding Prerequisites)

在正式启动商业客户生产或预发环境的 Modernization PoC 前，必须完成以下前置准备：

1. **知识产权与法律授权审查 (IP Clearance)**：
   - 确认客户源项目具备合法完整的商用源代码权利，且第三方开源依赖符合商业使用许可。
   - 签署书面授权协议，明确迁移试点范围与不可变凭证采集授权。
2. **基线环境与凭证安全托管**：
   - 客户需提供预发/沙箱隔离环境，严禁在未经授权的生产库中执行写入。
   - 敏感配置、密码及私钥必须进行脱敏，或通过 External Secrets / KMS 管理。
3. **真实流量与数据快照准备**：
   - 录制至少 50 组代表性业务场景的请求/响应报文（包含正向成功与边界异常流）。
   - 建立脱敏后的测试数据库基线快照。

---

## 四、 客户 UAT 业务验收与第三方独立审计指南

### 1. 13 维等价评测指标体系
| 维度 | 评测内容 | 验收合格标准 (Pass Criteria) |
| :--- | :--- | :--- |
| **Route & Protocol** | HTTP 方法、请求路径、协议标头 | 状态码与路由映射 100% 一致 |
| **View & Content** | JSON 响应报文、JSP 视图渲染 | 结构化报文完全等价（动态字段规范化后） |
| **Security** | 认证与授权边界、CSRF/CORS 策略 | 无非授权路径越权，安全规则不降级 |
| **Transaction & Database**| 事务提交/回滚、行级数据持久化 | 数据库变更行级哈希比对 100% 匹配，无脏数据残留 |
| **Performance** | 吞吐量、P95/P99 延迟响应 | 延迟劣化率在基线 1.5 倍容限以内，无连接池泄漏 |

### 2. 零容忍硬性不变量 (Zero-Tolerance Invariants)
以下任何一项指标大于 0，门禁立即熔断并判定 PoC 失败：
- `critical_unknowns = 0`（未识别的关键语法或组件）
- `silent_framework_drops = 0`（静默丢失的业务逻辑或拦截器）
- `critical_security_regressions = 0`（严重安全越权或鉴权缺陷）
- `critical_transaction_regressions = 0`（事务原子性破坏或分布式未同步）
- `critical_data_regressions = 0`（持久化数据行级不匹配或精度损失）
- `test_integrity_violations = 0`（测试用例被篡改或禁用断言）

---

## 五、 生产切换与应急回滚演练预案 (Rollback Playbook)

为确保生产业务的连续性，所有完成现代化翻新的服务上线必须严格遵守渐进式切换策略：

1. **影子双跑阶段 (Shadow Traffic)**：
   翻新后的 Spring Boot 3.5.3 实例旁路接入真实流量镜像，比对响应，不向主数据库执行破坏性写操作。
2. **金丝雀灰度切流 (Canary Wave Cutover)**：
   按照 `1% -> 5% -> 20% -> 100%` 的权重逐级提升流量，实时监控 Actuator 业务指标与错误率。
3. **一键回滚触发条件与流程**：
   - 若 5xx 错误率超过 0.1%，或 P99 响应延迟超过基线 200%，自动触发反向切流。
   - 数据库使用向下兼容设计（Expand-and-Contract），确保源旧系统可随时无缝接管业务。
