# Struts/Servlet to Spring Boot 4 Formal Golden Route

This Golden Route defines the minimum repeatable path for commercial certification of `spring-modernization`.

## Critical properties

- all legacy routes are mapped, explicitly removed, or unsupported
- authorization dominates every business side effect
- commit/rollback and exception mappings refine legacy behavior
- session lifecycle and filter/interceptor ordering are preserved
- critical observable traces match after approved normalization

## Certification conditions

- three repositories >500k LOC
- at least one repository >1M LOC
- failure injection
- shadow traffic
- E1-E5 complete

A successful package validation is not an E5 certification. E5 requires real repositories/environments, exact toolchain pins, failure injection and signed evidence.
