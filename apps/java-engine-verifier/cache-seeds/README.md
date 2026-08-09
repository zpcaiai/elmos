# Independent verifier Maven cache seeds

These POMs pre-resolve the dependencies and build plugins needed by the three
exact target tuples accepted by the Spring artifact verifier:

| Target Spring Boot | Target Java | Seed |
|---|---:|---|
| 2.7.18 | 17 | `spring-boot-2.7.18-java-17/pom.xml` |
| 3.2.12 | 17 | `spring-boot-3.2.12-java-17/pom.xml` |
| 3.5.3 | 21 | `spring-boot-3.5.3-java-21/pom.xml` |

Each seed includes representative web, validation, security, JPA/transaction,
Kafka messaging, actuator, H2 and test dependencies. Its Enforcer execution
rejects the wrong JDK before Maven resolves the tuple. The verifier Dockerfile
runs `go-offline` and `verify` for all three POMs into the same
`/opt/elmos/maven-cache`, then copies that cache into the runtime image as a
root-owned read-only dependency source. Each verification run copies only from
that immutable seed into a private writable repository.

These seeds are build plumbing, not behavior evidence. Static inspection or a
successful image build does not establish application startup, behavioral
equivalence, holdout success, external verification or certification.
