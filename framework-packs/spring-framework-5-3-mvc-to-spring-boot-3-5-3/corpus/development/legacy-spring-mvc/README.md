# Legacy Spring MVC development fixture

Executable-shaped non-Boot WAR fixture pinned to Spring Framework `5.3.39`,
Java `11`, Maven `3.9.11`, Servlet API `4.0.1` and Hibernate Validator
`6.2.5.Final`. It deliberately includes `web.xml`, root and servlet XML
contexts, filter/interceptor ordering, validation, ControllerAdvice, a JSP view
resolver and a small MockMvc contract suite.

The fixture has not been built or started with the exact toolchain. Its status is
`PREPARED_NOT_RUN`, not PASS evidence.
