# Primary References

本能力包的框架事实与目标基线优先依据官方规范、官方文档和上游源码。

## Spring Boot 4

- Spring Boot 4.0 Migration Guide  
  https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide
- Spring Boot Reference Documentation  
  https://docs.spring.io/spring-boot/

关键基线：Java 17+、Spring Framework 7.x、Jakarta EE 11、Servlet 6.1；Boot 4 采用更细粒度模块/Starter。

## Jakarta Servlet 6.1

- Specification  
  https://jakarta.ee/specifications/servlet/6.1/jakarta-servlet-spec-6.1

重点章节：RequestDispatcher、Filters、Listeners、Sessions、Security、Deployment Descriptor、web-fragment merge、error dispatch、async、multipart 和 WAR 结构。

## Apache Struts 1

- Source repository  
  https://github.com/apache/struts1
- `RequestProcessor.java`  
  `core/src/main/java/org/apache/struts/action/RequestProcessor.java`
- `ActionForm.java`  
  `core/src/main/java/org/apache/struts/action/ActionForm.java`

源码表明 Struts1 的请求流水线包含 multipart、path、locale、preprocess、mapping、roles、form、populate、validate、forward/include、Action、exception 和 final forward；ActionForm reset 在 populate 前，validate 在 Action 执行前；Action 实例存在共享/缓存生命周期风险。

## Apache Struts 2

- Source repository  
  https://github.com/apache/struts
- Interceptors documentation  
  https://struts.apache.org/core-developers/interceptors
- `DefaultActionInvocation.java`  
  `core/src/main/java/org/apache/struts2/DefaultActionInvocation.java`

源码和文档表明 interceptor stack 是 around-invocation 链，顺序、短路、after unwind、PreResultListener、Result、ValueStack/OGNL 和 action chain 都属于必须保留的运行时语义。

## Transformation Tooling

- OpenRewrite  
  https://github.com/openrewrite/rewrite

本包采用其“结构化 recipe + 类型信息 + 可重复变换”思想，但要求所有 framework rewrite 受 Evidence Graph 和 Semantic IR 前置约束。
