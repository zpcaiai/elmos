package io.elmos.persistence;

import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

/** Real PostgreSQL checks; requires an explicitly acknowledged disposable database. */
class JdbcTranslationExecutionInputLiveTest {
    static JdbcClient jdbc;
    static TransactionTemplate transactions;
    static DriverManagerDataSource connections;

    @BeforeAll static void database() throws Exception {
        String url = System.getenv("ELMOS_EXECUTION_QUEUE_TEST_JDBC_URL");
        assumeTrue(url != null && !url.isBlank(), "requires a disposable PostgreSQL fixture");
        if (!"true".equals(System.getenv("ELMOS_EXECUTION_QUEUE_TEST_DISPOSABLE")))
            throw new IllegalStateException("ELMOS_EXECUTION_QUEUE_TEST_DISPOSABLE=true required");
        var data = new DriverManagerDataSource(url,
                System.getenv().getOrDefault("ELMOS_EXECUTION_QUEUE_TEST_DATABASE_USER", System.getProperty("user.name")),
                System.getenv().getOrDefault("ELMOS_EXECUTION_QUEUE_TEST_DATABASE_PASSWORD", ""));
        Flyway.configure().dataSource(data).defaultSchema("public").load().migrate();
        // Exercise the repository's exact operator provisioning artifact, not
        // a test-only role whose permissions the deployed runtime cannot obtain.
        try(var connection=data.getConnection();var statement=connection.createStatement();
            var script=new org.springframework.core.io.ClassPathResource("db/provisioning/translation_input_runtime.sql").getInputStream()) {
            statement.execute(new String(script.readAllBytes(),java.nio.charset.StandardCharsets.UTF_8));
        }
        jdbc = JdbcClient.create(data);
        connections = data;
        transactions = new TransactionTemplate(new DataSourceTransactionManager(data));
    }

    @Test void expiredPreparedInputDoesNotAssumeAnUnknownPutHasStopped() {
        String org = tenant(); String object = object(org, 1); String binding = prepare(org, object, "same", 1);
        jdbc.sql("UPDATE execution_input_bindings SET prepared_expires_at = now() - interval '1 day' WHERE binding_id = :id")
                .param("id", binding).update();
        gc();
        assertEquals("AVAILABLE", state(object));
        assertTrue(retained(object));
        assertThrows(RuntimeException.class, () -> prepare(org, object, "same", 1),
                "a PREPARED root with an unknown writer cannot issue a second PUT permit");
    }

    @Test void uploadRegistrationCannotReissuePurgedKeysOrChangeContentIdentity() {
        String org=tenant();var store=new JdbcObjectStorageStore(jdbc,transactions,reference->{throw new AssertionError("no provider credentials needed");});
        String id=store.registerPendingObject(org,digest(50),100,"application/zip","primary","tenant-fixture/key");
        assertEquals(id,store.registerPendingObject(org,digest(50),100,"application/zip","primary","tenant-fixture/key"));
        assertThrows(io.elmos.storage.S3ObjectStore.ObjectStorageException.class,()->store.registerPendingObject(org,digest(50),101,"application/zip","primary","tenant-fixture/key"));
        assertThrows(io.elmos.storage.S3ObjectStore.ObjectStorageException.class,()->store.registerPendingObject(org,digest(50),100,"application/zip","primary","changed-key"));
        store.markAvailable(org,id);
        assertEquals(id,store.registerPendingObject(org,digest(50),100,"application/zip","primary","tenant-fixture/key"),"available exact content dedup remains compatible");
        for(String state:java.util.List.of("PURGE_PENDING","PURGED")) {
            jdbc.sql("UPDATE content_objects SET object_state=:state WHERE content_object_id=:id").param("state",state).param("id",id).update();
            assertThrows(io.elmos.storage.S3ObjectStore.ObjectStorageException.class,()->store.registerPendingObject(org,digest(50),100,"application/zip","primary","tenant-fixture/key"));
        }
    }

    @Test void provisioningRejectsAnUnsafeExistingRuntimeRole() throws Exception {
        for(String attribute:java.util.List.of("LOGIN","CREATEDB","CREATEROLE","REPLICATION","INHERIT","SUPERUSER","BYPASSRLS")) {
        try(var connection=connections.getConnection();var statement=connection.createStatement();
            var script=new org.springframework.core.io.ClassPathResource("db/provisioning/translation_input_runtime.sql").getInputStream()) {
            connection.setAutoCommit(false);
            try {
                statement.execute("ALTER ROLE elmos_translation_input_runtime "+attribute);
                String sql=new String(script.readAllBytes(),java.nio.charset.StandardCharsets.UTF_8);
                assertTrue(assertThrows(java.sql.SQLException.class,()->statement.execute(sql)).getMessage().contains("ELMOS_TRANSLATION_RUNTIME_ROLE_UNSAFE"));
            } finally {connection.rollback();}
        }
        }
    }

    @Test void digestTenantAndIdempotencyDriftCannotAttachAnotherObject() {
        String org = tenant(); String other = tenant(); String object = object(org, 2);
        prepare(org, object, "key", 2);
        assertThrows(RuntimeException.class, () -> prepare(other, object, "key", 2));
        assertThrows(RuntimeException.class, () -> prepare(org, object, "key", 3));
        String next = object(org, 3);
        assertThrows(RuntimeException.class, () -> prepare(org, next, "key", 3));
        assertEquals(1L, jdbc.sql("SELECT count(*) FROM execution_input_bindings WHERE organization_id = :org")
                .param("org", org).query(Long.class).single());
    }

    @Test void attachedInputLivesThroughRunningAndTerminalRetentionThenBecomesPurgeable() {
        String org = tenant(); String object = object(org, 4); String binding = prepare(org, object, "key", 4);
        String job = "job-" + UUID.randomUUID();
        jdbc.sql("""
            INSERT INTO execution_jobs(job_id,organization_id,actor_id,business_line,job_kind,idempotency_key,
              request_digest,required_capability,request_payload)
            VALUES (:job,:org,'fixture','TRANSLATION','translate-pipeline-v1',:job,:sha,'translation:multi',
              jsonb_build_object('input',jsonb_build_object('bindingId',CAST(:binding AS text),'objectId',CAST(:object AS text),
                'sha256',CAST(:sha AS text),'byteSize',CAST(100 AS bigint))))
            """).param("job", job).param("org", org).param("binding", binding).param("object", object).param("sha", digest(4)).update();
        assertEquals(Boolean.TRUE, transactions.execute(status -> {
            bind(org);
            return jdbc.sql("SELECT elmos_attach_execution_input(:org,:job,:binding)")
                    .param("org",org).param("job",job).param("binding",binding).query(Boolean.class).single();
        }));
        gc(); assertEquals("AVAILABLE", state(object));
        jdbc.sql("UPDATE execution_jobs SET status='CANCELLED',finished_at=now() WHERE job_id=:job").param("job",job).update();
        gc(); assertEquals("AVAILABLE", state(object));
        jdbc.sql("UPDATE execution_jobs SET finished_at=now()-interval '3651 days' WHERE job_id=:job").param("job",job).update();
        gc(); assertEquals("PURGE_PENDING", state(object));
        assertThrows(RuntimeException.class, () -> prepare(org,object,"key",4), "purge decision cannot be resurrected");
    }

    @Test void unresolvedPreparationHasAFiniteTenantBudget() {
        String org = tenant();
        for (int i=10;i<18;i++) prepare(org,object(org,i),"key-"+i,i);
        String extra = object(org,18);
        assertThrows(RuntimeException.class, () -> prepare(org,extra,"overflow",18));
        assertEquals(8L,jdbc.sql("SELECT count(*) FROM execution_input_bindings WHERE organization_id=:org")
                .param("org",org).query(Long.class).single());
    }

    @Test void ordinaryDefinerUsesGlobalBudgetAndRuntimeCannotBypassTenantRls() throws Exception {
        String org=tenant(), other=tenant(), ownObject=object(org,40), otherObject=object(other,41);
        prepare(other,otherObject,"existing",41);
        String owner="input_owner_"+UUID.randomUUID().toString().replace("-","");
        String prepareSignature="elmos_prepare_execution_input(varchar,varchar,varchar,varchar,varchar,bigint)";
        try(var connection=connections.getConnection()) {
            connection.setAutoCommit(false);
            try {
                execute(connection,"CREATE ROLE "+owner+" NOLOGIN NOSUPERUSER NOBYPASSRLS");
                execute(connection,"GRANT USAGE ON SCHEMA public TO "+owner);
                execute(connection,"GRANT SELECT,INSERT,UPDATE ON execution_input_bindings,execution_input_admission_budgets,content_objects TO "+owner);
                execute(connection,"GRANT SELECT ON execution_jobs TO "+owner);
                execute(connection,"GRANT EXECUTE ON FUNCTION elmos_effective_retention_days(varchar,varchar) TO "+owner);
                execute(connection,"ALTER FUNCTION "+prepareSignature+" OWNER TO "+owner);
                execute(connection,"ALTER FUNCTION elmos_execution_input_retained(varchar) OWNER TO "+owner);
                execute(connection,"SET LOCAL ROLE elmos_translation_input_runtime");
                assertEquals("true",scalar(connection,"SELECT has_function_privilege(current_user,?,'EXECUTE')",prepareSignature));
                assertEquals("false",scalar(connection,"SELECT has_table_privilege(current_user,'execution_input_admission_budgets','SELECT')"));
                scalar(connection,"SELECT set_config('app.organization_id',?,true)",org);
                String binding=scalar(connection,"SELECT elmos_prepare_execution_input(?,?,?,?,?,CAST(100 AS bigint))",
                        "input-"+UUID.randomUUID(),org,"own",ownObject,digest(40));
                assertTrue(binding.startsWith("input-"));
                assertEquals("1",scalar(connection,"SELECT count(*) FROM execution_input_bindings"),"runtime sees only its own binding");
                denied(connection,"ELMOS_EXECUTION_INPUT_SUBJECT_INVALID",
                        "SELECT elmos_prepare_execution_input(?,?,?,?,?,CAST(100 AS bigint))",
                        "input-"+UUID.randomUUID(),other,"cross",otherObject,digest(41));
                denied(connection,"ELMOS_EXECUTION_INPUT_UPLOAD_UNRECONCILED",
                        "SELECT elmos_prepare_execution_input(?,?,?,?,?,CAST(100 AS bigint))",
                        "input-"+UUID.randomUUID(),org,"own",ownObject,digest(40));

                execute(connection,"RESET ROLE");
                execute(connection,"UPDATE execution_input_admission_budgets SET prepared_count=128 WHERE budget_key='global'");
                execute(connection,"SET LOCAL ROLE elmos_translation_input_runtime");
                denied(connection,"ELMOS_EXECUTION_INPUT_UNRECONCILED_CAPACITY",
                        "SELECT elmos_prepare_execution_input(?,?,?,?,?,CAST(100 AS bigint))",
                        "input-"+UUID.randomUUID(),org,"global-full",ownObject,digest(40));
                execute(connection,"RESET ROLE");
                execute(connection,"DELETE FROM execution_input_admission_budgets WHERE budget_key='global'");
                execute(connection,"SET LOCAL ROLE elmos_translation_input_runtime");
                denied(connection,"ELMOS_EXECUTION_INPUT_BUDGET_STATE_UNKNOWN",
                        "SELECT elmos_prepare_execution_input(?,?,?,?,?,CAST(100 AS bigint))",
                        "input-"+UUID.randomUUID(),org,"missing-counter",ownObject,digest(40));

                execute(connection,"RESET ROLE"); execute(connection,"SET LOCAL ROLE "+owner);
                assertEquals("true",scalar(connection,"SELECT row_security_active('execution_input_bindings')"));
                assertEquals("true",scalar(connection,"SELECT elmos_execution_input_retained(?)",otherObject),"hidden objects are never unreferenced");
                scalar(connection,"SELECT set_config('app.organization_id','',true)");
                denied(connection,"ELMOS_OBJECT_GC_TENANT_CONTEXT_REQUIRED","SELECT elmos_execution_input_retained(?)",ownObject);
            } finally {connection.rollback();}
        }
    }

    @Test void tenantContextConstrainsGcEvenWithPrivilegedFunctionOwner() {
        String org=tenant(), other=tenant(), ownObject=object(org,42), otherObject=object(other,43);
        transactions.executeWithoutResult(status->{bind(org);gc();});
        assertEquals("PURGE_PENDING",state(ownObject));
        assertEquals("AVAILABLE",state(otherObject),"superuser SECURITY DEFINER must still honor the explicit tenant scope");
    }

    @Test void concurrentPrepareGrantsOnlyOneExternalWriterAuthority() throws Exception {
        String org=tenant(), object=object(org,44);
        try(var first=connections.getConnection();var pool=java.util.concurrent.Executors.newSingleThreadExecutor()) {
            first.setAutoCommit(false);
            scalar(first,"SELECT set_config('app.organization_id',?,true)",org);
            scalar(first,"SELECT elmos_prepare_execution_input(?,?,?,?,?,CAST(100 AS bigint))",
                    "input-"+UUID.randomUUID(),org,"one-writer",object,digest(44));
            var started=new java.util.concurrent.CountDownLatch(1);
            var second=pool.submit(()->{
                started.countDown();
                return assertThrows(RuntimeException.class,()->prepare(org,object,"one-writer",44));
            });
            assertTrue(started.await(20,java.util.concurrent.TimeUnit.SECONDS));
            first.commit();
            assertTrue(second.get(20,java.util.concurrent.TimeUnit.SECONDS).getMessage().contains("ELMOS_EXECUTION_INPUT_UPLOAD_UNRECONCILED"));
            assertEquals(1L,jdbc.sql("SELECT prepared_count::bigint FROM execution_input_admission_budgets WHERE budget_key=:key")
                    .param("key","tenant:"+org).query(Long.class).single());
        }
    }

    private static void execute(java.sql.Connection connection,String sql) throws java.sql.SQLException {
        try(var statement=connection.createStatement()){statement.execute(sql);}
    }
    private static String scalar(java.sql.Connection connection,String sql,String... parameters) throws java.sql.SQLException {
        try(var statement=connection.prepareStatement(sql)) {
            for(int index=0;index<parameters.length;index++)statement.setString(index+1,parameters[index]);
            try(var result=statement.executeQuery()){assertTrue(result.next());return String.valueOf(result.getObject(1));}
        }
    }
    private static void denied(java.sql.Connection connection,String code,String sql,String... parameters) throws java.sql.SQLException {
        var savepoint=connection.setSavepoint();
        try {assertTrue(assertThrows(java.sql.SQLException.class,()->scalar(connection,sql,parameters)).getMessage().contains(code));}
        finally {connection.rollback(savepoint);connection.releaseSavepoint(savepoint);}
    }

    @Test void publisherCannotResurrectObjectWhenGcWonTheObjectLock() throws Exception {
        String org=tenant(), object=object(org,30), job="job-"+UUID.randomUUID();
        jdbc.sql("""
            INSERT INTO execution_jobs(job_id,organization_id,actor_id,business_line,job_kind,idempotency_key,
              request_digest,required_capability) VALUES(:job,:org,'fixture','TRANSLATION','legacy-fixture',:job,:sha,'translation:multi')
            """).param("job",job).param("org",org).param("sha",digest(30)).update();
        try (var owner=connections.getConnection(); var pool=java.util.concurrent.Executors.newSingleThreadExecutor()) {
            owner.setAutoCommit(false);
            try(var lock=owner.prepareStatement("SELECT content_object_id FROM content_objects WHERE content_object_id=? FOR UPDATE")) {
                lock.setString(1,object); lock.executeQuery().close();
            }
            var publisherPid=new java.util.concurrent.CompletableFuture<Integer>();
            var published=pool.submit(()->{
                try(var publisher=connections.getConnection()) {
                    try(var query=publisher.createStatement();var result=query.executeQuery("SELECT pg_backend_pid()")) {
                        result.next();publisherPid.complete(result.getInt(1));
                    }
                    try(var call=publisher.prepareStatement("SELECT elmos_publish_job_artifact(?,?,?,?,?,?,?)")) {
                        call.setString(1,"artifact-"+UUID.randomUUID());call.setString(2,org);call.setString(3,job);
                        call.setString(4,"PROJECT_ARCHIVE");call.setString(5,"fixture.zip");call.setString(6,object);call.setString(7,"STANDARD");
                        call.executeQuery().close();return true;
                    } catch(java.sql.SQLException expected) {return false;}
                }
            });
            try {
                int pid=publisherPid.get(20,java.util.concurrent.TimeUnit.SECONDS);
                long deadline=System.nanoTime()+java.util.concurrent.TimeUnit.SECONDS.toNanos(20);
                boolean blocked=false;
                while(System.nanoTime()<deadline) {
                    blocked=jdbc.sql("SELECT cardinality(pg_blocking_pids(:pid))>0").param("pid",pid).query(Boolean.class).single();
                    if(blocked) break;
                    Thread.sleep(10);
                }
                assertTrue(blocked,"publisher must reach the controlled object-lock boundary");
                try(var gc=owner.prepareStatement("SELECT elmos_expire_artifacts(?,5000)")) {
                    gc.setString(1,"gc-"+UUID.randomUUID());gc.executeQuery().close();
                }
                owner.commit();
                assertFalse(published.get(20,java.util.concurrent.TimeUnit.SECONDS),"publisher must re-read PURGE_PENDING after acquiring the lock");
                assertEquals("PURGE_PENDING",state(object));
                assertEquals(0L,jdbc.sql("SELECT count(*) FROM job_artifacts WHERE content_object_ref=:object")
                        .param("object",object).query(Long.class).single());
            } finally {owner.rollback();}
        }
    }

    static String tenant() {
        String org="org-v86-"+UUID.randomUUID();
        jdbc.sql("INSERT INTO organizations(organization_id) VALUES(:org)").param("org",org).update(); return org;
    }
    static String digest(int n) { return String.format("%064x", n); }
    static String object(String org,int n) {
        String id="obj-"+UUID.randomUUID();
        jdbc.sql("""
            INSERT INTO content_objects(content_object_id,organization_id,content_sha256,byte_size,backend_id,storage_key,
              object_state,uploaded_at,verified_at) VALUES(:id,:org,:sha,100,'primary',:id,'AVAILABLE',now(),now())
            """).param("id",id).param("org",org).param("sha",digest(n)).update(); return id;
    }
    static void bind(String org) {
        jdbc.sql("SELECT set_config('app.organization_id',:org,true)").param("org",org).query(String.class).single();
    }
    static String prepare(String org,String object,String key,int n) {
        return transactions.execute(status -> {
            bind(org);
            return jdbc.sql("SELECT elmos_prepare_execution_input(:id,:org,:key,:object,:sha,CAST(100 AS bigint))")
                    .param("id","input-"+UUID.randomUUID()).param("org",org).param("key",key)
                    .param("object",object).param("sha",digest(n)).query(String.class).single();
        });
    }
    static boolean retained(String object) {
        return jdbc.sql("SELECT elmos_execution_input_retained(:object)").param("object",object).query(Boolean.class).single();
    }
    static String state(String object) {
        return jdbc.sql("SELECT object_state FROM content_objects WHERE content_object_id=:object")
                .param("object",object).query(String.class).single();
    }
    static void gc() {
        jdbc.sql("SELECT elmos_expire_artifacts(:id,5000)").param("id","gc-"+UUID.randomUUID()).query(Integer.class).single();
    }
}
