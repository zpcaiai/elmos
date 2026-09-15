# Spring modernization closure inventory

Observed on 2026-09-14 against the task-scoped Spring modernization branch.

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

## Route-local execution closure

The catalog's 39 directed routes now all carry one exact `PASSED_LOCAL` tuple:
39/39, or 100% route-local coverage. The final environment-dependent routes
were closed with a governed Gradle 4.10.3/JDK 8 Docker source stage followed by
Gradle 8.14.3/JDK 21 transformation, and a typed FCM generator whose non-Boot
Spring/MVC sources build and start in digest-pinned Docker contexts before a
fresh Boot target is built and its observable behavior compared.

This closes only the synthetic exact-tuple route layer. It does not generalize
evidence to another version spelling, source graph, framework feature, build
environment, or customer repository. `SpringRouteQualificationGate` remains
the only catalog admission path; catalog status must not be edited without the
corresponding canonical evidence file.

## Live external gate status

Ethan's approval authorizes execution, but it does not replace cryptographic
identity, role separation, or observed runtime evidence. No externally supplied
`external-intake`, `trust-store`, or physically separate `evidence-root` is
available in this run. The structural framework gate therefore validates the
experimental pack but returns `decision=NOT_CERTIFIED`; the external campaign
remains `NOT_RUN`. Any checked-in historical `actor-ethan-certified` material
inside a framework pack is not a successful live re-verification result because
the current gate requires evidence roots physically disjoint from the pack.

To close this gap legitimately, an authorized external executor must place the
artifact, execution profile, all 13 evidence classes, raw logs, customer and
holdout repository snapshots outside the framework pack; issue fresh,
non-revoked Ed25519 role keys whose private halves never enter this repository;
sign the exact new content and tuple; and submit the new intake, public trust
store, and external evidence root to `scripts/batch30/run_framework_gate.py`.
Until that succeeds, the current live decision remains `NOT_RUN / NOT_CERTIFIED`
even though all route-local reference fixtures pass.

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
