# Spring Framework 5.3 MVC / Java 11 to Spring Boot 3.5.3 / Java 21

Directional Batch 30 experimental modernization pack for a traditional, non-Boot
Spring MVC WAR application. The only admitted source tuple is Spring Framework
`5.3.39`, Java `11`, Maven `3.9.11`, Servlet API `4.0.1`, and WAR packaging. The
target tuple is Spring Boot `3.5.3`, Spring Framework `6.2.8`, Java `21`, Maven
`3.9.11`, Jakarta Servlet `6.1`, and embedded Tomcat `10.1.42`.

The pack contains a typed Framework Contract Model, deterministic OpenRewrite
recipe composition, an executable-shaped legacy MVC development fixture, and
fail-closed target obligations. Its exact identity is now wired into the route
catalog and source fingerprint, but that does not make the migration executable:
the traditional WAR source still requires an exact approved Servlet 4 container,
and Boot bootstrap, context merge, web.xml retirement and view strategy remain
explicit FCM obligations rather than inferred edits. Source build/startup,
transformation, target build/startup, behavior parity, negative cases, holdout,
representative repository, customer, Rootless, and independent review evidence
are all `NOT_RUN`.

Consequently the pack is `experimental` and `NOT_CERTIFIED`. Static validation
must never be presented as migration success or behavior equivalence.

Validation commands:

```bash
python3 scripts/batch30/validate_legacy_spring_mvc_pack.py
python3 scripts/batch30/validate_framework_pack.py \
  framework-packs/spring-framework-5-3-mvc-to-spring-boot-3-5-3
python3 scripts/batch30/run_framework_gate.py \
  framework-packs/spring-framework-5-3-mvc-to-spring-boot-3-5-3
```
