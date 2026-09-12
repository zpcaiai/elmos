# Spring 老项目现代化 Domain Pack

## 保证目标
Approved compatibility contract + old/new native runtime observations

## 首个商业纵向切片
一个可原生启动的Struts/Servlet样例 → 指定并批准的Spring Boot目标版本；旧新隔离运行

## 核心语义
旧系统黄金行为包含HTTP、headers、cookie/session、DB delta、event/cache、安全判断、异常与视图；也采集批处理和scheduler。
用真实容器/框架/DB验证事务代理、事务边界、调用链与异常；仅MockMvc或mock repository不能覆盖所有真实效应。
目标Boot/Framework/JDK/Jakarta/Servlet版本必须兼容矩阵锁定，不把“升级Boot 4”视为逐行注解替换。
既有漏洞/不合规行为形成approved behavior change，设计修复与单独测试；其他兼容性继续保留。
旧系统无法运行：只能提供scoped静态/合同保证，不自动给行为等价E4/E5。

## 必需验收场景
- **SPR-001** — 未登录请求+returnUrl：status/Location/cookie/session及安全决策一致或有批准变化。
- **SPR-002** — invalid binding/validation：业务逻辑/DB写入不得先于校验。
- **SPR-003** — 事务中途异常/checked exception/self-invocation：验证实际rollback/propagation，不只扫描注解。
- **SPR-004** — filter/interceptor/shiro/security顺序：逐条拒绝/允许路径和副作用核对。
- **SPR-005** — multipart/i18n/JSP/forward/redirect：文件/编码/视图/headers/cookies语义正确。
- **SPR-006** — Quartz/定时任务重复触发及旧任务残留：副作用幂等和调度交接符合合同。

## 形式化义务候选
请求状态/权限映射DSL规则；已建模validation-before-effect规则；小型配置规则的前置条件。

## 不支持/阻塞
无法取得的旧runtime证据；未建模动态代理/插件行为；无许可闭源依赖。

## 成熟度
本包仅SPECIFIED，原生适配与客户认证NOT_RUN。每种确切source/target/feature/environment组合独立晋级；不能用一个语言/DB测试结果覆盖整个矩阵。
