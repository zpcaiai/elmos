# Target scaffold

`materialize_target.py` is the pack-local, controlled emitter for inspecting the
exact development profile. The governed worker production path does not execute
this or any other repository Python. After the pinned OpenRewrite step and before
target verification it calls the typed Java
`io.elmos.worker.SpringMvcExactTargetMaterializer`.

The Java materializer is intentionally `EXACT_FIXTURE_ONLY`. Its immutable
classpath manifest binds all 13 admitted source files by path, byte count and
SHA-256, and it additionally validates the exact POM, Servlet XML, Spring XML,
Java and JSP shapes. It atomically creates a fresh Spring Boot 3.5.3 executable
WAR tree with content-addressed source-map and retirement receipts. It never
mutates the source or overwrites an existing output tree. Unknown source-owned
files, changed bytes, symlinks, route drift and unsupported constructs fail
closed.

Both emitters reject unknown dependencies, Servlet bootstrap elements, XML imports
or beans, JSP tag libraries, programmatic initializers, and provider-backed
security/data/transaction/messaging/cache/scheduler constructs. Those require
separate exact profiles; they are not silently dropped.

```bash
python3 target-profile/scaffold/materialize_target.py \
  --source corpus/development/legacy-spring-mvc \
  --output /new/empty/path/legacy-spring-mvc-boot
```

Materialization is static engineering preparation. Production wiring and unit
tests are not target build/startup evidence. The generated receipt retains
source build/startup, target build/startup, and behavior equivalence as `NOT_RUN`
until the exact Maven/JDK/container gates execute.
