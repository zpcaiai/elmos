# Batch 30 Initial Framework Matrix

| Pack family | Typical source | Typical target | Primary risks |
|---|---|---|---|
| Spring upgrade | Spring Boot exact version | Spring Boot exact version | Jakarta, auto-config, Security, Hibernate, properties |
| Jakarta modernization | Java/Jakarta EE server | Spring/Quarkus/Micronaut/Jakarta target | EJB, JTA/XA, JMS, JNDI, classloading |
| Quarkus | Spring/Jakarta/Quarkus | Quarkus or another target | build-time augmentation, Arc, extensions, native |
| Micronaut | Spring/Jakarta/Micronaut | Micronaut or another target | compile-time DI/AOP, generated metadata, native |
| .NET modernization | .NET Framework | modern .NET | System.Web, WCF, Windows APIs, EF6 |
| ASP.NET reverse | ASP.NET Core | Spring Boot | middleware, policies, EF Core, hosted services |
| FastAPI | FastAPI | configurable | dependency graph, Pydantic, ASGI, async |
| Django | Django/DRF | configurable | settings/apps, ORM/migrations, auth, signals, admin |
| Flask | Flask | configurable | dynamic registration, contexts, extensions, WSGI |
| SQLAlchemy | SQLAlchemy | target ORM/data layer | session/UoW, query, loading, migrations |
| Python jobs | Celery/RQ | target worker/workflow | ack, retry, workflow, schedule, idempotency |
| NestJS | NestJS | configurable | modules, scopes, guards/interceptors, transports |
| Express/Node | Express/Node | configurable | route order, dynamic middleware, async errors |
| Coexistence | any supported source | any supported target | authority, duplicate effects, security, exit |

Every concrete pack must use exact versions and a separately validated target profile.
