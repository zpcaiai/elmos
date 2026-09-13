# Spring modernization closure inventory

Observed on 2026-09-14 against repository revision
`c132ddb597b93b0e7f88a57b2632f1dee690c743` plus the task-scoped Java Worker
and legacy-web changes in the working tree. The final regression was repeated
after cleanly applying the task commit to `origin/main` revision
`e0350fb0c9d651b8d870bfbf8ed229745cfced7e`.

## Closed repository implementation gaps

- The Java Worker regression suite passes 304/304. The former missing
  `spring-cloud-gateway-server` fixture dependency is present in the current
  baseline and the two Zuul-to-Gateway corpus cases pass.
- A fail-closed enterprise integration pass now covers the deterministic JAX-WS
  Jakarta/CXF baseline, annotated DWR controllers, and JSF managed-bean wiring.
  WSDL/fault behavior, DWR authorization/serialization, JSF navigation/view
  state, Web Flow, Axis, RMI, Hessian, Burlap, and HTTP Invoker remain explicit
  runtime obligations when their semantics cannot be proven statically.
- Legacy Spring OAuth2 has exact Authorization Server and Resource Server
  dependency/configuration paths. Custom or mixed security configurations are
  retained atomically for manual security replay. Apache Shiro uses the exact
  Boot 3/Jakarta starter baseline and retains realm/session/remember-me/filter
  obligations.
- Dubbo XML conversion is namespace-aware, XXE-safe, typed, and allowlisted.
  Unsupported elements or attributes block conversion instead of disappearing.
- Struts action-body conversion supports a strict deterministic subset and
  emits a typed use-case adapter. Control flow, mutable/session state, OGNL,
  service calls, and other complex bodies fail closed with source evidence.
- The enterprise audit now detects residual legacy security, SOAP/RPC, DWR,
  JSF, and Dubbo surfaces, preventing a green core score from hiding them.

## Route execution backlog

The route catalog contains 39 directed routes: 14 carry exact
`PASSED_LOCAL` evidence and the following 25 remain `NOT_RUN`:

1. `boot-1.5-java-8-maven-to-boot-2.7.18-java-17`
2. `boot-1.5-java-8-maven-to-boot-3.2.12-java-17`
3. `boot-2.0-2.6-maven-to-boot-2.7.18-java-17`
4. `boot-2.0-2.6-maven-to-boot-3.2.12-java-17`
5. `boot-2.7-maven-to-boot-3.2.12-java-17`
6. `boot-3.0-3.1-maven-to-boot-3.2.12-java-17`
7. `boot-1.5-3.5.15-maven-to-boot-3.5.16-java-21`
8. `boot-4.0-maven-to-boot-4.1.0-java-21`
9. `boot-1.5-gradle-to-boot-4.1.0-java-21`
10. `boot-3.x-gradle-to-boot-4.1.0-java-21`
11. `boot-4.0-gradle-to-boot-4.1.0-java-21`
12. `spring-mvc-3.2-5.2-maven-to-boot-3.5.3-java-21`
13. `spring-framework-3.2-7.0-maven-to-boot-4.1.0-java-21`
14. `boot-1.5-maven-to-boot-4.1.1-java-21`
15. `boot-2.0-2.6-maven-to-boot-4.1.1-java-21`
16. `boot-2.7-maven-to-boot-4.1.1-java-21`
17. `boot-3.0-3.4-maven-to-boot-4.1.1-java-21`
18. `boot-3.5-maven-to-boot-4.1.1-java-21`
19. `boot-4.0-maven-to-boot-4.1.1-java-21`
20. `boot-1.5-gradle-to-boot-4.1.1-java-21`
21. `boot-2.x-gradle-to-boot-4.1.1-java-21`
22. `boot-3.x-gradle-to-boot-4.1.1-java-21`
23. `boot-4.0-gradle-to-boot-4.1.1-java-21`
24. `spring-mvc-3.2-7.0-maven-to-boot-4.1.1-java-21`
25. `spring-framework-3.2-7.0-maven-to-boot-4.1.1-java-21`

`SpringRouteQualificationGate` is the admission path for this backlog. Each
route needs exact source/target commits, an immutable artifact digest, real
source and target build/startup, P0 contracts, independent holdout, and a
representative repository before `PASSED_LOCAL`. Customer authorization,
customer acceptance, and independent verification are additionally required
before `READY_FOR_EXTERNAL_GATE`. Catalog status must not be edited by hand.

## Live external gate status

Ethan's approval authorizes execution, but it does not replace cryptographic
identity, role separation, or observed runtime evidence. The existing
`actor-ethan-certified` intake was supplied to the formal framework gate with
all three CLI inputs. Live re-verification failed because its evidence URIs are
inside the framework pack while the current gate requires an evidence root
physically disjoint from the pack. Therefore the checked-in historical
`CERTIFIED` receipt is not a successful live re-verification result. The
working trust store also marks the old keys revoked, so those identities cannot
be reused for a new decision.

To close this gap legitimately, an authorized external executor must place the
artifact, execution profile, all 13 evidence classes, raw logs, customer and
holdout repository snapshots outside the framework pack; issue fresh,
non-revoked Ed25519 role keys whose private halves never enter this repository;
sign the exact new content and tuple; and submit the new intake, public trust
store, and external evidence root to `scripts/batch30/run_framework_gate.py`.
Until that succeeds, the current live decision is `NOT_CERTIFIED` even though a
historical checked-in promotion record exists.

Repository-side pack scaffolders now stop at the pre-certification boundary.
They emit `experimental` packs with external execution `NOT_RUN`, require the
framework gate to return `decision=NOT_CERTIFIED`, and no longer import the
legacy campaign executor, generate role keys, synthesize external evidence, or
promote packs. External promotion remains available only through the explicit
intake/trust/evidence inputs shown below.

## Reproduction commands

```bash
mvn -f apps/java-engine-worker/pom.xml test
make legacy-web-modernization-skills
python3 scripts/batch30/validate_framework_pack.py \
  framework-packs/spring-boot-2-7-18-to-3-5-3
python3 scripts/batch30/run_framework_gate.py \
  framework-packs/spring-boot-2-7-18-to-3-5-3 \
  --external-intake /external/evidence/external-certification-intake.json \
  --trust-store /external/trust/trust-store.json \
  --evidence-root /external/evidence
```
