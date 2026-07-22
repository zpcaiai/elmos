# ELMOS Database and Data Platform Engine

This independently deployable Java 21 worker is ELMOS's fifth execution engine. Its repository-safe core declares vendor Runner boundaries, three independent modernization tracks, target-candidate policy, a governed migration state machine, canonical conversion obligations, cutover aggregation, and 24 deterministic accident scenarios.

Run the module with:

    JAVA_HOME=$(/usr/libexec/java_home -v 21) mvn -B -pl engines/database-data-engine -am verify
    java -jar engines/database-data-engine/target/elmos-database-data-engine-0.1.0-SNAPSHOT-exec.jar
    curl http://127.0.0.1:8089/engine/v1/capabilities

The worker exposes the shared capability, scan, plan, execute-step, validate, tenant-scoped job, and cancellation routes. Oracle, SQL Server, MySQL, PostgreSQL, Data Platform, and BI Validation Runners are declared but NOT_CONFIGURED. Requests that require database access or external evidence return terminal FAILED with empty evidence.

The static core never opens JDBC connections, launches host processes, loads vendor libraries, changes logging, starts CDC, writes customer data, or switches a production writer. Those actions require a short-lived job credential, a capability-matched approved Runner, explicit production authority, immutable provider evidence, and independent validation.

Five JSON Schema fixtures, the OpenAPI contract, and the 24 required Batch 15 incidents are checked by the module tests. These artifacts do not claim that a customer database, lakehouse, pipeline, report, or metric was migrated.
